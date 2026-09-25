"""Chapter-aware ebook chunking service."""

from dataclasses import dataclass

from core.domain.entities.chapter import Chapter
from core.domain.entities.chunk import Chunk


@dataclass(frozen=True)
class ChunkingConfig:
	max_tokens: int = 400
	overlap_tokens: int = 75


def chunk_chapters(
	chapters: list[Chapter],
	config: ChunkingConfig = ChunkingConfig(),
) -> list[Chunk]:
	if config.max_tokens <= 0 or config.overlap_tokens < 0:
		raise ValueError("Chunk size must be positive and overlap cannot be negative")
	if config.overlap_tokens >= config.max_tokens:
		raise ValueError("Overlap must be smaller than chunk size")

	total_tokens = sum(len(chapter.text.split()) for chapter in chapters)
	if total_tokens == 0:
		return []

	chunks: list[Chunk] = []
	chunk_index = 0
	book_offset = 0
	step = config.max_tokens - config.overlap_tokens

	for chapter in chapters:
		tokens = chapter.text.split()
		for start in range(0, len(tokens), step):
			end = min(start + config.max_tokens, len(tokens))
			chunk_start = book_offset + start
			chunk_end = book_offset + end
			chunks.append(
				Chunk(
					chapter_id=chapter.chapter_id,
					chunk_index=chunk_index,
					text=" ".join(tokens[start:end]),
					start_pctg=chunk_start / total_tokens,
					end_pctg=chunk_end / total_tokens,
				)
			)
			chunk_index += 1
			if end == len(tokens):
				break
		book_offset += len(tokens)

	return chunks
