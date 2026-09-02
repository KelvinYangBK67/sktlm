"""Bounded post-hoc archival reduction for completed unrestricted S1M1 cells.

This module is deliberately separate from the frozen six-representation gate.
It validates the same retained collections, reads them locally, and never
mutates source artifacts.
"""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sktlm.latent.frontend import parse_surface

from .six_representation_gate import (
    MASS_THRESHOLDS,
    GateValidationError,
    LoadedCell,
    _file_sha256,
    _load_cell,
    _parse_manifest,
    _validate_cross_cell_contract,
)

SCHEMA_VERSION = "sktlm-s1m1-archival-reduction/v1"
QUANTILES = (0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99)
TOP_MASS_K = (10, 100, 1_000, 10_000, 100_000, 1_000_000)
PAIR_TOP_K = (100, 1_000, 10_000)
LENGTH_MASS_THRESHOLDS = (8, 16, 32, 64)
REUSE_THRESHOLDS = (2, 5, 10)
CONFIDENCE_THRESHOLDS = (0.5, 0.9, 0.95, 0.99)
MINHASH_SIZE = 2_048
EVIDENCE_LIMIT = 12
SOURCE_FILES = (
    "config.json",
    "checkpoint.json",
    "provenance.json",
    "iteration_metrics.json",
    "summary.json",
    "timing_metrics.json",
    "analyses.jsonl",
    "boundary_posteriors.jsonl",
    "latent_lexicon.tsv",
    "rule_usage.tsv",
    "inspection_report.md",
)


