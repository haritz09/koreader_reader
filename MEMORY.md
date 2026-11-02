# Project Memory

Durable decisions and constraints only. Repository operating rules belong in `AGENTS.md`.

## Product

- API-first backend; the planned client is Next.js with TypeScript.
- Knowledge is hierarchical: books, chapters, chunks, entities, events, locations, facts. It is not a single static summary.
- Answers must be traceable to source text. The deliverable is a knowledge graph; RAG, embeddings, chunk retrieval, and chat are not implemented.
- EPUB uploads use the MD5 hash of the binary as the KOReader document identity.
- Processing is asynchronous through ARQ. The source file is deleted after successful processing; derived chapters and chunks remain.
- Chunk indices are globally monotonic per book. Chunks target 300-500 tokens with 50-100 tokens of overlap, so percentage ranges may overlap.
- The graph is refreshed by reading progress. A sync that advances the stored position makes newly visible knowledge available; a sync with no new data changes nothing.
- Ports and concrete implementations use distinct names. Concrete adapters name their backend, such as `PostgresBookRepository`; ports stay provider-agnostic.
- `api/dependencies.py` is the composition root. Providers return ports and build adapters internally, so routers and use cases never name Postgres or an external vendor.
- Repeated reads on a long-lived session must be refresh-safe. Repositories project fresh dataclasses instead of replaying ORM entities from the identity map.
- Processing status is push-based: the worker publishes each committed transition to Redis `book-status:{book_id}` and `/events` waits for subscription acknowledgement before re-reading the row, so a terminal event cannot be missed. No database polling; heartbeat every 15 seconds; close on `ready`, `failed`, or `partial`.
- `LibraryRepositoryFactory` gives the status stream a short-lived session for authorization and the current status; the stream itself holds no database session.

## Shared Constants

- Book processing statuses have one definition per runtime: `backend/core/domain/status.py` and `frontend/lib/status.ts`. Use cases, repositories, routes, workers, and components import the shared names; they never repeat status strings or status sets.
- Status lifecycle: `pending -> processing -> ready | partial | failed`. Only `partial` and `failed` are retryable, and a retry returns the book to `pending`. The status stream closes on `ready`, `partial`, or `failed`. Graph reads and graph generation are allowed on `ready` or `partial` only.
- Frontend status contract: open the graph on `ready` or `partial`, offer retry on `failed` or `partial`, and keep streaming for `pending` or `processing`.
- Business rules belong in `AGENTS.md` and `MEMORY.md`, not in code comments. Code comments stay limited to what the code cannot express on its own.

## Quality Gates

- Required local checks: `ruff check backend` from the repository root, `npx tsc --noEmit` and `npm run lint` from `frontend`, plus the focused pytest tier for the change.
- Tests assert raw status literals on purpose; production code imports the canonical constants. Do not refactor contract tests to import production constants.
- Generated artifacts stay out of git, including `*.tsbuildinfo`, `.next/`, and tool caches.
- Dependency security is judged with `npm audit --omit=dev`. Dev-only tooling advisories are not runtime exposure and are upgraded with the framework, not forced separately.

## Graph And Anti-Spoiler Boundary

- The graph endpoint takes no position parameter. It reads the caller's `user_books.progress_position` and ownership together, so an unowned book is indistinguishable from an unknown one.
- Do not materialize a graph snapshot at a sync position. Readers rewind; the visible graph must be derived per request from stored identity only.
- `entities.canonical_id` stores identity only. Labels, descriptions, subtypes, aliases, first-seen positions, and mention counts are derived from mentions visible at the requested position.
- Identity resolution deliberately runs over every mention in the book. The result is an id-to-id mapping without text. Never add a position clause to `PostgresKnowledgeRepository.get_entity_candidates`; stored identity must not depend on when the job ran.
- Emit an edge only when both endpoints resolve to a node visible at the current position. Missing endpoints, ambiguous names, and self-references produce no edge.
- `books.graph_revision` changes only when stored resolution changes. Rewinding queues no work because the read already filters.
- Extraction completion queues a first identity resolution pass, so a book opened at position zero still gets merged nodes before any sync.
- Resolution is deterministic first: casefold, strip accents and punctuation, collapse whitespace, then group by normalized name and entity type. Similar-but-unequal names or conflicting types escalate to `EntityResolver`; resolver failure leaves candidates separate.
- `entity_type` is a closed vocabulary: `character`, `enemy`, `artifact`, `organization`, `concept`, plus code-only fallback `other`. `location` and `event` are node types, never entity types. The database `CHECK` enforces this.
- Entity descriptions, subtypes, and aliases are position-derived, never read from a canonical row.
- Events and locations are first-class graph nodes. They are grouped at read time by normalized name; the earliest visible mention supplies the node id.

