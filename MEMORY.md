# Project Memory

This file records durable project decisions, product choices, and current state. Repository operating rules belong in `AGENTS.md`.

## Product Decisions

- The backend is API-first so web, mobile, and other clients can consume the same analysis service. The planned web client is Next.js with TypeScript.
- Ebook knowledge is modeled hierarchically as books, chapters, chunks, entities, events, and facts rather than as a single static summary.
- Interactive answers must be traceable back to the source text so a client can open the supporting paragraph.
- Port interfaces and concrete implementations use distinct names. Provider-specific implementations include their backend or provider, such as `PostgresBookRepository`, while generic ports remain provider-agnostic.

## KOReader Integration Decision

- KOReader will synchronize through its native Kosync HTTP API.
- KOReader sends a POST containing `document` (the EPUB hash), `progress` (a float from `0.0` to `1.0`), `percentage` (an integer from `0` to `100`), and `device`.
- The endpoint is versioned at `/api/v1/adapters/koreader/sync`.
- The adapter resolves the Kosync `document` hash to the internal `book_id`, then passes normalized progress to the provider-agnostic application service.

## Current State

- The versioned endpoint, request/response schemas, normalized progress value, port method, and adapter method are now scaffolded.
- The next implementation slice is the hash resolver behind `resolve_book_id()`, backed by the book repository, followed by dependency wiring and focused tests.

## Testing Decision

- Before committing a feature on a feature branch, add and run simple unit tests, integration tests, and end-to-end tests when the feature has an end-to-end surface that warrants them.