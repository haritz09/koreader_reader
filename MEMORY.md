# Project Memory

This file records durable project decisions, product choices, and current state. Repository operating rules belong in `AGENTS.md`.

## Product Decisions

- The backend is API-first so web, mobile, and other clients can consume the same analysis service. The planned web client is Next.js with TypeScript.
- Ebook knowledge is modeled hierarchically as books, chapters, chunks, entities, events, locations, and facts rather than as a single static summary.
- Interactive answers must be traceable back to the source text so a client can open the supporting paragraph.
- Port interfaces and concrete implementations use distinct names. Provider-specific implementations include their backend or provider, such as `PostgresBookRepository`, while generic ports remain provider-agnostic.
- EPUB uploads use the MD5 hash of the uploaded binary as the KOReader document identity.
- EPUB processing is asynchronous through ARQ. Uploaded source files are deleted after successful processing, while derived chapters and chunks remain available.
- Chunk indices are globally monotonic per book. Chunks target 300-500 tokens with 50-100 tokens of overlap and percentage ranges may overlap.
- The deliverable is a knowledge graph that a client renders visually, not a question-answering feature.
- The graph is refreshed by reading progress. When a KOReader sync advances the stored position, the client refetches the graph and sees newly visible knowledge. A sync that finds no new data changes nothing.

## Graph Generation Decision

- The graph read is the anti-spoiler boundary for this feature. `GET /api/v1/ebooks/{book_id}/graph` takes no position parameter; it resolves the reader's position from `books.progress_position` in storage. 
- Materializing a full graph snapshot at the sync position is forbidden. Readers re-read, so a snapshot built at a previous high-water mark would disclose knowledge the reader has rewound past. The stored mapping is a position-independent identity pointer; the visible graph is derived per request.
- `entities.canonical_id` stores identity only. No canonical display name is stored, because a single stored name would let a later alias label a node the reader has not reached. `GraphAssemblyService` derives every label, `description`, `sub_type`, `aliases`, `first_seen_position`, and `mention_count` from the mentions visible at the requested position.
- Identity resolution runs over every mention in the book, deliberately unfiltered by reading position. The output is an id-to-id mapping containing no text, so resolving ahead of the reader discloses nothing. Do not add a position clause to `PostgresKnowledgeRepository.get_entity_candidates`: `canonical_id` is book-level stored state, and making it position-dependent would make stored identity depend on when the job happened to run rather than on the book. Labels are derived from visible mentions in `GraphAssemblyService`, which is where the boundary holds.
- An edge is emitted only when both endpoints resolve to a node visible at that position. Facts with a single endpoint, unresolvable endpoints, ambiguous names, or self-references produce no edge rather than a dangling reference.
- `books.graph_revision` increments only when the stored resolution actually changes, and is surfaced on the sync response so a client can detect structural change from the call it already makes. Progress-driven content change is signalled by the position, not the revision.
- Rewinding intentionally queues no work. The read filters on every request, so a re-read already yields a smaller graph.
- Entity resolution is deterministic first: names are normalized by casefolding, accent and punctuation stripping, and whitespace collapsing, then grouped by normalized name and entity type. A group whose names are similar but unequal, or whose same name carries conflicting types, is escalated to the `EntityResolver` port. A resolver failure leaves candidates separate rather than merging them incorrectly.
- That grouping keys on `(normalize_name(name), entity_type.casefold())`. `entity_type` is a closed vocabulary: `character`, `enemy`, `artifact`, `organization`, `concept`, plus the code-only fallback `other` for legacy and unparseable values. `EXTRACTABLE_ENTITY_TYPES` is what the prompt asks for and deliberately omits `other`. The column carries a `CHECK` (`ck_entities_entity_type`), so a value outside the vocabulary fails at the database rather than drifting. `location` and `event` are never valid `entity_type` values; they are `node_type` values only.
- Each extracted entity also carries `description`, `sub_type` (free text, e.g. `mistborn`), and `aliases` (per mention, capped at 8 by the provider and 64 in the API schema). All three are position-derived in `GraphAssemblyService`, never read from a canonical row, so a description written later cannot describe a node the reader has not reached.
- `Event` has no `subject` and no `object`. An event is an independent story node, like a place, and is grouped at read time by `normalize_name(name)`; the earliest visible mention supplies the stable node id. Locations are grouped the same way. Both are therefore first-class nodes of `node_type` `event` and `location`.
- `OpenAIProvider` implements both `extract_knowledge` and `resolve_group`. Compose does not pass `LLM_API_KEY`, so the default stack extracts no knowledge and resolves no aliases; the provider now logs a warning instead of silently returning empty results.
- `tests/unit/test_openai_provider_parsing.py` drives `OpenAIProvider._parse_response` directly. That is a deliberate exception to the no-private-mirrors rule: the input is a JSON string and the output a dataclass, with no network involved. `extract_knowledge` itself is covered only on its no-API-key branch, which is the default under Compose. Testing the HTTP call or real model output would need a key and would be non-deterministic, and no such test tier exists.

