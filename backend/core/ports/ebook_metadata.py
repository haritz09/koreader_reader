from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EbookMetadata:
    title: str | None = None
    author: str | None = None


class EbookMetadataReader(Protocol):
    async def read_metadata(self, storage_path: str) -> EbookMetadata:
        ...
