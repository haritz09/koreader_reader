"""Reading progress request and response schemas."""

from pydantic import BaseModel, ConfigDict, Field


class KoreaderSyncRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	document: str = Field(min_length=1)
	progress: float = Field(ge=0.0, le=1.0)
	percentage: int = Field(ge=0, le=100)
	device: str = Field(min_length=1)


class KoreaderSyncResponse(BaseModel):
	book_id: str
	position: float
	device: str
	accepted: bool = True
