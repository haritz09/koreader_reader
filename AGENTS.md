# Project Agent Instructions

The durable project decisions are recorded in [MEMORY.md](MEMORY.md). Update it when an architectural or integration decision is made that future work must preserve.

## Scope
These instructions apply to the entire repository. Read the relevant skill before changing code:

- `.agents/skills/fastapi-clean-architecture/SKILL.md`
- `.agents/skills/rag-anti-spoiler/SKILL.md`
- `.agents/skills/reading-progress-adapters/SKILL.md`

## Non-negotiable project rules

- Preserve Clean Architecture boundaries: HTTP routers, application services/use cases, repositories, and persistence models remain separate.
- Keep FastAPI handlers thin. Database access belongs in repositories, never directly in route functions.
- Use Pydantic v2 schemas for every API request and response, with explicit types and JSON-serializable payloads.
- Treat `reading_position` as a security boundary. Any retrieval of chunks, entities, facts, or events for chat or graph generation must filter by `reading_position <= current_position`.
- Never expose post-position context to an LLM.
- Chat responses must include a typed `sources` array with the exact `chunk_id` values used for the answer.
- Keep the core domain provider-agnostic. KOReader details belong only in the adapter layer.
- Progress synchronization must be asynchronous and expensive extraction work must run in a background queue.

## Change workflow

1. Locate the owning layer before editing.
2. Reuse existing ports, schemas, repositories, and providers before adding abstractions.
3. Add or update focused tests for changed behavior, especially spoiler filtering and API contracts.
4. Run the narrowest relevant test or type check, then the broader suite when practical.
5. Do not weaken anti-spoiler filtering to make a test or query pass.

Tests must be behavior-first: derive cases from the feature's public contract and realistic failure modes, not from the current implementation structure. Do not add tests merely to mirror private methods or make coverage numbers increase.

## Definition of done

A change is complete only when its layer boundaries are preserved, typed contracts remain explicit, spoiler filtering is enforced at the data-access boundary, and focused validation passes.
