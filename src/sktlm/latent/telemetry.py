"""Low-overhead runtime counters kept separate from scientific artifacts."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RuntimeTelemetry:
    timings: Counter[str] = field(default_factory=Counter)
    counters: Counter[str] = field(default_factory=Counter)

    @staticmethod
    def now() -> float:
        return time.perf_counter()

    def elapsed(self, label: str, started: float) -> None:
        self.timings[label] += time.perf_counter() - started

    def increment(self, label: str, value: int = 1) -> None:
        self.counters[label] += value

    def payload(self) -> dict[str, Any]:
        return {
            "timings_seconds": dict(sorted(self.timings.items())),
            "counters": dict(sorted(self.counters.items())),
        }
