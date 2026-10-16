import pytest

from adapters.auth.jwt_tokens import JwtTokenService


def service(secret: str = "test-secret-that-is-long-enough-32b") -> JwtTokenService:
    return JwtTokenService(secret, algorithm="HS256", ttl_days=1)


def test_a_issued_token_round_trips_the_owner_id() -> None:
    tokens = service()

    token = tokens.issue("owner-1")

    assert tokens.verify(token) == "owner-1"


def test_a_token_signed_with_another_secret_is_rejected() -> None:
    token = service("test-secret-that-is-long-enough-32b").issue("owner-1")

    assert service("other-secret-that-is-long-enough").verify(token) is None


def test_a_tampered_token_is_rejected() -> None:
    token = service().issue("owner-1")

    assert service().verify(f"{token}x") is None


def test_a_non_token_string_is_rejected() -> None:
    assert service().verify("not-a-jwt") is None


def test_an_expired_token_is_rejected() -> None:
    tokens = JwtTokenService(
        "test-secret-that-is-long-enough-32b", algorithm="HS256", ttl_days=-1
    )

    assert tokens.verify(tokens.issue("owner-1")) is None


@pytest.mark.parametrize("owner_id", ["", "owner-1"])
def test_issued_tokens_carry_the_subject(owner_id: str) -> None:
    tokens = service()
    issued = tokens.issue(owner_id)

    assert tokens.verify(issued) == (owner_id or None)
