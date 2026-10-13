# KOReader Knowledge Graph

> **Estado: en desarrollo activo.** Backend implementado y funcional con cobertura completa de tests. Frontend en progreso. Integración con LLM pendiente de API key.

## Descripción

Aplicación que convierte EPUBs en un grafo de conocimiento anti-spoiler. El grafo se actualiza automáticamente con el progreso de lectura sincronizado desde KOReader, mostrando solo entidades, relaciones y eventos que el lector ya ha alcanzado.

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2 |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS, ReactFlow |
| Queue | ARQ (Redis) |
| Database | PostgreSQL 16 |
| Tests | pytest (unit, contract, postgres, e2e), ruff |

## Arquitectura

```
backend/
├── api/            # HTTP routes, schemas Pydantic, dependencies
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

| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/ebooks` | Subir EPUB (async, retorna 202) |
| GET | `/api/v1/ebooks` | Listar libros |
| GET | `/api/v1/ebooks/{id}` | Estado del libro |
| GET | `/api/v1/ebooks/{id}/graph` | Grafo anti-spoiler en posición actual |
| GET | `/api/v1/ebooks/{id}/events` | SSE: estado de procesamiento |
| GET | `/api/v1/ebooks/{id}/position-events` | SSE: cambio de posición de lectura |
| GET | `/api/v1/ebooks/{id}/cover` | Portada del libro |
| POST | `/api/v1/ebooks/{id}/retry` | Reintentar procesamiento (solo failed) |
| POST | `/api/v1/adapters/koreader/sync` | Sincronizar progreso KOReader |

## Decisiones Clave

### Anti-Spoiler
- El grafo se deriva por-request desde menciones visibles (`reading_position <= stored_position`)
- Nunca se materializa un snapshot del grafo completo
- Labels, descripciones, aliases e importancia se derivan de menciones visibles en `GraphAssemblyService`
- Reesceder no filtra — el grafo se encoge naturalmente

### Progreso de Lectura
- KOReader envía POST con hash del documento, progreso float [0,1] y porcentaje
- El backend resuelve el hash → book_id, actualiza posición y encola regeneración de grafo
- El cliente recibe SSE con el cambio de posición y refresca el grafo automáticamente

### Entidad Importance
- 1=protagonista, 2=secundario, 3=terciario (nullable)
- Se deriva como `min()` de las menciones visibles — sube con la trama sin spoilers

## Ejecución Local

```powershell
# Stack completo con Docker
docker compose up -d --build

# Tests (desde backend/)
python -m pytest tests/                    # sin servicios externos
python -m pytest tests/ -m postgres         # con PostgreSQL
$env:RUN_E2E="1"; python -m pytest tests/ -m e2e  # e2e con Compose

# Linter
ruff check .
```

## CI

- **Lint**: ruff en PR y push a main
- **Unit + Contract**: pytest sin servicios
- **PostgreSQL**: pytest con PostgreSQL 16
- **E2E**: solo en main y manual dispatch, construye imagen Compose completo

## Features Pendientes

| Issue | Descripción | Estado |
|-------|-------------|--------|
| #12 | Diseño de UI del grafo: layout, colores, animaciones | Open |
| #6 | Wayfinder: planificación de features futuras | Open |

## Decisions Pendientes

- **LLM**: Sin API key configurada por defecto. El stack funciona pero extrae conocimiento vacío cuando no hay key. Configurar `LLM_API_KEY` para extracción real.
- **Cover extraction**: Implementada en backend (cover_path). Pendiente extracción robusta de portadas de EPUBs reales.
- **Sync manual desde frontend**: El botón de retry está listo. Pendiente UI para sync manual de posición (input de progreso).
