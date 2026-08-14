"""Public data models for mdchunk."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    """Metadata attached to every generated chunk."""

    chunk_id: str
    chunk_index: int
    chunk_type: str
    heading_path: tuple[str, ...] = ()
    start_line: int | None = None
    end_line: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    size: int = 0
    size_metric: str = "characters"
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Chunk:
    """A RAG-ready chunk and its source metadata."""

    text: str
    metadata: ChunkMetadata

    @property
    def heading_path(self) -> tuple[str, ...]:
        return self.metadata.heading_path