def _number(value: object, label: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise GateValidationError((f"{label} must be numeric",))
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise GateValidationError((f"{label} must be numeric",)) from exc
    if not math.isfinite(result):
        raise GateValidationError((f"{label} must be finite",))
    if nonnegative and result < 0.0:
        raise GateValidationError((f"{label} must be nonnegative",))
    return result


def _integer(value: object, label: str, *, nonnegative: bool = True) -> int:
    number = _number(value, label, nonnegative=nonnegative)
    integer = int(number)
    if number != integer:
        raise GateValidationError((f"{label} must be an integer",))
    return integer


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateValidationError((f"{label} must be a JSON object",))
    return value


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise GateValidationError((f"{label} must be a JSON array",))
    return value


def _required(row: Mapping[str, Any], names: Iterable[str], label: str) -> None:
    missing = sorted(name for name in names if name not in row)
    if missing:
        raise GateValidationError((f"{label} is missing fields: {missing}",))


def _ratio(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0.0 else numerator / denominator


def _relative_change(current: float, previous: float) -> float | None:
    return None if previous == 0.0 else (current - previous) / abs(previous)


def _quantile_name(value: float) -> str:
    return f"q{value * 100:g}"


@dataclass(slots=True)
class NumericSummary:
    """Constant-domain-memory deterministic log2 histogram.

    Quantiles are bin-midpoint estimates with 1/8-octave bins. Counts, mean,
    minimum, and maximum remain exact up to ordinary floating-point summation.
    """

    count: int = 0
    total: float = 0.0
    compensation: float = 0.0
    minimum: float = math.inf
    maximum: float = -math.inf
    buckets: Counter[int] = field(default_factory=Counter)

    _ZERO_BUCKET = -100_000
    _BINS_PER_OCTAVE = 8

    def add(self, value: object, label: str = "value") -> float:
        number = _number(value, label, nonnegative=True)
        adjusted = number - self.compensation
        updated = self.total + adjusted
        self.compensation = (updated - self.total) - adjusted
        self.total = updated
        self.count += 1
        self.minimum = min(self.minimum, number)
        self.maximum = max(self.maximum, number)
        bucket = (
            self._ZERO_BUCKET
            if number == 0.0
            else math.floor(math.log2(number) * self._BINS_PER_OCTAVE)
        )
        self.buckets[bucket] += 1
        return number

    def quantile(self, probability: float) -> float | None:
        if self.count == 0:
            return None
        target = max(1, math.ceil(probability * self.count))
        seen = 0
        for bucket, bucket_count in sorted(self.buckets.items()):
            seen += bucket_count
            if seen >= target:
                if bucket == self._ZERO_BUCKET:
                    return 0.0
                return 2.0 ** ((bucket + 0.5) / self._BINS_PER_OCTAVE)
        raise AssertionError("histogram quantile target was not reached")

    def payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "count": self.count,
            "mean": None if self.count == 0 else self.total / self.count,
            "minimum": None if self.count == 0 else self.minimum,
            "maximum": None if self.count == 0 else self.maximum,
            "quantile_method": "deterministic_log2_histogram_1/8_octave_midpoint",
        }
        result.update({_quantile_name(q): self.quantile(q) for q in QUANTILES})
        return result


@dataclass(slots=True)
class OnlinePair:
    count: int = 0
    mean_x: float = 0.0
    mean_y: float = 0.0
    sum_xx: float = 0.0
    sum_yy: float = 0.0
    sum_xy: float = 0.0

    def add(self, x: float, y: float) -> None:
        self.count += 1
        dx = x - self.mean_x
        self.mean_x += dx / self.count
        dy = y - self.mean_y
        self.mean_y += dy / self.count
        self.sum_xx += dx * (x - self.mean_x)
        self.sum_yy += dy * (y - self.mean_y)
        self.sum_xy += dx * (y - self.mean_y)

    def pearson(self) -> float | None:
        denominator = math.sqrt(self.sum_xx * self.sum_yy)
        return None if self.count < 2 or denominator == 0.0 else self.sum_xy / denominator


@dataclass(slots=True)
class TopReservoir:
    category: str
    limit: int = EVIDENCE_LIMIT
    heap: list[tuple[float, str, dict[str, Any]]] = field(default_factory=list)

    def add(self, score: float, source_id: str, payload: dict[str, Any]) -> None:
        item = (float(score), source_id, payload)
        if len(self.heap) < self.limit:
            heapq.heappush(self.heap, item)
        elif item[:2] > self.heap[0][:2]:
            heapq.heapreplace(self.heap, item)

    def rows(self, cell_id: str) -> list[dict[str, Any]]:
        return [
            {
                "cell_id": cell_id,
                "category": self.category,
                "source_id": source_id,
                "selection_score": score,
                **payload,
            }
            for score, source_id, payload in sorted(self.heap, reverse=True)
        ]


@dataclass(slots=True)
class HashReservoir:
    category: str
    limit: int = EVIDENCE_LIMIT
    heap: list[tuple[int, str, dict[str, Any]]] = field(default_factory=list)

    def add(self, source_id: str, payload: dict[str, Any]) -> None:
        digest = int.from_bytes(
            hashlib.sha256(source_id.encode("utf-8")).digest()[:8], "big"
        )
        item = (-digest, source_id, payload)
        if len(self.heap) < self.limit:
            heapq.heappush(self.heap, item)
        elif item[:2] > self.heap[0][:2]:
            heapq.heapreplace(self.heap, item)

    def rows(self, cell_id: str) -> list[dict[str, Any]]:
        return [
            {
                "cell_id": cell_id,
                "category": self.category,
                "source_id": source_id,
                "selection_hash_u64": -negative_digest,
                **payload,
            }
            for negative_digest, source_id, payload in sorted(
                self.heap, key=lambda item: (-item[0], item[1])
            )
        ]


@dataclass(slots=True)
class BottomKSketch:
    limit: int = MINHASH_SIZE
    heap: list[int] = field(default_factory=list)

    def add(self, key: str) -> None:
        digest = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
        item = -digest
        if len(self.heap) < self.limit:
            heapq.heappush(self.heap, item)
        elif item > self.heap[0]:
            heapq.heapreplace(self.heap, item)

    def values(self) -> frozenset[int]:
        return frozenset(-item for item in self.heap)


def _minhash_jaccard(left: BottomKSketch, right: BottomKSketch) -> float | None:
    a, b = left.values(), right.values()
    if not a and not b:
        return None
    union = a | b
    cutoff = sorted(union)[: min(MINHASH_SIZE, len(union))]
    if not cutoff:
        return None
    return sum(value in a and value in b for value in cutoff) / len(cutoff)


def _weighted_quantile(distribution: Mapping[int, float], probability: float) -> float | None:
    total = sum(distribution.values())
    if total <= 0.0:
        return None
    target = probability * total
    cumulative = 0.0
    for value, weight in sorted(distribution.items()):
        cumulative += weight
        if cumulative >= target:
            return float(value)
    return float(max(distribution))


def _distribution_row(
    cell_id: str, family: str, metric: str, summary: NumericSummary
) -> dict[str, Any]:
    return {"cell_id": cell_id, "family": family, "metric": metric, **summary.payload()}


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateValidationError((f"{label} is unreadable JSON: {path}: {exc}",)) from exc


def _relative_path(path: Path, base: Path) -> str:
    return os.path.relpath(path.resolve(), base.resolve()).replace("\\", "/")


def _count_bin(value: float) -> str:
    bounds = (0.01, 0.1, 1.0, 2.0, 5.0, 10.0, 100.0, 1_000.0)
    lower = 0.0
    for upper in bounds:
        if value <= upper:
            return f"({lower:g},{upper:g}]"
        lower = upper
    return "(1000,inf)"


def _length_stratum(length: int) -> str:
    for lower, upper in ((1, 4), (5, 8), (9, 16), (17, 32), (33, 64)):
        if lower <= length <= upper:
            return f"{lower}-{upper}"
    return "65+"


@dataclass(slots=True)
class LexiconReduction:
    row_count: int
    distribution_rows: list[dict[str, Any]]
    length_rows: list[dict[str, Any]]
    reuse_rows: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    top_order: tuple[str, ...]
    top_weights: dict[str, float]
    mass_sketches: dict[str, BottomKSketch]


def _reduce_lexicon(cell: LoadedCell) -> LexiconReduction:
    path = cell.spec.run_dir / "latent_lexicon.tsv"
    complexity = _object(cell.summary.get("complexity"), f"{cell.spec.cell_id} complexity")
    declared_types = _integer(
        complexity.get("active_lexical_types"),
        f"{cell.spec.cell_id} active_lexical_types",
    )
    declared_total = _number(
        complexity.get("expected_lexical_tokens"),
        f"{cell.spec.cell_id} expected_lexical_tokens",
        nonnegative=True,
    )
    if declared_types <= 0 or declared_total <= 0.0:
        raise GateValidationError((f"{cell.spec.cell_id}: lexicon must have positive support",))
    low_threshold = _number(
        complexity.get("low_count_threshold"),
        f"{cell.spec.cell_id} low_count_threshold",
        nonnegative=True,
    )

    count_summary = NumericSummary()
    length_type: Counter[int] = Counter()
    length_mass: Counter[int] = Counter()
    count_bins: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    reuse: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    binned_relationships: dict[str, list[float]] = defaultdict(
        lambda: [0.0, 0.0, 0.0, 0.0]
    )
    pairs = {
        "expected_count__phoneme_length": OnlinePair(),
        "expected_count__contexts": OnlinePair(),
        "expected_count__surface_variants": OnlinePair(),
        "phoneme_length__contexts": OnlinePair(),
        "phoneme_length__surface_variants": OnlinePair(),
        "contexts__surface_variants": OnlinePair(),
    }
    reservoirs = {
        "longest_lexical_forms": TopReservoir("longest_lexical_forms"),
        "high_mass_long_forms": TopReservoir("high_mass_long_forms"),
        "high_context_forms": TopReservoir("high_context_forms"),
        "high_surface_variant_forms": TopReservoir("high_surface_variant_forms"),
        "low_count_forms": TopReservoir("low_count_forms"),
    }
    top_order: list[str] = []
    top_weights: dict[str, float] = {}
    mass_sketches = {
        f"{threshold * 100:g}%": BottomKSketch() for threshold in MASS_THRESHOLDS
    }
    support: dict[str, int] = {}
    top_mass_at: dict[int, float] = {}
    total = 0.0
    total_compensation = 0.0
    count_log_count = 0.0
    count_square = 0.0
    rank_weighted = 0.0
    previous_count = math.inf
    previous_key = ""
    row_count = 0
    high_single_threshold = max(10.0, low_threshold * 10.0)

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {
            "form_key",
            "phoneme_ids",
            "expected_count",
            "probability",
            "number_of_surface_variants",
            "number_of_contexts",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise GateValidationError(
                (f"{cell.spec.cell_id}: latent lexicon header lacks {sorted(required)}",)
            )
        for line_number, row in enumerate(reader, start=2):
            row_count += 1
            label = f"{path}:{line_number}"
            key = row.get("form_key", "")
            if not key:
                raise GateValidationError((f"{label}: form_key must be nonempty",))
            count = _number(row.get("expected_count"), f"{label} expected_count", nonnegative=True)
            _number(row.get("probability"), f"{label} probability", nonnegative=True)
            variants = _integer(
                row.get("number_of_surface_variants"), f"{label} surface variants"
            )
            contexts = _integer(row.get("number_of_contexts"), f"{label} contexts")
            phoneme_ids = row.get("phoneme_ids", "").split()
            if not phoneme_ids:
                raise GateValidationError((f"{label}: phoneme_ids must be nonempty",))
            length = len(phoneme_ids)
            if count > previous_count or (
                count == previous_count and previous_key and key < previous_key
            ):
                raise GateValidationError(
                    (
                        f"{cell.spec.cell_id}: latent lexicon is not sorted by "
                        f"expected_count DESC, form_key ASC at line {line_number}",
                    )
                )
            previous_count, previous_key = count, key

            adjusted = count - total_compensation
            updated = total + adjusted
            total_compensation = (updated - total) - adjusted
            total = updated
            count_summary.add(count, f"{label} expected_count")
            count_log_count += 0.0 if count == 0.0 else count * math.log(count)
            count_square += count * count
            rank_weighted += (declared_types + 1 - row_count) * count
            length_type[length] += 1
            length_mass[length] += count
            bin_name = _count_bin(count)
            count_bins[bin_name][0] += 1
            count_bins[bin_name][1] += count
            rel = binned_relationships[bin_name]
            rel[0] += 1
            rel[1] += length
            rel[2] += contexts
            rel[3] += variants

            for threshold in REUSE_THRESHOLDS:
                if contexts >= threshold:
                    values = reuse[f"contexts>={threshold}"]
                    values[0] += 1
                    values[1] += count
            if variants >= 2:
                values = reuse["surface_variants>=2"]
                values[0] += 1
                values[1] += count
            if contexts == 1 and count >= high_single_threshold:
                values = reuse[f"single_context_count>={high_single_threshold:g}"]
                values[0] += 1
                values[1] += count

            pairs["expected_count__phoneme_length"].add(count, length)
            pairs["expected_count__contexts"].add(count, contexts)
            pairs["expected_count__surface_variants"].add(count, variants)
            pairs["phoneme_length__contexts"].add(length, contexts)
            pairs["phoneme_length__surface_variants"].add(length, variants)
            pairs["contexts__surface_variants"].add(contexts, variants)

            payload = {
                "source_artifact": "latent_lexicon.tsv",
                "form_key": key,
                "phoneme_ids": phoneme_ids,
                "phoneme_length": length,
                "expected_count": count,
                "number_of_contexts": contexts,
                "number_of_surface_variants": variants,
            }
            reservoirs["longest_lexical_forms"].add(length, key, payload)
            if length >= 8:
                reservoirs["high_mass_long_forms"].add(count, key, payload)
            reservoirs["high_context_forms"].add(contexts, key, payload)
            reservoirs["high_surface_variant_forms"].add(variants, key, payload)
            reservoirs["low_count_forms"].add(-count, key, payload)

            if row_count <= max(PAIR_TOP_K):
                top_order.append(key)
                top_weights[key] = count / declared_total
            cumulative_before = total - count
            for threshold in MASS_THRESHOLDS:
                threshold_name = f"{threshold * 100:g}%"
                if cumulative_before < threshold * declared_total:
                    mass_sketches[threshold_name].add(key)
                if threshold_name not in support and total >= threshold * declared_total:
                    support[threshold_name] = row_count
            for k in TOP_MASS_K:
                if row_count == k:
                    top_mass_at[k] = total / declared_total

    if row_count != declared_types:
        raise GateValidationError(
            (
                f"{cell.spec.cell_id}: lexicon row count {row_count} differs from "
                f"declared active types {declared_types}",
            )
        )
    tolerance = max(1e-9, 1e-9 * declared_total)
    if abs(total - declared_total) > tolerance:
        raise GateValidationError(
            (
                f"{cell.spec.cell_id}: lexicon mass {total} differs from "
                f"declared expected tokens {declared_total}",
            )
        )
    for threshold in MASS_THRESHOLDS:
        support.setdefault(f"{threshold * 100:g}%", row_count)
    for k in TOP_MASS_K:
        top_mass_at.setdefault(k, 1.0)

    entropy = math.log(total) - count_log_count / total
    inverse_simpson = total * total / count_square
    gini = (
        (declared_types + 1) / declared_types
        - 2.0 * rank_weighted / (declared_types * total)
    )
    distribution_rows = [
        _distribution_row(cell.spec.cell_id, "lexicon", "expected_count", count_summary),
        {
            "cell_id": cell.spec.cell_id,
            "family": "lexicon",
            "metric": "diversity",
            "active_types": declared_types,
            "expected_count_total": total,
            "shannon_entropy_nats": entropy,
            "effective_vocabulary_exp_entropy": math.exp(entropy),
            "inverse_simpson_effective_vocabulary": inverse_simpson,
            "gini_expected_count": gini,
            "gini_formula": "descending_rank_exact",
        },
    ]
    distribution_rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "mass_support",
            "metric": threshold_name,
            "type_count": type_count,
            "type_fraction": type_count / declared_types,
        }
        for threshold_name, type_count in sorted(support.items())
    )
    distribution_rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "top_mass",
            "metric": f"top_{k}",
            "mass_fraction": top_mass_at[k],
        }
        for k in TOP_MASS_K
    )
    distribution_rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "expected_count_bin",
            "metric": bin_name,
            "type_count": int(values[0]),
            "type_fraction": values[0] / declared_types,
            "mass": values[1],
            "mass_fraction": values[1] / total,
        }
        for bin_name, values in sorted(count_bins.items())
    )

    length_rows: list[dict[str, Any]] = []
    for weighting, distribution in (("type", length_type), ("expected_mass", length_mass)):
        row = {
            "cell_id": cell.spec.cell_id,
            "weighting": weighting,
            "mean_phoneme_length": (
                sum(length * weight for length, weight in distribution.items())
                / sum(distribution.values())
            ),
            "quantile_method": "exact_discrete_weighted",
        }
        row.update({_quantile_name(q): _weighted_quantile(distribution, q) for q in QUANTILES})
        length_rows.append(row)
    for threshold in LENGTH_MASS_THRESHOLDS:
        mass = sum(value for length, value in length_mass.items() if length >= threshold)
        length_rows.append(
            {
                "cell_id": cell.spec.cell_id,
                "weighting": "expected_mass_tail",
                "threshold": f"length>={threshold}",
                "mass": mass,
                "mass_fraction": mass / total,
            }
        )

    reuse_rows = [
        {
            "cell_id": cell.spec.cell_id,
            "family": "reuse_threshold",
            "metric": metric,
            "type_count": int(values[0]),
            "type_fraction": values[0] / declared_types,
            "mass": values[1],
            "mass_fraction": values[1] / total,
            "usage_semantics": "thresholded_top_k_contexts_or_surface_associations",
        }
        for metric, values in sorted(reuse.items())
    ]
    reuse_rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "pearson",
            "metric": metric,
            "value": pair.pearson(),
            "formula": "one_pass_centered_product_moment",
        }
        for metric, pair in sorted(pairs.items())
    )
    reuse_rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "expected_count_bin_relationship",
            "metric": bin_name,
            "type_count": int(values[0]),
            "mean_phoneme_length": values[1] / values[0],
            "mean_contexts": values[2] / values[0],
            "mean_surface_variants": values[3] / values[0],
        }
        for bin_name, values in sorted(binned_relationships.items())
    )
    evidence = [
        row
        for reservoir in reservoirs.values()
        for row in reservoir.rows(cell.spec.cell_id)
    ]
    return LexiconReduction(
        row_count=row_count,
        distribution_rows=distribution_rows,
        length_rows=length_rows,
        reuse_rows=reuse_rows,
        evidence=evidence,
        top_order=tuple(top_order),
        top_weights=top_weights,
        mass_sketches=mass_sketches,
    )


