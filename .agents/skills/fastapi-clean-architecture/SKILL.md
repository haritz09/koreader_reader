---
name: fastapi-clean-architecture
description: Build and review the FastAPI backend using Clean Architecture, async SQLAlchemy 2.0, and strict Pydantic v2 JSON contracts.
---

# FastAPI Clean Architecture

## Apply when
Use this skill for API routes, schemas, use cases, services, repositories, persistence models, dependency injection, and backend tests.

## Architecture

- Keep HTTP concerns in `backend/api/routes/` and request/response contracts in `backend/api/schemas/`.
- Keep business rules in application use cases and domain services.
- Keep database access in `backend/db/repositories/`.
- Keep SQLAlchemy and pgvector persistence models in `backend/db/models/`.
- Keep integrations behind ports in `backend/core/ports/` and implementations under `backend/adapters/`.
- Route functions must orchestrate dependencies and call a use case or service; they must not contain SQL or repository query construction.

## API contract

- Use Pydantic v2 models for every request and response. Prefer `ConfigDict` and explicit field types.
- Declare response models on FastAPI endpoints.
- Return typed JSON objects, lists, and primitives only. Do not use HTML or Markdown as the primary payload.
- Preserve stable field names and update tests when contracts change.
- Keep async boundaries genuinely async; do not block the event loop with file, CPU, or synchronous database work.

## Review checklist

Before finishing, verify that the changed code has a clear owning layer, no route-level database access, explicit schemas, awaited async calls, and focused tests for success and failure paths.
