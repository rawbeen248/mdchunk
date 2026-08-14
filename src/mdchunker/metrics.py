"""Chunk-size metrics.

The core package deliberately does not depend on a tokenizer. A custom metric
can be supplied when model-specific token budgets are required.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable


class SizeMetric(ABC):
    """Interface used by the chunker to measure text."""

    name = "custom"

    @abstractmethod
    def measure(self, text: str) -> int:
        """Return the size of *text* according to this metric."""


class CharacterSizeMetric(SizeMetric):
    name = "characters"

    def measure(self, text: str) -> int:
        return len(text)


class WordSizeMetric(SizeMetric):
    name = "words"

    def measure(self, text: str) -> int:
        return len(text.split())


class CallableSizeMetric(SizeMetric):
    """Adapt a callable such as a tokenizer length function."""

    def __init__(self, function: Callable[[str], int], name: str = "custom") -> None:
        self._function = function
        self.name = name

    def measure(self, text: str) -> int:
        return int(self._function(text))