def _reduce_passes(cell: LoadedCell) -> tuple[list[dict[str, Any]], int]:
    path = cell.spec.run_dir / "iteration_metrics.json"
    history = _array(_read_json(path, f"{cell.spec.cell_id} pass history"), str(path))
    expected_passes = _integer(cell.config.get("passes"), f"{cell.spec.cell_id} passes")
    if len(history) != expected_passes:
        raise GateValidationError(
            (f"{cell.spec.cell_id}: pass history length differs from config",)
        )
    fields = (
        "lexicon_types",
        "lexical_count_total",
        "expected_lexical_tokens",
        "mean_identity_mass",
        "mean_latent_mass",
        "log_partition",
        "candidate_factors",
        "candidate_nodes",
        "candidate_edges",
        "overflowed_tokens",
    )
    previous: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(history, start=1):
        item = _object(raw, f"{path} pass {index}")
        if _integer(item.get("pass"), f"{path} pass index") != index:
            raise GateValidationError((f"{cell.spec.cell_id}: pass order is not contiguous",))
        segments = _number(item.get("segments"), f"{path} pass {index} segments", nonnegative=True)
        metrics = {
            field: _number(item.get(field), f"{path} pass {index} {field}")
            for field in fields
        }
        metrics["expected_tokens_per_segment"] = (
            0.0 if segments == 0.0 else metrics["expected_lexical_tokens"] / segments
        )
        metrics["candidate_nodes_per_segment"] = (
            0.0 if segments == 0.0 else metrics["candidate_nodes"] / segments
        )
        metrics["candidate_edges_per_segment"] = (
            0.0 if segments == 0.0 else metrics["candidate_edges"] / segments
        )
        for metric, value in metrics.items():
            old = previous.get(metric)
            rows.append(
                {
                    "cell_id": cell.spec.cell_id,
                    "pass": index,
                    "metric": metric,
                    "value": value,
                    "absolute_change_from_previous": None if old is None else value - old,
                    "relative_change_from_previous": (
                        None if old is None else _relative_change(value, old)
                    ),
                }
            )
            previous[metric] = value
    return rows, len(history)


def _edge_tail_share(
    bucket_counts: Mapping[int, int],
    bucket_mass: Mapping[int, float],
    row_count: int,
    fraction: float,
) -> float:
    target = max(1, math.ceil(row_count * fraction))
    remaining = target
    selected_mass = 0.0
    for bucket in sorted(bucket_counts, reverse=True):
        count = bucket_counts[bucket]
        take = min(remaining, count)
        selected_mass += bucket_mass[bucket] * take / count
        remaining -= take
        if remaining == 0:
            break
    total = sum(bucket_mass.values())
    return 0.0 if total == 0.0 else selected_mass / total


@dataclass(slots=True)
class AnalysisReduction:
    row_count: int
    phoneme_count: int
    id_digest: str
    ambiguity_rows: list[dict[str, Any]]
    candidate_rows: list[dict[str, Any]]
    document_rows: list[dict[str, Any]]
    length_rows: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    topk_rule_mass: dict[str, float]


