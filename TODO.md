# Ebook Upload And Processing Plan

This plan covers the upload flow required before KOReader progress synchronization can use the ebook content.

## Concrete Decisions

- KOReader compatibility: calculate and store the MD5 hash of the uploaded EPUB binary. The implementation must verify this against a real KOReader-generated document hash fixture.
- Original EPUB retention: delete the stored EPUB after successful processing; retain processing metadata and derived content.
- Chunk ordering: `chunk_index` is globally monotonic within a book, not reset per chapter.
- Chunk sizing: target 300 to 500 tokens with 50 to 100 tokens of overlap, with configuration exposed for later tuning.
- Progress during processing: accept and store the latest progress on the book even while processing. Do not run background RAG or entity extraction until the book reaches `ready`.
- Development infrastructure: Redis will be started locally by the developer with Docker for ARQ testing.

## Target Flow

```text
POST /api/v1/ebooks
    -> validate EPUB and compute the KOReader-compatible document hash
    -> create book record with processing status = pending
    -> persist the original EPUB in durable storage
    -> enqueue ARQ job with book_id and stored-file reference
    -> return book_id, document_hash, and processing status

ARQ job
    -> parse EPUB into ordered chapters and text
    -> split text into overlapping chunks
    -> calculate start_pctg, end_pctg, and chunk_index
    -> persist chunks idempotently
    -> mark book ready or failed

KOReader Kosync POST
    -> resolve document hash to book_id
    -> update reading position
    -> retrieve only chunks allowed by the current position
```

## Important Decisions

### 1. Confirm the Kosync hash algorithm first

The upload endpoint must generate the same `document` hash that KOReader sends. A generic SHA-256 or MD5 of the complete EPUB is not acceptable unless it matches KOReader's implementation.

Before coding the upload contract:

- Inspect the KOReader Kosync implementation or protocol documentation.
- Create a fixture EPUB and record its KOReader document hash.
- Verify that the backend computes the identical value.
- Reject or quarantine uploads whose hash cannot be calculated consistently.

### 2. Separate upload from processing

The HTTP handler must not parse the EPUB or create chunks inline. It should only validate the upload, persist the file and book metadata, and enqueue a job.

The ARQ job should receive stable references such as `book_id` and `storage_key`, never a large byte payload. The original EPUB must remain available until processing succeeds and any configured retention policy permits deletion.

### 3. Use explicit processing states

Add a status lifecycle such as:

```text
pending -> processing -> ready
                    \-> failed
```

Record failure information without exposing internal stack traces through the API. Repeated submissions of the same document hash should be idempotent and must not create duplicate books or duplicate chunks.

### 4. Store chunk positions as ranges

Each chunk should include:

- `book_id`
- `chapter_id` or an equivalent chapter reference
- `chunk_index` with a deterministic order within the book
- `text`
- `start_pctg` in `[0.0, 1.0]`
- `end_pctg` in `[0.0, 1.0]`

Percentages should be derived from stable source offsets, preferably normalized text offsets across the ordered book content. The exact mapping from EPUB locations to reading percentage must be documented and tested because KOReader progress is not necessarily a character offset.

### 5. Overlap chunks deliberately

Use a target chunk size and an overlap size measured in the same unit used by the splitter, preferably tokens or normalized characters. Prefer breaking at paragraph or sentence boundaries near the target size.

The end of one chunk should overlap the start of the next by a fixed amount. Therefore, adjacent ranges may overlap:

```text
chunk 0: start_pctg=0.000, end_pctg=0.120
chunk 1: start_pctg=0.105, end_pctg=0.225
```

Do not deduplicate the overlap during retrieval; the overlap preserves context. Deduplicate chunk IDs after retrieval if the same chunk is selected more than once.

## Implementation Steps

1. Confirm the KOReader hash algorithm and add a real fixture containing an EPUB and its expected `document` hash.
2. Define domain objects and ports for books, stored ebook content, chapters, chunks, and processing jobs.
3. Extend the persistence model with book identity/hash, processing status, storage reference, chapters, and chunks. Add constraints for unique document hashes and deterministic chunk ordering.
4. Define Pydantic upload and status response schemas. Include `book_id`, `document_hash`, and processing status; do not return the EPUB contents.
5. Implement the ebook storage adapter. Keep filesystem/object-storage details outside the use case and return a stable storage reference.
6. Implement the upload use case: validate EPUB type and size, compute the compatible hash, create or reuse the book, store the file, and enqueue processing.
7. Add `POST /api/v1/ebooks` and a status endpoint such as `GET /api/v1/ebooks/{book_id}`. Keep both handlers thin.
8. Implement EPUB parsing into ordered chapters and normalized text through the existing parser port.
9. Implement a pure chunking service with configurable chunk size, overlap, boundary handling, `chunk_index`, and percentage range calculation.
10. Implement the ARQ job. Make it retryable and idempotent: replace or upsert chunks for one book only after parsing succeeds, then update the processing status.
11. Wire ARQ configuration and worker startup. Verify Redis failures produce an observable failed or retrying state rather than a falsely ready book.
12. Connect the KOReader hash resolver to the uploaded book records and reject progress for books that are not ready for analysis.
13. Add behavior-first unit tests for hash compatibility, validation, chunk boundaries, overlap, percentage monotonicity, duplicate uploads, and job idempotency.
14. Add integration tests for upload responses, persistence, status transitions, and the versioned KOReader sync flow.
15. Add an end-to-end test with a real EPUB fixture and an in-memory or test PostgreSQL/Redis setup when the infrastructure fixtures exist.
16. Run focused tests first, then the complete backend suite, and update `MEMORY.md` only for decisions that should remain stable.
17. Create `Dockerfile` and `docker-compose.yml` for the API, worker, and local Redis development services.