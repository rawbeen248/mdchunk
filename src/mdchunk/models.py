"""Public data models for mdchunk."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    """Metadata attached to every generated chunk."""

    chunk_id: str
    chunk_index: int
    chunk_type: str
    heading_path: Tuple[str, ...] = ()
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    size: int = 0
    size_metric: str = "characters"
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Chunk:
    """A RAG-ready chunk and its source metadata."""

    text: str
    metadata: ChunkMetadata

    @property
    def heading_path(self) -> Tuple[str, ...]:
        return self.metadata.heading_path