def _reduce_analyses(cell: LoadedCell) -> AnalysisReduction:
    path = cell.spec.run_dir / "analyses.jsonl"
    summaries = {
        metric: NumericSummary()
        for metric in (
            "identity_mass",
            "latent_mass",
            "entropy",
            "top1_posterior",
            "top_analysis_mass",
            "residual_posterior",
            "top1_top2_margin",
            "effective_ambiguity",
            "topk_effective_ambiguity",
        )
    }
    candidates = {
        metric: NumericSummary()
        for metric in (
            "factors",
            "lattice_nodes",
            "lexical_edges",
            "overflowed_tokens",
            "edges_per_phoneme",
        )
    }
    optional_candidates = {
        "raw_internal_matches": NumericSummary(),
        "retained_internal_matches": NumericSummary(),
    }
    candidate_relations = {
        "lexical_edges__phoneme_length": OnlinePair(),
        "lexical_edges__entropy": OnlinePair(),
        "lexical_edges__identity_mass": OnlinePair(),
        "lexical_edges__latent_mass": OnlinePair(),
    }
    reservoirs = {
        "high_entropy_segments": TopReservoir("high_entropy_segments"),
        "low_top1_segments": TopReservoir("low_top1_segments"),
        "high_residual_segments": TopReservoir("high_residual_segments"),
        "large_candidate_graphs": TopReservoir("large_candidate_graphs"),
        "long_surface_segments": TopReservoir("long_surface_segments"),
        "overflow_segments": TopReservoir("overflow_segments"),
    }
    common = HashReservoir("hash_selected_common_lines")
    documents: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    length_strata: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    topk_rule_mass: Counter[str] = Counter()
    id_hash = hashlib.sha256()
    edge_bucket_counts: Counter[int] = Counter()
    edge_bucket_mass: Counter[int] = Counter()
    row_count = 0
    phoneme_count = 0

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise GateValidationError((f"{path}:{line_number}: blank JSONL row",))
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise GateValidationError(
                    (f"{path}:{line_number}: invalid JSON: {exc}",)
                ) from exc
            row = _object(raw, f"{path}:{line_number}")
            _required(
                row,
                (
                    "schema_version",
                    "segment_id",
                    "document",
                    "line_number",
                    "surface",
                    "top_analyses",
                    "top_analysis_mass",
                    "residual_posterior",
                    "identity_mass",
                    "latent_mass",
                    "entropy",
                    "log_partition",
                    "candidate_counts",
                ),
                f"{path}:{line_number}",
            )
            if row["schema_version"] != 1:
                raise GateValidationError((f"{path}:{line_number}: unsupported schema",))
            segment_id = row["segment_id"]
            document = row["document"]
            surface = row["surface"]
            if not all(isinstance(value, str) and value for value in (segment_id, document, surface)):
                raise GateValidationError(
                    (f"{path}:{line_number}: segment/document/surface must be nonempty strings",)
                )
            _integer(row["line_number"], f"{path}:{line_number} source line")
            id_hash.update(segment_id.encode("utf-8"))
            id_hash.update(b"\0")
            row_count += 1
            try:
                segment_phonemes = len(
                    parse_surface(surface, script=cell.spec.script).phonemes
                )
            except (ValueError, TypeError) as exc:
                raise GateValidationError(
                    (f"{path}:{line_number}: surface does not parse: {exc}",)
                ) from exc
            if segment_phonemes <= 0:
                raise GateValidationError((f"{path}:{line_number}: no surface phonemes",))
            phoneme_count += segment_phonemes

            identity = summaries["identity_mass"].add(
                row["identity_mass"], f"{path}:{line_number} identity_mass"
            )
            latent = summaries["latent_mass"].add(
                row["latent_mass"], f"{path}:{line_number} latent_mass"
            )
            entropy = summaries["entropy"].add(
                row["entropy"], f"{path}:{line_number} entropy"
            )
            if abs(identity + latent - 1.0) > 1e-7:
                raise GateValidationError(
                    (f"{path}:{line_number}: identity_mass + latent_mass must equal one",)
                )
            top = _array(row["top_analyses"], f"{path}:{line_number} top_analyses")
            probabilities: list[float] = []
            for analysis_index, analysis_raw in enumerate(top):
                analysis = _object(
                    analysis_raw, f"{path}:{line_number} top analysis {analysis_index}"
                )
                _required(
                    analysis,
                    ("posterior", "latent_units", "rule_ids"),
                    f"{path}:{line_number} top analysis {analysis_index}",
                )
                probability = _number(
                    analysis["posterior"],
                    f"{path}:{line_number} top posterior",
                    nonnegative=True,
                )
                if probability > 1.0:
                    raise GateValidationError(
                        (f"{path}:{line_number}: top posterior exceeds one",)
                    )
                probabilities.append(probability)
                rule_ids = _array(
                    analysis["rule_ids"], f"{path}:{line_number} rule_ids"
                )
                if any(not isinstance(rule_id, str) or not rule_id for rule_id in rule_ids):
                    raise GateValidationError(
                        (f"{path}:{line_number}: rule_ids must be nonempty strings",)
                    )
                for rule_id in rule_ids:
                    topk_rule_mass[rule_id] += probability
            if probabilities != sorted(probabilities, reverse=True):
                raise GateValidationError(
                    (f"{path}:{line_number}: top analyses are not posterior sorted",)
                )
            top_mass = summaries["top_analysis_mass"].add(
                row["top_analysis_mass"], f"{path}:{line_number} top_analysis_mass"
            )
            residual = summaries["residual_posterior"].add(
                row["residual_posterior"], f"{path}:{line_number} residual"
            )
            if abs(sum(probabilities) - top_mass) > 1e-7:
                raise GateValidationError(
                    (f"{path}:{line_number}: top_analysis_mass differs from top-k sum",)
                )
            if abs(residual - max(0.0, 1.0 - top_mass)) > 1e-7:
                raise GateValidationError(
                    (f"{path}:{line_number}: residual posterior is inconsistent",)
                )
            top1 = probabilities[0] if probabilities else 0.0
            top2 = probabilities[1] if len(probabilities) > 1 else 0.0
            margin = top1 - top2
            summaries["top1_posterior"].add(top1)
            summaries["top1_top2_margin"].add(margin)
            summaries["effective_ambiguity"].add(math.exp(entropy))
            normalized_square = (
                0.0
                if top_mass == 0.0
                else sum((probability / top_mass) ** 2 for probability in probabilities)
            )
            summaries["topk_effective_ambiguity"].add(
                0.0 if normalized_square == 0.0 else 1.0 / normalized_square
            )
            reconstructed_tokens: list[dict[str, Any]] | None = None
            if top:
                top_analysis = _object(top[0], f"{path}:{line_number} top analysis 0")
                units = _array(
                    top_analysis["latent_units"],
                    f"{path}:{line_number} top latent_units",
                )
                reconstructed_tokens = []
                for unit_index, raw_unit in enumerate(units):
                    unit = _object(
                        raw_unit,
                        f"{path}:{line_number} top latent unit {unit_index}",
                    )
                    _required(
                        unit,
                        ("form_key", "phoneme_ids"),
                        f"{path}:{line_number} top latent unit {unit_index}",
                    )
                    if not isinstance(unit["form_key"], str) or not unit["form_key"]:
                        raise GateValidationError(
                            (f"{path}:{line_number}: invalid top latent form_key",)
                        )
                    phoneme_ids = _array(
                        unit["phoneme_ids"],
                        f"{path}:{line_number} top latent phoneme_ids",
                    )
                    if not phoneme_ids or any(
                        not isinstance(symbol, str) or not symbol
                        for symbol in phoneme_ids
                    ):
                        raise GateValidationError(
                            (f"{path}:{line_number}: invalid top latent phoneme_ids",)
                        )
                    reconstructed_tokens.append(
                        {"form_key": unit["form_key"], "phoneme_ids": phoneme_ids}
                    )

            candidate = _object(
                row["candidate_counts"], f"{path}:{line_number} candidate_counts"
            )
            _required(
                candidate,
                ("factors", "lattice_nodes", "lexical_edges", "overflowed_tokens"),
                f"{path}:{line_number} candidate_counts",
            )
            candidate_values = {
                name: candidates[name].add(
                    candidate[name], f"{path}:{line_number} candidate {name}"
                )
                for name in ("factors", "lattice_nodes", "lexical_edges", "overflowed_tokens")
            }
            edges = candidate_values["lexical_edges"]
            candidates["edges_per_phoneme"].add(edges / segment_phonemes)
            for name, summary in optional_candidates.items():
                if name in candidate:
                    summary.add(candidate[name], f"{path}:{line_number} candidate {name}")
            edge_bucket = (
                NumericSummary._ZERO_BUCKET
                if edges == 0.0
                else math.floor(math.log2(edges) * NumericSummary._BINS_PER_OCTAVE)
            )
            edge_bucket_counts[edge_bucket] += 1
            edge_bucket_mass[edge_bucket] += edges
            candidate_relations["lexical_edges__phoneme_length"].add(
                edges, segment_phonemes
            )
            candidate_relations["lexical_edges__entropy"].add(edges, entropy)
            candidate_relations["lexical_edges__identity_mass"].add(edges, identity)
            candidate_relations["lexical_edges__latent_mass"].add(edges, latent)

            evidence_payload = {
                "source_artifact": "analyses.jsonl",
                "document": document,
                "line_number": int(row["line_number"]),
                "surface_phoneme_length": segment_phonemes,
                "entropy": entropy,
                "top1_posterior": top1,
                "residual_posterior": residual,
                "identity_mass": identity,
                "latent_mass": latent,
                "candidate_edges": int(edges),
                "overflowed_tokens": int(candidate_values["overflowed_tokens"]),
                "topk_only_fields": [
                    "top1_posterior",
                    "top1_top2_margin",
                    "top_analysis_mass",
                    "residual_posterior",
                ],
                "reconstructed_top_analysis_tokens": reconstructed_tokens,
                "reconstruction_scope": (
                    "valid_bounded_top_k_latent_units"
                    if reconstructed_tokens is not None
                    else "unavailable"
                ),
            }
            reservoirs["high_entropy_segments"].add(entropy, segment_id, evidence_payload)
            reservoirs["low_top1_segments"].add(-top1, segment_id, evidence_payload)
            reservoirs["high_residual_segments"].add(residual, segment_id, evidence_payload)
            reservoirs["large_candidate_graphs"].add(edges, segment_id, evidence_payload)
            reservoirs["long_surface_segments"].add(
                segment_phonemes, segment_id, evidence_payload
            )
            if candidate_values["overflowed_tokens"] > 0:
                reservoirs["overflow_segments"].add(
                    candidate_values["overflowed_tokens"], segment_id, evidence_payload
                )
            common.add(segment_id, evidence_payload)

            document_row = documents[document]
            document_row["segments"] += 1
            document_row["phonemes"] += segment_phonemes
            document_row["candidate_edges"] += edges
            document_row["entropy"] += entropy
            document_row["identity_mass"] += identity
            document_row["latent_mass"] += latent
            stratum_row = length_strata[_length_stratum(segment_phonemes)]
            stratum_row["segments"] += 1
            stratum_row["phonemes"] += segment_phonemes
            stratum_row["candidate_edges"] += edges
            stratum_row["entropy"] += entropy
            stratum_row["identity_mass"] += identity
            stratum_row["latent_mass"] += latent

    declared_segments = _integer(
        cell.summary.get("segments"), f"{cell.spec.cell_id} summary segments"
    )
    if row_count != declared_segments:
        raise GateValidationError(
            (
                f"{cell.spec.cell_id}: analyses row count {row_count} differs "
                f"from summary segments {declared_segments}",
            )
        )

    ambiguity_rows = [
        _distribution_row(cell.spec.cell_id, "segment_posterior", metric, summary)
        for metric, summary in summaries.items()
    ]
    for row in ambiguity_rows:
        if row["metric"] in {
            "top1_posterior",
            "top_analysis_mass",
            "residual_posterior",
            "top1_top2_margin",
            "topk_effective_ambiguity",
        }:
            row["estimate_scope"] = "bounded_top_k_inspection"
        else:
            row["estimate_scope"] = "exact_full_posterior_summary"
    candidate_rows = [
        _distribution_row(cell.spec.cell_id, "candidate_scaling", metric, summary)
        for metric, summary in candidates.items()
    ]
    for metric, summary in optional_candidates.items():
        candidate_rows.append(
            {
                **_distribution_row(
                    cell.spec.cell_id, "candidate_scaling_optional", metric, summary
                ),
                "available": summary.count > 0,
            }
        )
    candidate_rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "edge_heavy_tail",
            "metric": f"top_{fraction * 100:g}_percent_segments",
            "edge_mass_fraction": _edge_tail_share(
                edge_bucket_counts, edge_bucket_mass, row_count, fraction
            ),
            "estimate_scope": "deterministic_log2_histogram_within_bin_mean",
        }
        for fraction in (0.001, 0.01, 0.05)
    )
    candidate_rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "pearson",
            "metric": metric,
            "value": relation.pearson(),
            "formula": "one_pass_centered_product_moment",
        }
        for metric, relation in candidate_relations.items()
    )
    document_rows = [
        {
            "cell_id": cell.spec.cell_id,
            "document": document,
            **values,
            "mean_entropy": values["entropy"] / values["segments"],
            "mean_identity_mass": values["identity_mass"] / values["segments"],
            "mean_latent_mass": values["latent_mass"] / values["segments"],
            "edges_per_phoneme": values["candidate_edges"] / values["phonemes"],
        }
        for document, values in sorted(documents.items())
    ]
    length_rows = [
        {
            "cell_id": cell.spec.cell_id,
            "length_stratum": stratum,
            **values,
            "mean_entropy": values["entropy"] / values["segments"],
            "mean_identity_mass": values["identity_mass"] / values["segments"],
            "mean_latent_mass": values["latent_mass"] / values["segments"],
            "edges_per_phoneme": values["candidate_edges"] / values["phonemes"],
        }
        for stratum, values in sorted(length_strata.items())
    ]
    evidence = [
        row
        for reservoir in reservoirs.values()
        for row in reservoir.rows(cell.spec.cell_id)
    ]
    evidence.extend(common.rows(cell.spec.cell_id))
    return AnalysisReduction(
        row_count=row_count,
        phoneme_count=phoneme_count,
        id_digest=id_hash.hexdigest(),
        ambiguity_rows=ambiguity_rows,
        candidate_rows=candidate_rows,
        document_rows=document_rows,
        length_rows=length_rows,
        evidence=evidence,
        topk_rule_mass=dict(sorted(topk_rule_mass.items())),
    )


