from fastapi.testclient import TestClient

from adapters.auth.jwt_tokens import JwtTokenService
from api.dependencies import get_current_owner, get_user_repository
from core.config import settings
from core.domain.entities.user import User
from main import app


class FakeUserRepository:
    def __init__(self, user: User | None = None) -> None:
        self.user = user
        self.created = 0

    async def create_anonymous(self) -> User:
        self.created += 1
        self.user = User(id="new-user", is_anonymous=True)
        return self.user

    async def get_by_id(self, user_id: str) -> User | None:
        if self.user is not None and self.user.id == user_id:
            return self.user
        return None


def token_service() -> JwtTokenService:
    return JwtTokenService(
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        ttl_days=settings.jwt_ttl_days,
    )


def test_creating_a_session_returns_a_token_and_sets_an_httponly_cookie() -> None:
    users = FakeUserRepository()
    app.dependency_overrides[get_user_repository] = lambda: users
    client = TestClient(app)

    try:
        response = client.post("/api/v1/session")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == "new-user"
    assert body["is_anonymous"] is True
    assert body["token"]
    assert users.created == 1
    cookie_header = response.headers["set-cookie"]
    assert settings.session_cookie_name in cookie_header
    assert "HttpOnly" in cookie_header


def test_reading_a_session_requires_a_token() -> None:
    app.dependency_overrides.pop(get_current_owner, None)
    client = TestClient(app)

    response = client.get("/api/v1/session")

    assert response.status_code == 401


def test_reading_a_session_with_a_cookie_returns_the_owner() -> None:
    users = FakeUserRepository(User(id="user-1", is_anonymous=True))
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides.pop(get_current_owner, None)
    client = TestClient(app)
    client.cookies.set(settings.session_cookie_name, token_service().issue("user-1"))

    try:
        response = client.get("/api/v1/session")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"user_id": "user-1", "is_anonymous": True}


def test_a_bearer_header_can_replace_the_cookie() -> None:
    users = FakeUserRepository(User(id="user-1", is_anonymous=True))
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides.pop(get_current_owner, None)
    client = TestClient(app)

    try:
        response = client.get(
            "/api/v1/session",
            headers={"Authorization": f"Bearer {token_service().issue('user-1')}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["user_id"] == "user-1"


def test_a_forged_token_is_rejected_before_reaching_the_database() -> None:
    app.dependency_overrides.pop(get_current_owner, None)
    client = TestClient(app)
    client.cookies.set(settings.session_cookie_name, "forged.token.value")

    response = client.get("/api/v1/ebooks")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid session"}


def test_protected_endpoints_require_a_session() -> None:
    app.dependency_overrides.pop(get_current_owner, None)
    client = TestClient(app)

    response = client.get("/api/v1/ebooks")

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing session"}
