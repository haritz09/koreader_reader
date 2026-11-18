import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from typing import Any

from fastapi.responses import StreamingResponse

from api.presenters.ebooks import progress_counts
from core.ports.book_status_events import BookStatusEvent

RETRY_FRAME = "retry: 5000\n\n"
KEEP_ALIVE_FRAME = ": keep-alive\n\n"
SSE_MEDIA_TYPE = "text/event-stream"

_SSE_HEADERS = {
	"Cache-Control": "no-cache",
	"Connection": "keep-alive",
}
STATUS_STREAM_HEADERS = {**_SSE_HEADERS, "X-Accel-Buffering": "no"}
POSITION_STREAM_HEADERS = dict(_SSE_HEADERS)


def encode_status_event(event: BookStatusEvent) -> str:
	payload: dict[str, object] = {
		"type": "status",
		"status": event.status,
		"error": event.error,
	}
	chunks_total, chunks_extracted = progress_counts(
		event.chunks_total,
		event.chunks_extracted,
	)
	if chunks_total is not None and chunks_extracted is not None:
		payload["chunks_total"] = chunks_total
		payload["chunks_extracted"] = chunks_extracted
	return _data_frame(payload)


def encode_error_event(message: str) -> str:
	return _data_frame({"type": "error", "message": message})


def encode_position_event(event: dict[str, Any]) -> str:
	return _data_frame(event)


def _data_frame(payload: dict[str, Any]) -> str:
	return f"data: {json.dumps(payload)}\n\n"


async def _status_frames(
	events: AsyncGenerator[BookStatusEvent | None, None],
) -> AsyncIterator[str]:
	async with aclosing(events):
		yield RETRY_FRAME
		async for event in events:
			if event is None:
				yield KEEP_ALIVE_FRAME
				continue
			yield encode_status_event(event)


async def _position_frames(
	events: AsyncGenerator[dict[str, Any], None],
) -> AsyncIterator[str]:
	async with aclosing(events):
		async for event in events:
			yield encode_position_event(event)


async def _single_event_frames(frame: str) -> AsyncIterator[str]:
	yield RETRY_FRAME
	yield frame


def status_stream_response(
	events: AsyncGenerator[BookStatusEvent | None, None],
) -> StreamingResponse:
	return StreamingResponse(
		_status_frames(events),
		media_type=SSE_MEDIA_TYPE,
		headers=STATUS_STREAM_HEADERS,
	)


def position_stream_response(
	events: AsyncGenerator[dict[str, Any], None],
) -> StreamingResponse:
	return StreamingResponse(
		_position_frames(events),
		media_type=SSE_MEDIA_TYPE,
		headers=POSITION_STREAM_HEADERS,
	)


def error_event_response(message: str) -> StreamingResponse:
	return StreamingResponse(
		_single_event_frames(encode_error_event(message)),
		media_type=SSE_MEDIA_TYPE,
		headers=STATUS_STREAM_HEADERS,
	)