@dataclass(slots=True)
class BoundaryReduction:
    row_count: int
    boundary_count: int
    expected_boundary_total: float
    id_digest: str
    rows: list[dict[str, Any]]
    evidence: list[dict[str, Any]]


def _binary_entropy(probability: float) -> float:
    result = 0.0
    for value in (probability, 1.0 - probability):
        if value > 0.0:
            result -= value * math.log(value)
    return result


def _reduce_boundaries(cell: LoadedCell) -> BoundaryReduction:
    path = cell.spec.run_dir / "boundary_posteriors.jsonl"
    probability_summary = NumericSummary()
    entropy_summary = NumericSummary()
    expected_per_segment = NumericSummary()
    expected_per_phoneme = NumericSummary()
    cue: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    confidence: Counter[str] = Counter()
    entropy_examples = TopReservoir("high_boundary_entropy_segments")
    confidence_examples = TopReservoir("high_boundary_confidence_segments")
    id_hash = hashlib.sha256()
    row_count = 0
    boundary_count = 0
    expected_total = 0.0

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise GateValidationError((f"{path}:{line_number}: blank JSONL row",))
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise GateValidationError(
                    (f"{path}:{line_number}: invalid JSON: {exc}",)
                ) from exc
            row = _object(raw, f"{path}:{line_number}")
            _required(
                row,
                ("schema_version", "segment_id", "surface", "boundaries"),
                f"{path}:{line_number}",
            )
            if row["schema_version"] != 1:
                raise GateValidationError((f"{path}:{line_number}: unsupported schema",))
            segment_id, surface = row["segment_id"], row["surface"]
            if not isinstance(segment_id, str) or not segment_id:
                raise GateValidationError((f"{path}:{line_number}: invalid segment_id",))
            if not isinstance(surface, str) or not surface:
                raise GateValidationError((f"{path}:{line_number}: invalid surface",))
            try:
                phonemes = len(parse_surface(surface, script=cell.spec.script).phonemes)
            except (TypeError, ValueError) as exc:
                raise GateValidationError(
                    (f"{path}:{line_number}: surface does not parse: {exc}",)
                ) from exc
            if phonemes <= 0:
                raise GateValidationError((f"{path}:{line_number}: no surface phonemes",))
            id_hash.update(segment_id.encode("utf-8"))
            id_hash.update(b"\0")
            row_count += 1
            segment_expected = 0.0
            segment_entropy = 0.0
            segment_confidence = 0.0
            boundaries = _array(row["boundaries"], f"{path}:{line_number} boundaries")
            for boundary_index, raw_boundary in enumerate(boundaries):
                boundary = _object(
                    raw_boundary, f"{path}:{line_number} boundary {boundary_index}"
                )
                _required(
                    boundary,
                    (
                        "boundary_id",
                        "cue_kind",
                        "source_start",
                        "source_end",
                        "probability",
                    ),
                    f"{path}:{line_number} boundary {boundary_index}",
                )
                boundary_id, cue_kind = boundary["boundary_id"], boundary["cue_kind"]
                if not isinstance(boundary_id, str) or not boundary_id:
                    raise GateValidationError(
                        (f"{path}:{line_number}: invalid boundary_id",)
                    )
                if not isinstance(cue_kind, str) or not cue_kind:
                    raise GateValidationError((f"{path}:{line_number}: invalid cue_kind",))
                _integer(boundary["source_start"], f"{path}:{line_number} source_start")
                _integer(boundary["source_end"], f"{path}:{line_number} source_end")
                probability = _number(
                    boundary["probability"],
                    f"{path}:{line_number} boundary probability",
                    nonnegative=True,
                )
                if probability > 1.0:
                    raise GateValidationError(
                        (f"{path}:{line_number}: boundary probability exceeds one",)
                    )
                entropy = _binary_entropy(probability)
                probability_summary.add(probability)
                entropy_summary.add(entropy)
                segment_expected += probability
                segment_entropy += entropy
                segment_confidence = max(
                    segment_confidence, max(probability, 1.0 - probability)
                )
                boundary_count += 1
                cue_row = cue[cue_kind]
                cue_row["count"] += 1
                cue_row["expected_boundaries"] += probability
                cue_row["binary_entropy"] += entropy
                for threshold in CONFIDENCE_THRESHOLDS:
                    if probability >= threshold:
                        confidence[f"present_p>={threshold:g}"] += 1
                    if probability <= 1.0 - threshold:
                        confidence[f"absent_p>={threshold:g}"] += 1
                    if max(probability, 1.0 - probability) >= threshold:
                        confidence[f"decision_confidence>={threshold:g}"] += 1
            expected_total += segment_expected
            expected_per_segment.add(segment_expected)
            expected_per_phoneme.add(segment_expected / phonemes)
            payload = {
                "source_artifact": "boundary_posteriors.jsonl",
                "surface_phoneme_length": phonemes,
                "candidate_boundary_count": len(boundaries),
                "expected_boundaries": segment_expected,
                "mean_binary_entropy": (
                    0.0 if not boundaries else segment_entropy / len(boundaries)
                ),
                "maximum_binary_decision_confidence": segment_confidence,
            }
            entropy_examples.add(segment_entropy, segment_id, payload)
            confidence_examples.add(segment_confidence, segment_id, payload)

    declared_segments = _integer(
        cell.summary.get("segments"), f"{cell.spec.cell_id} summary segments"
    )
    if row_count != declared_segments:
        raise GateValidationError(
            (
                f"{cell.spec.cell_id}: boundary row count {row_count} differs "
                f"from summary segments {declared_segments}",
            )
        )
    rows = [
        _distribution_row(
            cell.spec.cell_id, "boundary", "posterior_probability", probability_summary
        ),
        _distribution_row(
            cell.spec.cell_id, "boundary", "binary_entropy_nats", entropy_summary
        ),
        _distribution_row(
            cell.spec.cell_id, "boundary", "expected_boundaries_per_segment",
            expected_per_segment,
        ),
        _distribution_row(
            cell.spec.cell_id, "boundary", "expected_boundaries_per_phoneme",
            expected_per_phoneme,
        ),
    ]
    rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "cue_kind",
            "metric": cue_kind,
            "candidate_boundary_count": int(values["count"]),
            "expected_boundaries": values["expected_boundaries"],
            "mean_posterior": values["expected_boundaries"] / values["count"],
            "mean_binary_entropy_nats": values["binary_entropy"] / values["count"],
            "interpretation": "orthographic_cue_not_gold_lexical_boundary",
        }
        for cue_kind, values in sorted(cue.items())
    )
    rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "confidence_threshold",
            "metric": metric,
            "count": count,
            "fraction_of_candidate_boundaries": (
                None if boundary_count == 0 else count / boundary_count
            ),
        }
        for metric, count in sorted(confidence.items())
    )
    evidence = entropy_examples.rows(cell.spec.cell_id)
    evidence.extend(confidence_examples.rows(cell.spec.cell_id))
    return BoundaryReduction(
        row_count=row_count,
        boundary_count=boundary_count,
        expected_boundary_total=expected_total,
        id_digest=id_hash.hexdigest(),
        rows=rows,
        evidence=evidence,
    )


