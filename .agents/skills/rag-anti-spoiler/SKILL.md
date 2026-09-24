---
name: rag-anti-spoiler
description: Implement and review hierarchical RAG, pgvector retrieval, graph generation, and chat with strict reading-position spoiler protection.
---

# RAG Anti-Spoiler

## Data model

Preserve the hierarchy `Book -> Chapters -> Chunks -> Entities/Facts/Events`. Every chunk, entity, fact, and event must carry `reading_position: float` in the inclusive range `[0.0, 1.0]`.

## Mandatory retrieval invariant

Every query used for chat context, graph generation, entity lookup, fact lookup, or vector retrieval must enforce:

```sql
WHERE reading_position <= :current_position
```

Apply this filter at the repository/query boundary, before results reach the LLM or graph builder. Never rely only on prompt instructions or frontend filtering. Validate `current_position` and fail closed when it is absent or invalid.

## Chat output

All chat endpoint responses must use a typed schema and include `sources`, an array containing the exact `chunk_id` values used to produce the answer. Keep source IDs traceable to retrieved chunks and do not cite inaccessible or post-position chunks.

## Review checklist

Test boundary positions `0.0`, `1.0`, and equal positions; verify future chunks are excluded; verify empty retrieval is handled safely; verify graph and chat paths share the same filter; and verify source IDs match the final retrieved context.
