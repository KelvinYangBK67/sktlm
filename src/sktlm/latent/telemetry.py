"""Low-overhead runtime counters kept separate from scientific artifacts."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


_HISTOGRAM_UPPER_BOUNDS = (0,) + tuple(1 << exponent for exponent in range(25))


@dataclass(slots=True)
class _FixedHistogram:
    count: int = 0
    total: int = 0
    maximum: int = 0
    buckets: Counter[int] = field(default_factory=Counter)

    def observe(self, value: int) -> None:
        if value < 0:
            raise ValueError("histogram observations must be nonnegative")
        self.count += 1
        self.total += value
        self.maximum = max(self.maximum, value)
        bucket = next(
            (
                upper
                for upper in _HISTOGRAM_UPPER_BOUNDS
                if value <= upper
            ),
            -1,
        )
        self.buckets[bucket] += 1

    def merge_payload(self, payload: dict[str, Any]) -> None:
        self.count += int(payload["count"])
        self.total += int(payload["total"])
        self.maximum = max(self.maximum, int(payload["max"]))
        for label, count in payload["buckets"].items():
            bucket = -1 if label == "overflow" else int(label)
            self.buckets[bucket] += int(count)

    def percentile_upper_bound(self, percentile: int) -> int | None:
        if self.count == 0:
            return 0
        target = ((self.count - 1) * percentile + 50) // 100
        seen = 0
        for upper in (*_HISTOGRAM_UPPER_BOUNDS, -1):
            seen += self.buckets[upper]
            if seen > target:
                return None if upper == -1 else upper
        raise AssertionError("histogram counts do not sum to count")

    def payload(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "total": self.total,
            "mean": self.total / max(1, self.count),
            "max": self.maximum,
            "p50_upper_bound": self.percentile_upper_bound(50),
            "p90_upper_bound": self.percentile_upper_bound(90),
            "p95_upper_bound": self.percentile_upper_bound(95),
            "p99_upper_bound": self.percentile_upper_bound(99),
            "buckets": {
                ("overflow" if upper == -1 else str(upper)): count
                for upper, count in sorted(
                    self.buckets.items(),
                    key=lambda item: (
                        item[0] == -1,
                        item[0] if item[0] != -1 else 0,
                    ),
                )
                if count
            },
        }


@dataclass(slots=True)
class RuntimeTelemetry:
    timings: Counter[str] = field(default_factory=Counter)
    counters: Counter[str] = field(default_factory=Counter)
    gauges: dict[str, int | float] = field(default_factory=dict)
    histograms: dict[str, _FixedHistogram] = field(default_factory=dict)

    @staticmethod
    def now() -> float:
        return time.perf_counter()

    def elapsed(self, label: str, started: float) -> None:
        self.timings[label] += time.perf_counter() - started

    def add_seconds(self, label: str, value: float) -> None:
        self.timings[label] += value

    def increment(self, label: str, value: int = 1) -> None:
        self.counters[label] += value

    def maximum(self, label: str, value: int | float) -> None:
        self.gauges[label] = max(value, self.gauges.get(label, value))

    def observe(self, label: str, value: int) -> None:
        self.histograms.setdefault(label, _FixedHistogram()).observe(value)

    def merge_payload(self, payload: dict[str, Any]) -> None:
        self.timings.update(
            {
                label: float(value)
                for label, value in payload.get("timings_seconds", {}).items()
            }
        )
        self.counters.update(
            {
                label: int(value)
                for label, value in payload.get("counters", {}).items()
            }
        )
        for label, value in payload.get("gauges", {}).items():
            self.maximum(label, value)
        for label, value in payload.get("histograms", {}).items():
            self.histograms.setdefault(label, _FixedHistogram()).merge_payload(
                value
            )

    def payload(self) -> dict[str, Any]:
        return {
            "timings_seconds": dict(sorted(self.timings.items())),
            "counters": dict(sorted(self.counters.items())),
            "gauges": dict(sorted(self.gauges.items())),
            "histograms": {
                label: histogram.payload()
                for label, histogram in sorted(self.histograms.items())
            },
        }