def _reduce_rules(
    cell: LoadedCell,
    *,
    segments: int,
    expected_boundaries: float,
    phonemes: int,
    topk_rule_mass: Mapping[str, float],
) -> tuple[list[dict[str, Any]], int]:
    path = cell.spec.run_dir / "rule_usage.tsv"
    declared = _integer(
        cell.provenance.get("external_rule_count"),
        f"{cell.spec.cell_id} external_rule_count",
    )
    values: list[tuple[str, float]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or not {"rule_id", "expected_usage"}.issubset(
            reader.fieldnames
        ):
            raise GateValidationError((f"{cell.spec.cell_id}: invalid rule_usage header",))
        seen: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            rule_id = row.get("rule_id", "")
            if not rule_id or rule_id in seen:
                raise GateValidationError(
                    (f"{path}:{line_number}: empty or duplicate rule_id",)
                )
            seen.add(rule_id)
            values.append(
                (
                    rule_id,
                    _number(
                        row.get("expected_usage"),
                        f"{path}:{line_number} expected_usage",
                        nonnegative=True,
                    ),
                )
            )
    if len(values) != declared:
        raise GateValidationError(
            (
                f"{cell.spec.cell_id}: rule row count {len(values)} differs "
                f"from declared count {declared}",
            )
        )
    total = sum(value for _rule_id, value in values)
    probabilities = {
        rule_id: (0.0 if total == 0.0 else value / total)
        for rule_id, value in values
    }
    entropy = -sum(p * math.log(p) for p in probabilities.values() if p > 0.0)
    ordered = sorted(values, key=lambda item: (-item[1], item[0]))
    rows: list[dict[str, Any]] = [
        {
            "cell_id": cell.spec.cell_id,
            "family": "exact_global_summary",
            "metric": "rule_usage",
            "rule_inventory_size": declared,
            "rules_with_positive_usage": sum(value > 0.0 for _rule, value in values),
            "positive_rule_coverage": (
                0.0 if declared == 0 else sum(value > 0.0 for _rule, value in values) / declared
            ),
            "expected_usage_total": total,
            "shannon_entropy_nats": entropy,
            "effective_rule_count": 0.0 if total == 0.0 else math.exp(entropy),
            "usage_per_segment": _ratio(total, float(segments)),
            "usage_per_expected_boundary": _ratio(total, expected_boundaries),
            "usage_per_phoneme": _ratio(total, float(phonemes)),
        }
    ]
    rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "exact_global_rule",
            "metric": rule_id,
            "rank": rank,
            "expected_usage": value,
            "normalized_usage": probabilities[rule_id],
        }
        for rank, (rule_id, value) in enumerate(ordered, start=1)
    )
    for k in (1, 5, 10, 25):
        rows.append(
            {
                "cell_id": cell.spec.cell_id,
                "family": "exact_global_top_n",
                "metric": f"top_{k}",
                "normalized_usage": (
                    0.0 if total == 0.0 else sum(value for _rule, value in ordered[:k]) / total
                ),
            }
        )
    rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "top_k_segment_diagnostic",
            "metric": rule_id,
            "posterior_weighted_reported_usage": mass,
            "estimate_scope": "bounded_top_k_inspection_approximate",
        }
        for rule_id, mass in sorted(topk_rule_mass.items())
    )
    return rows, len(values)


def _reduce_runtime(
    cell: LoadedCell, *, phonemes: int
) -> list[dict[str, Any]]:
    timing = cell.timing
    timings = _object(
        timing.get("timings_seconds", {}), f"{cell.spec.cell_id} timings_seconds"
    )
    counters = _object(timing.get("counters", {}), f"{cell.spec.cell_id} counters")
    rows: list[dict[str, Any]] = []
    inclusion = {
        "inspection_inference": "includes lexical scoring and SQLite lookup",
        "inspection_worker_sqlite": "subset of inspection inference/scoring",
        "inspection_serialization": "JSONL serialization only",
        "lexicon_finalize": "SQLite lexicon finalization",
    }
    for metric, raw_value in sorted(timings.items()):
        rows.append(
            {
                "cell_id": cell.spec.cell_id,
                "family": "timer",
                "metric": metric,
                "value": _number(
                    raw_value, f"{cell.spec.cell_id} timer {metric}", nonnegative=True
                ),
                "inclusion_note": inclusion.get(metric, ""),
            }
        )
    for metric, raw_value in sorted(counters.items()):
        rows.append(
            {
                "cell_id": cell.spec.cell_id,
                "family": "counter",
                "metric": metric,
                "value": _number(
                    raw_value, f"{cell.spec.cell_id} counter {metric}", nonnegative=True
                ),
            }
        )
    scorers = _array(timing.get("lexical_scorers", []), f"{cell.spec.cell_id} scorers")
    scorer_totals: Counter[str] = Counter()
    for index, raw_scorer in enumerate(scorers):
        scorer = _object(raw_scorer, f"{cell.spec.cell_id} scorer {index}")
        for metric in (
            "score_calls",
            "cache_hits",
            "cache_misses",
            "sqlite_selects",
            "sqlite_seconds",
        ):
            if metric in scorer:
                scorer_totals[metric] += _number(
                    scorer[metric],
                    f"{cell.spec.cell_id} scorer {index} {metric}",
                    nonnegative=True,
                )
    rows.extend(
        {
            "cell_id": cell.spec.cell_id,
            "family": "lexical_scorer_total",
            "metric": metric,
            "value": value,
        }
        for metric, value in sorted(scorer_totals.items())
    )
    for metric, raw_value in sorted(cell.process.items()):
        if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            rows.append(
                {
                    "cell_id": cell.spec.cell_id,
                    "family": "process_tree",
                    "metric": metric,
                    "value": _number(
                        raw_value, f"{cell.spec.cell_id} process {metric}", nonnegative=True
                    ),
                }
            )
    wall = _number(
        cell.process.get("wall_seconds"),
        f"{cell.spec.cell_id} process wall_seconds",
        nonnegative=True,
    )
    edges = _number(
        cell.summary.get("candidate_edges"),
        f"{cell.spec.cell_id} candidate_edges",
        nonnegative=True,
    )
    characters = _number(
        cell.summary.get("characters"),
        f"{cell.spec.cell_id} characters",
        nonnegative=True,
    )
    rows.extend(
        (
            {
                "cell_id": cell.spec.cell_id,
                "family": "throughput",
                "metric": "candidate_edges_per_wall_second",
                "value": _ratio(edges, wall),
            },
            {
                "cell_id": cell.spec.cell_id,
                "family": "throughput",
                "metric": "surface_characters_per_wall_second",
                "value": _ratio(characters, wall),
            },
            {
                "cell_id": cell.spec.cell_id,
                "family": "throughput",
                "metric": "surface_phonemes_per_wall_second",
                "value": _ratio(float(phonemes), wall),
            },
        )
    )
    return rows


