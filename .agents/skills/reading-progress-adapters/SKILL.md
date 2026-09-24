---
name: reading-progress-adapters
description: Design provider-agnostic asynchronous reading-progress synchronization and KOReader adapters.
---

# Reading Progress Adapters

## Boundary

The core domain understands only the normalized value:

```json
{"book_id": "string", "position": 0.0}
```

Do not leak KOReader filenames, `.sdr` paths, SQLite rows, or adapter-specific types into domain entities or use cases.

## KOReader adapter

- Keep KOReader parsing under `backend/adapters/koreader/`.
- Parse `.sdr` folders and SQLite metadata to extract the current reading percentage.
- Resolve the local EPUB filename to the database `book_id`.
- Map the result into the core progress contract and call the existing provider/use-case port.
- Keep I/O asynchronous. Offload CPU-heavy parsing, entity extraction, embedding generation, and similar work to ARQ, Celery, or the repository's queue abstraction.
- Make synchronization idempotent and explicit about malformed, missing, or unmapped metadata.

## Review checklist

Verify the adapter can be replaced without core changes, progress values are validated in `[0.0, 1.0]`, sync endpoints do not perform heavy extraction inline, and failures are observable without corrupting stored progress.
