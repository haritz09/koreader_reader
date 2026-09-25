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

## Current State

- The versioned KOReader sync endpoint and ebook upload endpoint are implemented with unit and integration coverage.
- The upload pipeline has local storage, ARQ queue and worker boundaries, EPUB parsing, chunk persistence, processing status, and a book status endpoint.
- Docker configuration is available for the API, ARQ worker, PostgreSQL, and Redis services.

## Testing Decision

- Before committing a feature on a feature branch, add and run simple unit tests, integration tests, and end-to-end tests when the feature has an end-to-end surface that warrants them.