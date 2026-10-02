"""Knowledge graph schemas."""

from pydantic import BaseModel, ConfigDict, Field


class GraphNodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    label: str
    node_type: str
    first_seen_position: float = Field(ge=0.0, le=1.0)
    mention_count: int = Field(ge=1)


class GraphEdgeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str
    source_id: str
    target_id: str
    statement: str
    position: float = Field(ge=0.0, le=1.0)
    chunk_id: str


class GraphResponse(BaseModel):
    """The graph a reader may see, resolved at their stored progress position.

    The position is never taken from the request, so a client cannot ask for a
    graph beyond what it has read.
    """

    model_config = ConfigDict(extra="forbid")

    book_id: str
    position: float = Field(ge=0.0, le=1.0)
    revision: int = Field(ge=0)
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
