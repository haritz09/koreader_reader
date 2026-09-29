# Project Memory

This file records durable project decisions, product choices, and current state. Repository operating rules belong in `AGENTS.md`.

## Product Decisions

- The backend is API-first so web, mobile, and other clients can consume the same analysis service. The planned web client is Next.js with TypeScript.
- Ebook knowledge is modeled hierarchically as books, chapters, chunks, entities, events, and facts rather than as a single static summary.
- Interactive answers must be traceable back to the source text so a client can open the supporting paragraph.
- Port interfaces and concrete implementations use distinct names. Provider-specific implementations include their backend or provider, such as `PostgresBookRepository`, while generic ports remain provider-agnostic.
- EPUB uploads use the MD5 hash of the uploaded binary as the KOReader document identity.
- EPUB processing is asynchronous through ARQ. Uploaded source files are deleted after successful processing, while derived chapters and chunks remain available.
- Chunk indices are globally monotonic per book. Chunks target 300-500 tokens with 50-100 tokens of overlap and percentage ranges may overlap.

## KOReader Integration Decision

- KOReader will synchronize through its native Kosync HTTP API.
- KOReader sends a POST containing `document` (the EPUB hash), `progress` (a float from `0.0` to `1.0`), `percentage` (an integer from `0` to `100`), and `device`.
- The endpoint is versioned at `/api/v1/adapters/koreader/sync`.
- The adapter resolves the Kosync `document` hash to the internal `book_id`, then passes normalized progress to the provider-agnostic application service.

## Continuous Integration

- CI lives in `.github/workflows/ci.yml` and runs ruff plus the pytest suite on every pull request and on pushes to `main`.
- Pytest must be run from the `backend` directory. Tests import top-level project modules such as `core.config` and `main`, and the Alembic fixtures resolve `alembic.ini` by relative path, so `backend` is the import root and the required working directory.
- Tests are tiered by marker. Unmarked tests need no services, `postgres` tests need a real PostgreSQL, and `e2e` tests need the full Docker Compose stack with `RUN_E2E=1`.
- Service-backed tests self-skip when their dependency is unavailable, which can hide regressions. The CI jobs therefore fail when a `postgres` or `e2e` test is skipped instead of executed.
- The `e2e` tier only runs on `main` and on manual dispatch, because it builds the image and starts the whole Compose stack.
- Ruff configuration lives in the root `pyproject.toml` and the pinned version in `backend/requirements-dev.txt`. Alembic migration files are excluded because Alembic regenerates them. `B008` and `UP043` are ignored because FastAPI dependency injection and explicit generator type arguments are intentional.
- An `integration` test means in-process wiring of the real app, not database coverage. Only tests marked `postgres` or `e2e` reach real infrastructure. Do not read a green integration run as evidence that persistence is covered.
- Database-backed test cleanup truncates application tables but deliberately preserves `alembic_version`. Truncating it leaves the schema in place with no recorded migration, so the next `pytest -m postgres` run against a persistent database fails on `relation "books" already exists`.

## Anti-Spoiler Coverage

- `PostgresKnowledgeRepository` is the data-access boundary that enforces `reading_position <= reading_position` for entities, facts, events, and locations.
- Its retrieval queries are covered by `tests/integration/test_knowledge_retrieval_postgres.py`, which drives the real `KnowledgeExtractionService` with a stub LLM over chunks with known `start_pctg`, then asserts through the real repository. Testing the filter alone would not catch a tagging regression that leaks spoilers, so both hops are exercised.
- Boundary cases covered are `0.0`, `1.0`, a position exactly equal to a chunk, an unread book, and cross-book isolation. The two `sources` and `chunk_id` traceability assertions from the skill still have no coverage because the chat and graph routes are stubs that are not registered in the router.
- The skill requires failing closed on an absent or invalid `current_position`, but the repository takes a bare `float` with no range check and the column has no `CHECK` constraint. An out-of-range position is currently accepted silently.

## ARQ Worker Decision

- `WorkerSettings` must set `redis_settings` from `settings.redis_url`. Without it arq falls back to `localhost:6379`, so the worker crashed on startup inside Docker and never consumed a job, while the API correctly enqueued to the `redis` service. Only the `e2e` tier detects this, which is why that tier must not be allowed to skip.

## Current State

- The versioned KOReader sync endpoint and ebook upload endpoint are implemented with unit and integration coverage.
- The upload pipeline has local storage, ARQ queue and worker boundaries, EPUB parsing, chunk persistence, processing status, and a book status endpoint.
- Docker configuration is available for the API, ARQ worker, PostgreSQL, and Redis services.