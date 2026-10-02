"""Entity resolver port for cross-chunk identity grouping."""

from collections.abc import Sequence
from typing import Protocol

from core.domain.entities.graph import EntityCandidate


class EntityResolver(Protocol):
    """Decides which entity mentions refer to the same thing.

    Deterministic name matching runs first and resolves most mentions. This port
    exists for the remainder, where names are similar but not equal and only a
    language model can tell an alias from a different character. It is separate
    from ``LLMProvider`` so that knowledge extraction stays the only concern
    coupled to the knowledge domain.
    """

    async def resolve_group(
        self, candidates: Sequence[EntityCandidate]
    ) -> list[list[str]]: ...