## LLM Extraction

- Use Gemini through its OpenAI-compatible endpoint. `Settings` defaults and `backend/.env.example` use `gemini-2.5-flash`, `gemini-2.5-flash-lite` as fallback, and `https://generativelanguage.googleapis.com/v1beta/openai/`; `LLM_API_KEY` is the only accepted key variable.
- Free-tier tuning: concurrency 2, 5 requests per minute, batch size 3, 3 attempts, exponential backoff capped at 20 seconds, and a 3600-second job timeout.
- `OpenAIProvider` classifies failures at the HTTP boundary. 401/403/404/422 abort the book; 408/429/5xx, timeouts, transport errors, and malformed responses are transient; other 4xx fail only that chunk. Honor `Retry-After`.
- Gemini's OpenAI-compatible error body can be a one-element array; unwrap it before reading `QuotaFailure`, `RetryInfo`, or `error.code`.
- A 429 becomes `LLMQuotaExhaustedError` only with a per-day quota signal (`PerDay`, daily quota id or message, `insufficient_quota`, or a retry delay over 300 seconds). A per-minute 429 stays transient and does not switch models.
- The provider must return a map keyed by every exact input `chunk_id`, once each, with no unknown ids. This validation prevents a later chunk's knowledge from being stored at an earlier position.
- Only LLM calls run concurrently. Persist sequentially through one `AsyncSession`; SQLAlchemy sessions are not concurrency-safe.
- A book is `ready` only when every chunk was extracted. Zero successful chunks mark it `failed`; partial success marks it `partial`, keeps the EPUB for manual retry, and exposes only the position-filtered graph. A daily-quota failure after successful chunks returns a partial summary; with zero successes it marks `failed`.
- `FailoverLLMProvider` switches only after daily-quota exhaustion, remembers exhausted models until the retry delay or next midnight Pacific Time, and raises when every model is exhausted.
- The worker marks the book `failed` without an ARQ retry on configuration or quota errors before any successful chunk. Partial results are terminal for the current attempt, preserve the EPUB, close the status stream, and can be manually retried; transient failures with no successful chunks still use `max_tries=3`.
- The rate limiter is per worker process and enforces only requests per minute. Multiple workers multiply the rate; daily quotas are handled only by model fallback.
- Real extraction without a valid key marks the book `failed`, not `ready` with empty knowledge.
- CI e2e must not call a real LLM. `docker-compose.e2e.yml` selects `MockLLMProvider` with `LLM_PROVIDER=mock` and `ALLOW_MOCK_LLM=true`; the worker refuses mock mode unless both are set. The mock returns empty results for every requested chunk and no resolution groups.
- The base worker `env_file` is optional so a CI checkout without the gitignored `backend/.env` can start. The normal Compose path still loads it when present.
- Extraction counts are logged; an incomplete reason is stored as the book's processing error.

## Reading Position

- `ReadingPosition` is the single definition of a valid position: finite and within `[0.0, 1.0]`. Repository queries validate through it before building SQL.
- Database `CHECK` constraints enforce the same range for `entities`, `facts`, `events`, `locations`, and `user_books.progress_position`.
- The anti-spoiler filter is `reading_position <= current_position`. It applies to graph reads and knowledge retrieval.
- `PostgresKnowledgeRepository.get_entity_candidates` is the intentional exception: identity resolution needs all mentions because the stored mapping contains no text.

