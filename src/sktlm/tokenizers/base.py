"""A small tokenizer contract with explicit surface-span tracking."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


Span = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Encoding:
    """Token IDs, display pieces, and their source character spans."""

    ids: tuple[int, ...]
    pieces: tuple[str, ...]
    spans: tuple[Span, ...]
    byte_spans: tuple[Span, ...] | None = None

    def __post_init__(self) -> None:
        if not (len(self.ids) == len(self.pieces) == len(self.spans)):
            raise ValueError("ids, pieces, and spans must have equal length")
        if self.byte_spans is not None and len(self.byte_spans) != len(self.ids):
            raise ValueError("byte_spans must be absent or match token length")
        if any(start < 0 or end < start for start, end in self.spans):
            raise ValueError("character spans must be ordered non-negative ranges")


class Tokenizer(ABC):
    """Minimal common interface for controlled tokenizer comparisons."""

    name: str
    bos_id: int | None = None
    eos_id: int | None = None

    @property
    @abstractmethod
    def vocab_size(self) -> int:
        """Return the number of IDs accepted by the tokenizer."""

    @abstractmethod
    def encode(self, text: str) -> Encoding:
        """Encode text and retain surface character spans."""

    @abstractmethod
    def decode(self, ids: list[int] | tuple[int, ...]) -> str:
        """Decode token IDs where the tokenizer supports reconstruction."""

    def fingerprint_payload(self) -> dict[str, Any]:
        """Return deterministic tokenizer metadata suitable for hashing."""
        return {"type": self.name, "vocab_size": self.vocab_size}


def span_coverage(text: str, encoding: Encoding) -> float:
    """Return the proportion of source character positions covered by tokens."""
    if not text:
        return 1.0
    covered: set[int] = set()
    for start, end in encoding.spans:
        if end > len(text):
            raise ValueError("token span extends beyond the surface text")
        covered.update(range(start, end))
    return len(covered) / len(text)


def validate_surface_spans(text: str, encoding: Encoding, *, require_full_coverage: bool = True) -> None:
    """Validate bounds and optionally require every surface character to be covered."""
    coverage = span_coverage(text, encoding)
    if require_full_coverage and coverage != 1.0:
        raise ValueError(f"token spans cover {coverage:.2%} of the surface text")