## Reading Position Validation Decision

- `ReadingPosition` in `core/domain/value_objects/` is the single definition of a valid position: finite, numeric, and within `[0.0, 1.0]`. Every repository query validates through it before building SQL, and `CHECK` constraints enforce the same range in the database for `entities`, `facts`, `events`, `locations`, and `books.progress_position`.
- Before this, the repository accepted any `float`, so a position above `1.0` returned the whole book. The value object plus the constraints are what make the boundary fail closed.

## KOReader Integration Decision

- KOReader will synchronize through its native Kosync HTTP API.
- KOReader sends a POST containing `document` (the EPUB hash), `progress` (a float from `0.0` to `1.0`), `percentage` (an integer from `0` to `100`), and `device`.
- The endpoint is versioned at `/api/v1/adapters/koreader/sync`.
- The adapter resolves the Kosync `document` hash to the internal `book_id`, then passes normalized progress to the provider-agnostic application service.

## Continuous Integration

- CI lives in `.github/workflows/ci.yml` and runs ruff plus the pytest suite on every pull request and on pushes to `main`.
- Pytest must be run from the `backend` directory. Tests import top-level project modules such as `core.config` and `main`, and the Alembic fixtures resolve `alembic.ini` by relative path, so `backend` is the import root and the required working directory.
- Tests are tiered by marker, and the directory matches the tier. Unmarked tests in `tests/unit/` and `tests/contract/` need no services, `tests/integration/` holds the `postgres`-marked tests that need a real PostgreSQL, and `tests/e2e/` holds the `e2e`-marked tests that need the full Docker Compose stack with `RUN_E2E=1`.
- Service-backed tests self-skip when their dependency is unavailable, which can hide regressions. The CI jobs therefore fail when a `postgres` or `e2e` test is skipped instead of executed.
- The `e2e` tier only runs on `main` and on manual dispatch, because it builds the image and starts the whole Compose stack.
- Ruff configuration lives in the root `pyproject.toml` and the pinned version in `backend/requirements-dev.txt`. Alembic migration files are excluded because Alembic regenerates them. `B008` and `UP043` are ignored because FastAPI dependency injection and explicit generator type arguments are intentional.
- `tests/contract/` wires the real FastAPI app in-process with `dependency_overrides` fakes; it proves the HTTP contract, never persistence. Only tests marked `postgres` or `e2e` reach real infrastructure. Do not read a green contract run as evidence that persistence is covered.
- Database-backed test cleanup truncates application tables but deliberately preserves `alembic_version`. Truncating it leaves the schema in place with no recorded migration, so the next `pytest -m postgres` run against a persistent database fails on `relation "books" already exists`.

## Anti-Spoiler Coverage

- Two data-access boundaries enforce `reading_position <= reading_position`. `PostgresGraphRepository.get_visible_mentions` and `get_visible_facts` guard the graph read path, validating the position before building SQL. `PostgresKnowledgeRepository` guards the knowledge retrieval path for entities, facts, events, and locations. The one exception is `PostgresKnowledgeRepository.get_entity_candidates`, which is intentionally unfiltered.
- `PostgresKnowledgeRepository` retrieval queries are covered by `tests/integration/test_knowledge_retrieval_postgres.py`, which drives the real `KnowledgeExtractionService` with a stub LLM over chunks with known `start_pctg`, then asserts through the real repository. Testing the filter alone would not catch a tagging regression that leaks spoilers, so both hops are exercised.
- Boundary cases covered are `0.0`, `1.0`, a position exactly equal to a chunk, an unread book, and cross-book isolation.
- The graph read is covered by `tests/integration/test_graph_postgres.py`.

## ARQ Worker Decision

- `WorkerSettings` must set `redis_settings` from `settings.redis_url`. Without it arq falls back to `localhost:6379`, so the worker crashed on startup inside Docker and never consumed a job, while the API correctly enqueued to the `redis` service. Only the `e2e` tier detects this, which is why that tier must not be allowed to skip.
- `generate_graph` must stay non-fatal. It logs and returns on any failure and never mutates stored progress or the graph revision, so a broken resolver degrades the graph without corrupting the book.

## Current State

- The versioned KOReader sync endpoint, ebook upload endpoint, and graph endpoint are implemented with unit, contract, postgres, and e2e coverage.
- The upload pipeline has local storage, ARQ queue and worker boundaries, EPUB parsing, chunk persistence, processing status, and a book status endpoint.
- Docker configuration is available for the API, ARQ worker, PostgreSQL, and Redis services.
- Entity resolution runs in the background after extraction and on forward progress sync. The graph endpoint is registered at `/api/v1/ebooks/{book_id}/graph`.
- The frontend directory is still empty and intentionally out of scope until the API contract settles.
- `locations` and `events` are read by the graph path: `PostgresGraphRepository.get_visible_mentions` unions `EntityRecord`, `LocationRecord`, and `EventRecord` through the same position filter, so a place or an event becomes a node as soon as it is visible.
