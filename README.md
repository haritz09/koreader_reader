# KOReader Knowledge Graph

> **Status: active development.** Backend implemented and functional with full test coverage. Frontend in progress. LLM integration pending API key.

## Description

Application that converts EPUBs into an anti-spoiler knowledge graph. The graph updates automatically with reading progress synced from KOReader, showing only entities, relations, and events the reader has already reached.

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2 |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS, ReactFlow |
| Queue | ARQ (Redis) |
| Database | PostgreSQL 16 |
| Tests | pytest (unit, contract, postgres, e2e), ruff |

## Architecture

```
backend/
├── api/            # HTTP routes, Pydantic schemas, dependencies
├── core/           # Domain entities, ports, application use cases
├── adapters/       # LLM, storage, queue implementations
├── db/             # SQLAlchemy models, repositories, migrations
├── workers/        # ARQ worker (process_ebook, generate_graph)
└── tests/          # Tiered: unit, contract, postgres, e2e

frontend/
├── app/            # Next.js App Router pages
├── components/     # React components (graph-view, book-grid, etc.)
├── hooks/          # Custom hooks (useGraphData)
├── lib/            # API client functions
└── types/          # TypeScript interfaces from Pydantic schemas
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/session` | Start an anonymous session (sets httpOnly cookie, returns a bearer token) |
| GET | `/api/v1/session` | Current identity and whether it is anonymous |
| POST | `/api/v1/ebooks` | Upload EPUB to the caller's library (async, returns 202) |
| GET | `/api/v1/ebooks` | List the caller's books |
| GET | `/api/v1/ebooks/{id}` | Book status |
| DELETE | `/api/v1/ebooks/{id}` | Remove a book from the caller's library (204; 409 while processing) |
| GET | `/api/v1/ebooks/{id}/graph` | Anti-spoiler graph at current position |
| GET | `/api/v1/ebooks/{id}/events` | SSE: processing status |
| GET | `/api/v1/ebooks/{id}/position-events` | SSE: reading position change |
| GET | `/api/v1/ebooks/{id}/cover` | Book cover |
| POST | `/api/v1/ebooks/{id}/retry` | Retry processing (failed only) |
| POST | `/api/v1/adapters/koreader/sync` | Sync KOReader progress |

Every `/ebooks` and `/adapters` route requires a session. The browser sends the
httpOnly cookie; a device without a browser, such as KOReader, sends the token as
`Authorization: Bearer <token>`.

## Key Decisions

### Identity and Library
- No login required. `POST /api/v1/session` creates an anonymous owner and returns a JWT; a later login claims the same row, so nothing is migrated.

### Anti-Spoiler
- Graph is derived per-request from visible mentions (`reading_position <= stored_position`)
- Full graph snapshots are never materialized
- Labels, descriptions, aliases, and importance are derived from visible mentions in `GraphAssemblyService`
- Rewinding does not filter — the graph shrinks naturally

### Reading Progress
- KOReader sends POST with document hash, progress float [0,1], and percentage
- Backend resolves hash → book_id, updates position, and enqueues graph regeneration
- Client receives SSE with position change and refreshes graph automatically

### Entity Importance
- 1=protagonist, 2=secondary, 3=tertiary (nullable)
- Derived as `min()` of visible mentions — rises with the plot without spoilers

## Local Execution

```powershell
# Full stack with Docker
docker compose up -d --build

# Tests (from backend/)
python -m pytest tests/                    # without external services
python -m pytest tests/ -m postgres         # with PostgreSQL
$env:RUN_E2E="1"; python -m pytest tests/ -m e2e  # e2e with Compose

# Linter
ruff check .
```

## CI

- **Lint**: ruff on PR and push to main
- **Unit + Contract**: pytest without services
- **PostgreSQL**: pytest with PostgreSQL 16
- **E2E**: only on main and manual dispatch, builds full Compose image