## Ownership And Sessions

- The app works without login. `POST /api/v1/session` creates an anonymous `users` row and returns a JWT; browsers use an httpOnly cookie, other clients use `Authorization: Bearer`.
- Never accept an owner id from the client. `get_current_owner` verifies the token and reads the signed `sub` claim.
- "Anonymous" describes the row, not the transport. A later login claims the same user row, so library data is not migrated.
- Ownership lives in `user_books(owner_id, book_id, added_at, deleted_at)`, not on shared `books`. `books.document_hash` is globally unique, so identical EPUBs are parsed and extracted once.
- Deleting a book is a soft delete: set `user_books.deleted_at` only. Content, knowledge, and covers remain so the book can be restored. Re-uploading restores the same `book_id`.
- The DELETE endpoint returns 204, 409 while processing, and 404 for unknown or unowned books.
- Concurrent identical uploads are arbitrated by `document_hash` with `INSERT ... ON CONFLICT DO NOTHING RETURNING`; the loser deletes its file. The pre-check is only a fast path.
- Re-uploading a `failed` book resets it in place instead of deleting and recreating it.
- `replace_derived_content` deletes knowledge before chunks and chapters because knowledge references chunks.
- Progress belongs to the reader in `user_books`, so two owners of one EPUB can read at different positions without leaking into each other's graph or chat context.
- The SSE bus is keyed by `(owner_id, book_id)` so one token cannot subscribe to another owner's events.
- CORS uses explicit origins because credentialed requests cannot use a wildcard.
- `JWT_SECRET` must be stable and at least 32 bytes outside local development. `SESSION_COOKIE_SECURE` must be `true` over HTTPS.
- `POST /api/v1/session` is rate limited per client IP by Redis. Over-limit returns 429 with `Retry-After`; Redis failure fails open. `TRUST_FORWARDED_FOR` is opt-in for trusted proxies.
- No hard-purge job exists yet. A future purge must wait until no active owner references the book and the retention window has elapsed.

## KOReader

- KOReader syncs through its native Kosync HTTP API.
- The request contains `document` (EPUB hash), `progress` (0.0-1.0), `percentage` (0-100), and `device`.
- The endpoint is `/api/v1/adapters/koreader/sync`.
- Sync requires no login but does require an owner token as `Authorization: Bearer`. The adapter resolves the document hash to `book_id` and verifies ownership before writing progress.
- KOReader details stay in the adapter; the application service receives normalized progress.

## Worker And CI

- `WorkerSettings` must set `redis_settings` from `settings.redis_url`; otherwise ARQ falls back to localhost and never consumes Docker jobs. Only e2e detects this.
- `generate_graph` must stay non-fatal. It logs and returns on failure without mutating progress or graph revision.
- Run pytest from `backend`; it is the import root and Alembic fixtures resolve `alembic.ini` relatively.
- CI must set `COMPOSE_FILE` to absolute paths. Pytest runs from `backend`, and `conftest.py` invokes `docker compose`; relative Compose paths resolve against `backend` and fail there even though the stack was started from the repository root.
- Test tiers follow markers and directories: unmarked unit/contract need no services, `postgres` needs PostgreSQL, and `e2e` needs the Compose stack with `RUN_E2E=1`.
- Service-backed tests self-skip when dependencies are missing, so CI must fail if a `postgres` or `e2e` test is skipped.
- The e2e tier runs on `main` and manual dispatch because it builds and starts the Compose stack.
- `tests/contract/` proves the HTTP contract only. A green contract run is not evidence that persistence works.
- Database cleanup truncates application tables but preserves `alembic_version`; truncating it would make the next run fail on an existing schema.
- E2E cleanup stops the worker and flushes Redis before truncating. A running job holds locks that conflict with `TRUNCATE`; pausing the container is not enough. Truncation sets `lock_timeout` so unexpected lock holders fail loudly.
- Ruff configuration lives in root `pyproject.toml`; the pinned version lives in `backend/requirements-dev.txt`.
