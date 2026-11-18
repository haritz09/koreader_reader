"""Chat request and response schemas."""

from pydantic import BaseModel, ConfigDict, Field

MAX_QUESTION_CHARS = 2000


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class ChatSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    chunk_index: int = Field(ge=0)
    reading_position: float = Field(ge=0.0, le=1.0)
    distance: float
    excerpt: str


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: str
    position: float = Field(ge=0.0, le=1.0)
    model: str
    answer: str
    sources: list[ChatSourceResponse]
