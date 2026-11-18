"""Presenters for the chat API."""

from api.schemas.chat import ChatResponse, ChatSourceResponse
from rag.domain.chat import ChatAnswer, ChatSource


def chat_response(answer: ChatAnswer) -> ChatResponse:
	return ChatResponse(
		book_id=answer.book_id,
		position=answer.position,
		model=answer.model,
		answer=answer.answer,
		sources=[_source_response(source) for source in answer.sources],
	)


def _source_response(source: ChatSource) -> ChatSourceResponse:
	return ChatSourceResponse(
		chunk_id=source.chunk_id,
		chunk_index=source.chunk_index,
		reading_position=source.reading_position,
		distance=source.distance,
		excerpt=source.excerpt,
	)
