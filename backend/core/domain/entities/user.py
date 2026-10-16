from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    """An owner of a library. Anonymous until the owner claims it with a login."""

    id: str
    is_anonymous: bool
