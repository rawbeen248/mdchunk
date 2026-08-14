"""Lightweight, structure-aware Markdown chunking for RAG."""

from .chunker import (
    ChunkerConfig,
    MarkdownChunker,
    chunk_markdown,
)
from .metrics import CallableSizeMetric, CharacterSizeMetric, SizeMetric, WordSizeMetric
from .models import Chunk, ChunkMetadata

__all__ = [
    "CallableSizeMetric",
    "CharacterSizeMetric",
    "Chunk",
    "ChunkMetadata",
    "ChunkerConfig",
    "MarkdownChunker",
    "SizeMetric",
    "WordSizeMetric",
    "chunk_markdown",
]

__version__ = "0.1.1"
