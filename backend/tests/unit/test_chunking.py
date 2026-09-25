import pytest

from core.domain.entities.chapter import Chapter
from core.services.chunking import ChunkingConfig, chunk_chapters


def test_chunking_uses_global_indexes_and_overlapping_ranges() -> None:
    chapters = [
        Chapter("chapter-1", "One", "one two three four five six", 0),
        Chapter("chapter-2", "Two", "seven eight nine ten eleven twelve", 1),
    ]

    chunks = chunk_chapters(
        chapters,
        ChunkingConfig(max_tokens=4, overlap_tokens=2),
    )

    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2, 3]
    assert chunks[0].end_pctg > chunks[1].start_pctg
    assert all(0.0 <= chunk.start_pctg <= chunk.end_pctg <= 1.0 for chunk in chunks)
    assert all(
        chunks[index].start_pctg <= chunks[index + 1].start_pctg
        for index in range(len(chunks) - 1)
    )


def test_chunking_rejects_overlap_equal_to_chunk_size() -> None:
    with pytest.raises(ValueError):
        chunk_chapters(
            [Chapter("chapter-1", "One", "one two", 0)],
            ChunkingConfig(max_tokens=2, overlap_tokens=2),
        )