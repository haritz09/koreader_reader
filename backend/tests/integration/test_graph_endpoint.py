"""Graph endpoint contract.

These run the real application with in-memory repositories, which verifies the
wiring and the JSON contract. They are not evidence that the SQL filter works;
that is covered by ``test_graph_postgres.py``.
"""

from fastapi.testclient import TestClient

from api.dependencies import get_book_repository, get_graph_repository
from core.domain.entities.graph import BookGraphState, EntityMention, FactLink
from main import app


class StubBookRepository:
    def __init__(
        self,
        progress_position: float = 0.5,
        processing_status: str = "ready",
        graph_revision: int = 2,
    ) -> None:
        self.progress_position = progress_position
        self.processing_status = processing_status
        self.graph_revision = graph_revision

    async def get_graph_state(self, book_id: str) -> BookGraphState | None:
        if book_id != "book-123":
            return None
        return BookGraphState(
            book_id=book_id,
            progress_position=self.progress_position,
            processing_status=self.processing_status,
            graph_revision=self.graph_revision,
        )


class FilteringGraphRepository:
    """Applies the same position filter the SQL implementation applies."""

    def __init__(self) -> None:
        self.mentions = [
            EntityMention(
                entity_id="e1",
                canonical_id="e1",
                name="Alice",
                entity_type="character",
                reading_position=0.1,
            ),
            EntityMention(
                entity_id="e2",
                canonical_id="e1",
                name="Alice",
                entity_type="character",
                reading_position=0.8,
            ),
            EntityMention(
                entity_id="e3",
                canonical_id="e3",
                name="Bob",
                entity_type="character",
                reading_position=0.3,
            ),
            EntityMention(
                entity_id="e4",
                canonical_id="e4",
                name="Carol",
                entity_type="character",
                reading_position=0.9,
            ),
        ]
        self.facts = [
            FactLink(
                fact_id="f1",
                chunk_id="chunk-0",
                statement="Alice knows Bob",
                subject="Alice",
                object="Bob",
                reading_position=0.4,
            ),
            FactLink(
                fact_id="f2",
                chunk_id="chunk-2",
                statement="Alice meets Carol",
                subject="Alice",
                object="Carol",
                reading_position=0.9,
            ),
        ]

    async def get_visible_mentions(
        self, book_id: str, reading_position: float
    ) -> list[EntityMention]:
        return [m for m in self.mentions if m.reading_position <= reading_position]

    async def get_visible_facts(
        self, book_id: str, reading_position: float
    ) -> list[FactLink]:
        return [f for f in self.facts if f.reading_position <= reading_position]

    async def get_revision(self, book_id: str) -> int:
        return 2

    async def delete_by_book(self, book_id: str) -> None:
        raise NotImplementedError


def get_client(book_repository: StubBookRepository) -> TestClient:
    app.dependency_overrides[get_book_repository] = lambda: book_repository
    app.dependency_overrides[get_graph_repository] = lambda: FilteringGraphRepository()
    return TestClient(app)


def fetch(book_repository: StubBookRepository, path: str = "/api/v1/ebooks/book-123/graph"):
    client = get_client(book_repository)
    try:
        return client.get(path)
    finally:
        app.dependency_overrides.clear()


def test_graph_endpoint_returns_nodes_and_edges_at_the_stored_position() -> None:
    response = fetch(StubBookRepository(progress_position=0.5))

    assert response.status_code == 200
    body = response.json()
    assert body["book_id"] == "book-123"
    assert body["position"] == 0.5
    assert body["revision"] == 2
    assert [node["label"] for node in body["nodes"]] == ["Alice", "Bob"]
    assert body["nodes"][0]["mention_count"] == 1
    assert [edge["edge_id"] for edge in body["edges"]] == ["f1"]


def test_graph_endpoint_merges_mentions_of_the_same_entity() -> None:
    response = fetch(StubBookRepository(progress_position=1.0))

    body = response.json()
    assert [node["node_id"] for node in body["nodes"]] == ["e1", "e3", "e4"]
    assert body["nodes"][0]["mention_count"] == 2


def test_graph_endpoint_returns_an_empty_graph_before_any_reading() -> None:
    response = fetch(StubBookRepository(progress_position=0.0))

    body = response.json()
    assert body["nodes"] == []
    assert body["edges"] == []


def test_graph_endpoint_ignores_a_client_supplied_position() -> None:
    response = fetch(StubBookRepository(progress_position=0.5), "/api/v1/ebooks/book-123/graph?position=1.0")

    assert response.status_code == 200
    assert [node["label"] for node in response.json()["nodes"]] == ["Alice", "Bob"]


def test_graph_endpoint_returns_not_found_for_an_unknown_book() -> None:
    response = fetch(StubBookRepository(), "/api/v1/ebooks/missing/graph")

    assert response.status_code == 404


def test_graph_endpoint_conflicts_while_the_book_is_processing() -> None:
    response = fetch(StubBookRepository(processing_status="processing"))

    assert response.status_code == 409
    assert "processing" in response.json()["detail"]


def test_graph_endpoint_conflicts_after_a_failed_upload() -> None:
    response = fetch(StubBookRepository(processing_status="failed"))

    assert response.status_code == 409
