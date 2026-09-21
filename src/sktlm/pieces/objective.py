"""Versioned reusable-piece objectives shared by training and diagnostics."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

from sktlm.latent.phonology import PhonologicalForm


S1M2_REUSABLE_PIECES_V1 = "reusable_pieces_v1"
S1M2_REUSABLE_PIECES_V2 = "reusable_pieces_v2"
S1M2_REUSABLE_PIECES_V3 = "reusable_pieces_v3"
S1M2_REUSABLE_PIECE_MODELS = frozenset(
    {S1M2_REUSABLE_PIECES_V2, S1M2_REUSABLE_PIECES_V3}
)


def cross_host_reusable_count(raw_count: float, squared_support_sum: float) -> float:
    """Return ``C - Q/C`` with clamps limited to floating-point roundoff.

    ``C`` is total posterior expected usage over latent phonological wordform
    host types and ``Q`` is the sum of squared, already host-aggregated support.
    """

    raw = float(raw_count)
    squared = float(squared_support_sum)
    if not math.isfinite(raw) or not math.isfinite(squared):
        raise ValueError("C and Q must be finite")
    if raw < 0.0 or squared < 0.0:
        raise ValueError("C and Q must be nonnegative")
    if raw == 0.0:
        if squared != 0.0:
            raise ValueError("Q must be zero when C is zero")
        return 0.0
    reusable = raw - squared / raw
    # In exact arithmetic 0 <= R_cross <= C. Admit only a few ULPs of
    # representational overshoot, rather than turning an invalid Q into a rule.
    tolerance = 8.0 * math.ulp(raw)
    if reusable < -tolerance or reusable > raw + tolerance:
        raise ValueError("C and Q do not define valid cross-host moments")
    return min(raw, max(0.0, reusable))


def cross_host_support_moments(
    support: Iterable[tuple[PhonologicalForm, float]],
) -> tuple[float, float, float, float]:
    """Aggregate occurrence support by host, then return ``C, Q, M, R``."""

    by_host: dict[PhonologicalForm, float] = defaultdict(float)
    for host, value in support:
        amount = float(value)
        if not math.isfinite(amount) or amount < 0.0:
            raise ValueError("host support must be finite and nonnegative")
        by_host[host] += amount
    raw = sum(by_host.values())
    squared = sum(value * value for value in by_host.values())
    maximum = max(by_host.values(), default=0.0)
    return raw, squared, maximum, cross_host_reusable_count(raw, squared)