def _jaccard(left: set[str], right: set[str]) -> float | None:
    union = left | right
    return None if not union else len(left & right) / len(union)


def _spearman_on_intersection(
    left_order: Sequence[str], right_order: Sequence[str]
) -> float | None:
    left_rank = {key: index + 1 for index, key in enumerate(left_order)}
    right_rank = {key: index + 1 for index, key in enumerate(right_order)}
    shared = sorted(set(left_rank) & set(right_rank))
    if len(shared) < 2:
        return None
    x = [float(left_rank[key]) for key in shared]
    y = [float(right_rank[key]) for key in shared]
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    numerator = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    denominator = math.sqrt(
        sum((a - mean_x) ** 2 for a in x) * sum((b - mean_y) ** 2 for b in y)
    )
    return None if denominator == 0.0 else numerator / denominator


def _pairwise_rows(
    cells: Sequence[LoadedCell],
    lexicons: Mapping[str, LexiconReduction],
    boundaries: Mapping[str, BoundaryReduction],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for left, right in combinations(cells, 2):
        left_id, right_id = left.spec.cell_id, right.spec.cell_id
        pair_id = f"{left_id}__vs__{right_id}"
        a, b = lexicons[left_id], lexicons[right_id]
        for k in PAIR_TOP_K:
            left_keys = set(a.top_order[:k])
            right_keys = set(b.top_order[:k])
            rows.append(
                {
                    "pair_id": pair_id,
                    "cell_a": left_id,
                    "cell_b": right_id,
                    "family": "top_k_support",
                    "metric": f"jaccard_top_{k}",
                    "value": _jaccard(left_keys, right_keys),
                    "scope": "exact_within_retained_top_k",
                }
            )
        union = set(a.top_weights) | set(b.top_weights)
        left_tail = max(0.0, 1.0 - sum(a.top_weights.values()))
        right_tail = max(0.0, 1.0 - sum(b.top_weights.values()))
        weighted_l1 = sum(
            abs(a.top_weights.get(key, 0.0) - b.top_weights.get(key, 0.0))
            for key in union
        ) + abs(left_tail - right_tail)
        rows.extend(
            (
                {
                    "pair_id": pair_id,
                    "cell_a": left_id,
                    "cell_b": right_id,
                    "family": "top_k_weighted",
                    "metric": "l1_top_10000_plus_aggregate_tail",
                    "value": weighted_l1,
                    "scope": "exact_top_k_with_single_unaligned_tail_bucket",
                },
                {
                    "pair_id": pair_id,
                    "cell_a": left_id,
                    "cell_b": right_id,
                    "family": "top_k_rank",
                    "metric": "spearman_shared_top_10000",
                    "value": _spearman_on_intersection(a.top_order, b.top_order),
                    "scope": "intersection_only",
                },
            )
        )
        for threshold in sorted(a.mass_sketches):
            rows.append(
                {
                    "pair_id": pair_id,
                    "cell_a": left_id,
                    "cell_b": right_id,
                    "family": "mass_support",
                    "metric": f"minhash_jaccard_{threshold}",
                    "value": _minhash_jaccard(
                        a.mass_sketches[threshold], b.mass_sketches[threshold]
                    ),
                    "scope": f"deterministic_bottom_{MINHASH_SIZE}_approximation",
                }
            )
        left_boundary = boundaries[left_id]
        right_boundary = boundaries[right_id]
        rows.append(
            {
                "pair_id": pair_id,
                "cell_a": left_id,
                "cell_b": right_id,
                "family": "boundary_reference",
                "metric": "expected_boundaries_per_segment_difference",
                "value": (
                    left_boundary.expected_boundary_total / left_boundary.row_count
                    - right_boundary.expected_boundary_total / right_boundary.row_count
                ),
                "scope": (
                    "continuous_posterior_or_surface_spacing_reference; "
                    "orthographic_spacing_is_not_gold"
                ),
            }
        )
    return rows


def _source_entry(
    cell: LoadedCell,
    name: str,
    *,
    base: Path,
    row_count: int | None,
) -> dict[str, Any]:
    path = cell.spec.run_dir / name
    audited = cell.audit.get("scientific_artifacts", {})
    identity = audited.get(name) if isinstance(audited, dict) else None
    if isinstance(identity, dict):
        size = _integer(identity.get("bytes"), f"{cell.spec.cell_id} {name} bytes")
        digest = identity.get("sha256")
    else:
        size = path.stat().st_size
        digest = _file_sha256(path)
    if not isinstance(digest, str) or len(digest) != 64:
        raise GateValidationError((f"{cell.spec.cell_id}: invalid SHA256 for {name}",))
    if name.endswith(".jsonl"):
        artifact_schema: object = 1
    elif name.endswith(".tsv"):
        with path.open("r", encoding="utf-8") as handle:
            artifact_schema = handle.readline().rstrip("\r\n")
    elif name.endswith(".json"):
        payload = _read_json(path, f"{cell.spec.cell_id} {name}")
        artifact_schema = payload.get("schema_version") if isinstance(payload, dict) else None
    else:
        artifact_schema = None
    return {
        "cell_id": cell.spec.cell_id,
        "run_id": cell.spec.run_id,
        "metrics_id": cell.spec.metrics_id,
        "script": cell.spec.script,
        "condition": cell.spec.condition,
        "relative_path": _relative_path(path, base),
        "bytes": size,
        "row_count": row_count,
        "sha256": digest,
        "scientific_git_sha": cell.spec.scientific_commit,
        "artifact_schema_or_header": artifact_schema,
        "config_signature": cell.provenance.get("config_signature"),
        "gate_input_identity": {
            "freeze_id": cell.provenance.get("freeze_id"),
            "manifest_sha256": cell.provenance.get("manifest_sha256"),
            "rules_sha256": cell.provenance.get("rules_sha256"),
        },
    }


def reduce_manifest(path: Path) -> dict[str, Any]:
    """Validate and stream all six completed cells into compact archive tables."""

    path = path.resolve()
    manifest_payload, specs = _parse_manifest(path)
    loaded = tuple(_load_cell(spec) for spec in specs)
    _validate_cross_cell_contract(loaded)

    tables: dict[str, list[dict[str, Any]]] = {
        "cells": [],
        "pass_dynamics": [],
        "lexicon_distribution": [],
        "lexical_length": [],
        "reuse_distribution": [],
        "ambiguity_distribution": [],
        "boundary_distribution": [],
        "rule_usage": [],
        "candidate_scaling": [],
        "document_distribution": [],
        "length_strata": [],
        "runtime_breakdown": [],
        "pairwise_stability": [],
    }
    evidence: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    lexicons: dict[str, LexiconReduction] = {}
    boundaries: dict[str, BoundaryReduction] = {}
    for cell in loaded:
        cell_id = cell.spec.cell_id
        pass_rows, pass_count = _reduce_passes(cell)
        lexicon = _reduce_lexicon(cell)
        analyses = _reduce_analyses(cell)
        boundary = _reduce_boundaries(cell)
        if analyses.id_digest != boundary.id_digest:
            raise GateValidationError(
                (f"{cell_id}: analyses and boundary segment identities/order differ",)
            )
        rules, rule_count = _reduce_rules(
            cell,
            segments=analyses.row_count,
            expected_boundaries=boundary.expected_boundary_total,
            phonemes=analyses.phoneme_count,
            topk_rule_mass=analyses.topk_rule_mass,
        )
        runtime = _reduce_runtime(cell, phonemes=analyses.phoneme_count)
        lexicons[cell_id] = lexicon
        boundaries[cell_id] = boundary
        tables["pass_dynamics"].extend(pass_rows)
        tables["lexicon_distribution"].extend(lexicon.distribution_rows)
        tables["lexical_length"].extend(lexicon.length_rows)
        tables["reuse_distribution"].extend(lexicon.reuse_rows)
        tables["ambiguity_distribution"].extend(analyses.ambiguity_rows)
        tables["boundary_distribution"].extend(boundary.rows)
        tables["rule_usage"].extend(rules)
        tables["candidate_scaling"].extend(analyses.candidate_rows)
        tables["document_distribution"].extend(analyses.document_rows)
        tables["length_strata"].extend(analyses.length_rows)
        tables["runtime_breakdown"].extend(runtime)
        evidence.extend(lexicon.evidence)
        evidence.extend(analyses.evidence)
        evidence.extend(boundary.evidence)
        exact_rule_rows = [
            row for row in rules if row.get("family") == "exact_global_rule"
        ]
        for category, ordered_rules in (
            ("common_rules", exact_rule_rows[:EVIDENCE_LIMIT]),
            (
                "low_usage_rules",
                sorted(
                    exact_rule_rows,
                    key=lambda row: (
                        float(row["expected_usage"]),
                        str(row["metric"]),
                    ),
                )[:EVIDENCE_LIMIT],
            ),
        ):
            evidence.extend(
                {
                    "cell_id": cell_id,
                    "category": category,
                    "source_id": str(row["metric"]),
                    "source_artifact": "rule_usage.tsv",
                    "rule_id": row["metric"],
                    "expected_usage": row["expected_usage"],
                    "normalized_usage": row["normalized_usage"],
                }
                for row in ordered_rules
            )
        tables["cells"].append(
            {
                "cell_id": cell_id,
                "script": cell.spec.script,
                "condition": cell.spec.condition,
                "run_id": cell.spec.run_id,
                "metrics_id": cell.spec.metrics_id,
                "scientific_git_sha": cell.spec.scientific_commit,
                "segments": analyses.row_count,
                "surface_phonemes": analyses.phoneme_count,
                "lexical_types": lexicon.row_count,
                "candidate_boundaries": boundary.boundary_count,
                "expected_boundaries": boundary.expected_boundary_total,
                "rules": rule_count,
            }
        )
        row_counts = {
            "iteration_metrics.json": pass_count,
            "summary.json": 1,
            "analyses.jsonl": analyses.row_count,
            "boundary_posteriors.jsonl": boundary.row_count,
            "latent_lexicon.tsv": lexicon.row_count,
            "rule_usage.tsv": rule_count,
            "config.json": 1,
            "checkpoint.json": 1,
            "provenance.json": 1,
            "timing_metrics.json": 1,
            "inspection_report.md": None,
        }
        sources.extend(
            _source_entry(
                cell, name, base=path.parent, row_count=row_counts.get(name)
            )
            for name in SOURCE_FILES
        )
        process_path = cell.spec.metrics_dir / "process_tree_summary.json"
        sources.append(
            {
                "cell_id": cell_id,
                "run_id": cell.spec.run_id,
                "metrics_id": cell.spec.metrics_id,
                "script": cell.spec.script,
                "condition": cell.spec.condition,
                "relative_path": _relative_path(process_path, path.parent),
                "bytes": process_path.stat().st_size,
                "row_count": 1,
                "sha256": _file_sha256(process_path),
                "scientific_git_sha": cell.spec.scientific_commit,
                "artifact_schema_or_header": cell.process.get("schema_version"),
                "config_signature": cell.provenance.get("config_signature"),
            }
        )
        sources.append(
            {
                "cell_id": cell_id,
                "run_id": cell.spec.run_id,
                "metrics_id": cell.spec.metrics_id,
                "script": cell.spec.script,
                "condition": cell.spec.condition,
                "relative_path": _relative_path(cell.spec.audit_path, path.parent),
                "bytes": cell.spec.audit_path.stat().st_size,
                "row_count": 1,
                "sha256": _file_sha256(cell.spec.audit_path),
                "scientific_git_sha": cell.spec.scientific_commit,
                "artifact_schema_or_header": cell.audit.get("schema_version"),
                "config_signature": cell.provenance.get("config_signature"),
                "identity_role": "completed_collection_final_audit",
            }
        )
    tables["pairwise_stability"] = _pairwise_rows(loaded, lexicons, boundaries)
    cross_differences = TopReservoir("cross_condition_metric_differences")
    for row in tables["pairwise_stability"]:
        value = row.get("value")
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            source_id = f"{row['pair_id']}:{row['metric']}"
            cross_differences.add(
                abs(float(value)),
                source_id,
                {
                    "source_artifact": "derived_pairwise_stability",
                    "pair_id": row["pair_id"],
                    "metric": row["metric"],
                    "value": value,
                    "scope": row.get("scope"),
                },
            )
    evidence.extend(cross_differences.rows("cross_cell"))
    evidence.sort(
        key=lambda row: (
            str(row.get("cell_id", "")),
            str(row.get("category", "")),
            str(row.get("source_id", "")),
        )
    )
    retention_manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "post_hoc_descriptive_archival",
        "scientific_scope": (
            "This reduction does not alter, reopen, or replace the frozen "
            "preregistered S1M1 gate."
        ),
        "source_gate_manifest": _relative_path(path, path.parent),
        "source_gate_manifest_sha256": _file_sha256(path),
        "gate_id": manifest_payload["gate_id"],
        "scientific_contract_id": manifest_payload["scientific_contract_id"],
        "approved_scientific_commits": manifest_payload["approved_scientific_commits"],
        "quantile_method": "deterministic_log2_histogram_1/8_octave_midpoint",
        "mass_support_overlap_method": f"deterministic_bottom_{MINHASH_SIZE}_minhash",
        "sources": sources,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "retention_manifest": retention_manifest,
        "tables": tables,
        "evidence_samples": evidence,
    }


def _write_tsv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, ensure_ascii=False, sort_keys=True)
                        if isinstance(value, (dict, list, tuple))
                        else "" if value is None else value
                    )
                    for key, value in row.items()
                }
            )


def render_summary(result: Mapping[str, Any]) -> str:
    tables = _object(result.get("tables"), "archive tables")
    cells = _array(tables.get("cells"), "archive cells")
    lines = [
        "# S1M1 post-hoc archival reduction",
        "",
        "> **Status:** post-hoc descriptive/archival only. This output does not "
        "alter, reopen, or replace the frozen preregistered S1M1 gate.",
        "",
        "All source identities were checked against completed local collections "
        "before streaming reduction. No source artifact was modified.",
        "",
        "| Cell | Segments | Phonemes | Lexical types | Expected boundaries |",
        "|---|---:|---:|---:|---:|",
    ]
    for cell in cells:
        lines.append(
            f"| {cell['cell_id']} | {cell['segments']} | "
            f"{cell['surface_phonemes']} | {cell['lexical_types']} | "
            f"{cell['expected_boundaries']:.6g} |"
        )
    lines.extend(
        (
            "",
            "## Interpretation limits",
            "",
            "- Lexicon and rule totals are exact streaming reductions.",
            "- Reported distribution quantiles use a deterministic bounded-memory "
            "1/8-octave log2 histogram and are explicitly approximate.",
            "- Top-analysis, margin, residual, context, surface-variant, and "
            "per-segment rule diagnostics inherit the bounded inspection top-k "
            "semantics recorded by the training artifact.",
            "- Orthographic spaces and other cues are reference signals, not gold "
            "lexical boundaries.",
            "- Pairwise top-10,000 support comparisons are exact within that retained "
            "head; high-mass-support Jaccard values are bounded MinHash estimates.",
            "",
        )
    )
    return "\n".join(lines)


def write_outputs(result: Mapping[str, Any], output_dir: Path) -> None:
    """Atomically write compact outputs, refusing to overwrite any directory."""

    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    try:
        (temporary / "manifest.json").write_text(
            json.dumps(
                result["retention_manifest"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="",
        )
        tables = _object(result.get("tables"), "archive tables")
        for name in (
            "cells",
            "pass_dynamics",
            "lexicon_distribution",
            "lexical_length",
            "reuse_distribution",
            "ambiguity_distribution",
            "boundary_distribution",
            "rule_usage",
            "candidate_scaling",
            "document_distribution",
            "length_strata",
            "runtime_breakdown",
            "pairwise_stability",
        ):
            _write_tsv(temporary / f"{name}.tsv", _array(tables.get(name), name))
        with (temporary / "evidence_samples.jsonl").open(
            "x", encoding="utf-8", newline=""
        ) as handle:
            for row in _array(result.get("evidence_samples"), "evidence_samples"):
                handle.write(
                    json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                )
        (temporary / "summary.md").write_text(
            render_summary(result), encoding="utf-8", newline=""
        )
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
