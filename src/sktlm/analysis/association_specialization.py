"""Streaming specialization analysis for scorer/association compact state."""

from __future__ import annotations

import csv
import gzip
import hashlib
import heapq
import io
import json
import math
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from sktlm.latent.phonology import Phoneme

from .six_representation_gate import GateValidationError

INPUT_SCHEMA_VERSION = "sktlm-association-specialization-input/v1"
OUTPUT_SCHEMA_VERSION = "sktlm-association-specialization/v1"
COMPACT_SCHEMA_VERSION = "sktlm-s1m1-sqlite-state/v2"
IMPLEMENTATION_ID = "sktlm.analysis.association_specialization:analyze_manifest"
IMPLEMENTATION_FILES = (
    "src/sktlm/analysis/association_specialization.py",
    "scripts/analysis/analyze_association_specialization.py",
)
TABLES = {
    "final_scorer": (
        "final_scorer.tsv.gz",
        ("form_key", "training_expected_count", "probability"),
        "training_expected_count",
    ),
    "surface_usage": (
        "surface_usage.tsv.gz",
        ("form_key", "surface", "expected_mass"),
        "expected_mass",
    ),
    "context_usage": (
        "context_usage.tsv.gz",
        ("form_key", "context", "expected_mass"),
        "expected_mass",
    ),
}
AXIS_METRICS = (
    "top1_share",
    "topk_share",
    "entropy_nats",
    "normalized_entropy",
    "effective_support_shannon",
    "herfindahl",
    "effective_support_simpson",
)
COMPARISON_METRICS = (
    "training_expected_count",
    "probability",
) + tuple(
    f"{axis}_{metric}"
    for axis in ("context", "surface")
    for metric in AXIS_METRICS
)
_VALID_PHONEME_IDS = frozenset(item.value for item in Phoneme)


def _error(message: str) -> GateValidationError:
    return GateValidationError((message,))


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(f"{label} must be a JSON object")
    return value


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error(f"{label} must be a JSON array")
    return value


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{label} must be a nonempty string")
    return value.strip()


def _number(value: object, label: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise _error(f"{label} must be numeric")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise _error(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise _error(f"{label} must be finite")
    if nonnegative and result < 0.0:
        raise _error(f"{label} must be nonnegative")
    return result


def _integer(value: object, label: str, *, positive: bool = False) -> int:
    number = _number(value, label, nonnegative=True)
    result = int(number)
    if number != result or (positive and result <= 0):
        required = "a positive integer" if positive else "an integer"
        raise _error(f"{label} must be {required}")
    return result


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), label)
    except (OSError, json.JSONDecodeError) as exc:
        raise _error(f"{label} is unreadable JSON: {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative_or_absolute(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _implementation_provenance() -> tuple[dict[str, Any], Path]:
    source_path = Path(__file__).resolve()

    def git_output(*arguments: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(source_path.parent), *arguments],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise _error(f"cannot resolve analysis Git provenance: {exc}") from exc
        value = result.stdout.strip()
        if not value:
            raise _error("cannot resolve analysis Git provenance: empty Git output")
        return value

    root = Path(git_output("rev-parse", "--show-toplevel")).resolve()
    commit = git_output("rev-parse", "--verify", "HEAD^{commit}").lower()
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise _error(f"invalid analysis Git commit SHA: {commit!r}")
    files = []
    for relative_path in IMPLEMENTATION_FILES:
        implementation_path = root / relative_path
        if not implementation_path.is_file():
            raise _error(f"analysis implementation file is missing: {implementation_path}")
        files.append(
            {"relative_path": relative_path, "sha256": _sha256(implementation_path)}
        )
    return (
        {
            "git_commit_sha": commit,
            "git_resolution": "resolved_fail_closed",
            "implementation_id": IMPLEMENTATION_ID,
            "implementation_files": files,
        },
        root,
    )


@dataclass(frozen=True, slots=True)
class BinSpec:
    labels: tuple[str, ...]
    upper_bounds: tuple[float, ...]

    def label(self, value: float) -> str:
        for upper, label in zip(self.upper_bounds, self.labels):
            if value <= upper:
                return label
        return self.labels[-1]

    def payload(self) -> dict[str, Any]:
        return {
            "labels": list(self.labels),
            "upper_bounds_inclusive": list(self.upper_bounds),
        }


def _parse_bins(raw: object, label: str, *, integer_bounds: bool) -> BinSpec:
    value = _object(raw, label)
    labels = tuple(
        _nonempty(item, f"{label}.labels")
        for item in _array(value.get("labels"), f"{label}.labels")
    )
    bounds = tuple(
        _number(item, f"{label}.upper_bounds", nonnegative=True)
        for item in _array(value.get("upper_bounds"), f"{label}.upper_bounds")
    )
    if integer_bounds and any(bound != int(bound) or bound < 1 for bound in bounds):
        raise _error(f"{label}.upper_bounds must contain positive integers")
    if not bounds or any(right <= left for left, right in zip(bounds, bounds[1:])):
        raise _error(f"{label}.upper_bounds must be nonempty and strictly increasing")
    if len(labels) != len(bounds) + 1 or len(set(labels)) != len(labels):
        raise _error(
            f"{label}.labels must be unique and have one more item than upper_bounds"
        )
    return BinSpec(labels, bounds)


@dataclass(frozen=True, slots=True)
class CellSpec:
    cell_id: str
    compact_dir: Path
    form_key_namespace: str
    checksum_status: str


@dataclass(frozen=True, slots=True)
class ComparisonSpec:
    comparison_id: str
    cell_a: str
    cell_b: str
    alignment_status: str
    alignment_reason: str | None
    namespace: str | None
    strong_count_increase_ratio: float


@dataclass(frozen=True, slots=True)
class DiagnosticSpec:
    diagnostic_id: str
    comparison_id: str
    target_cell: str
    reference_cell: str
    min_phoneme_length: int
    max_training_expected_count: float
    min_context_top1_share: float
    max_context_effective_support: float
    min_context_top1_delta: float
    limit_per_category: int

    def payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class AnalysisSpec:
    manifest_path: Path
    analysis_id: str
    cells: tuple[CellSpec, ...]
    comparisons: tuple[ComparisonSpec, ...]
    diagnostics: tuple[DiagnosticSpec, ...]
    top_k: int
    length_bins: BinSpec
    count_bins: BinSpec
    compact_schema: str
    exporter_implementation_id: str
    allowed_exporter_commits: frozenset[str]


def _parse_manifest(path: Path) -> AnalysisSpec:
    path = path.resolve()
    raw = _read_json(path, "association-specialization manifest")
    if raw.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise _error(f"schema_version must be {INPUT_SCHEMA_VERSION!r}")
    analysis_id = _nonempty(raw.get("analysis_id"), "analysis_id")
    contract = _object(raw.get("input_contract"), "input_contract")
    compact_schema = _nonempty(
        contract.get("compact_schema_version"),
        "input_contract.compact_schema_version",
    )
    if compact_schema != COMPACT_SCHEMA_VERSION:
        raise _error(f"unsupported compact schema: {compact_schema!r}")
    exporter_id = _nonempty(
        contract.get("exporter_implementation_id"),
        "input_contract.exporter_implementation_id",
    )
    commits = frozenset(
        _nonempty(item, "allowed exporter commit")
        for item in _array(
            contract.get("allowed_exporter_git_commits"),
            "input_contract.allowed_exporter_git_commits",
        )
    )
    if not commits or any(
        len(item) != 40
        or any(character not in "0123456789abcdef" for character in item)
        for item in commits
    ):
        raise _error(
            "allowed_exporter_git_commits must contain full lowercase SHA-1 values"
        )

    cells: list[CellSpec] = []
    cell_ids: set[str] = set()
    for index, item in enumerate(_array(raw.get("cells"), "cells")):
        row = _object(item, f"cells[{index}]")
        cell_id = _nonempty(row.get("cell_id"), f"cells[{index}].cell_id")
        if cell_id in cell_ids:
            raise _error(f"duplicate cell_id: {cell_id}")
        cell_ids.add(cell_id)
        compact_dir = Path(
            _nonempty(row.get("compact_dir"), f"cells[{index}].compact_dir")
        )
        if not compact_dir.is_absolute():
            compact_dir = path.parent / compact_dir
        cells.append(
            CellSpec(
                cell_id,
                compact_dir.resolve(),
                _nonempty(
                    row.get("form_key_namespace"),
                    f"cells[{index}].form_key_namespace",
                ),
                _nonempty(
                    row.get("checksum_status"),
                    f"cells[{index}].checksum_status",
                ),
            )
        )
    if not cells:
        raise _error("cells must not be empty")

    by_cell = {cell.cell_id: cell for cell in cells}
    comparisons: list[ComparisonSpec] = []
    comparison_ids: set[str] = set()
    for index, item in enumerate(_array(raw.get("comparisons", []), "comparisons")):
        row = _object(item, f"comparisons[{index}]")
        comparison_id = _nonempty(
            row.get("comparison_id"), f"comparisons[{index}].comparison_id"
        )
        if comparison_id in comparison_ids:
            raise _error(f"duplicate comparison_id: {comparison_id}")
        comparison_ids.add(comparison_id)
        cell_a = _nonempty(row.get("cell_a"), f"comparisons[{index}].cell_a")
        cell_b = _nonempty(row.get("cell_b"), f"comparisons[{index}].cell_b")
        if cell_a == cell_b or cell_a not in by_cell or cell_b not in by_cell:
            raise _error(
                f"comparison {comparison_id} must reference two distinct declared cells"
            )
        alignment = _object(
            row.get("form_alignment"),
            f"comparisons[{index}].form_alignment",
        )
        status = _nonempty(
            alignment.get("status"),
            f"comparisons[{index}].form_alignment.status",
        )
        reason: str | None = None
        namespace: str | None = None
        if status == "SUPPORTED":
            namespace = _nonempty(
                alignment.get("namespace"),
                f"comparisons[{index}].form_alignment.namespace",
            )
            if (
                by_cell[cell_a].form_key_namespace != namespace
                or by_cell[cell_b].form_key_namespace != namespace
            ):
                raise _error(
                    f"comparison {comparison_id} declares an incompatible "
                    "form-key namespace"
                )
        elif status == "UNSUPPORTED":
            reason = _nonempty(
                alignment.get("reason"),
                f"comparisons[{index}].form_alignment.reason",
            )
        else:
            raise _error(
                f"comparison {comparison_id} has unknown alignment status: {status!r}"
            )
        ratio = _number(
            row.get("strong_count_increase_ratio", 2.0),
            f"comparisons[{index}].strong_count_increase_ratio",
        )
        if ratio <= 1.0:
            raise _error("strong_count_increase_ratio must be greater than 1")
        comparisons.append(
            ComparisonSpec(
                comparison_id,
                cell_a,
                cell_b,
                status,
                reason,
                namespace,
                ratio,
            )
        )

    by_comparison = {item.comparison_id: item for item in comparisons}
    diagnostics: list[DiagnosticSpec] = []
    diagnostic_ids: set[str] = set()
    for index, item in enumerate(_array(raw.get("diagnostics", []), "diagnostics")):
        row = _object(item, f"diagnostics[{index}]")
        diagnostic_id = _nonempty(
            row.get("diagnostic_id"), f"diagnostics[{index}].diagnostic_id"
        )
        if diagnostic_id in diagnostic_ids:
            raise _error(f"duplicate diagnostic_id: {diagnostic_id}")
        diagnostic_ids.add(diagnostic_id)
        comparison_id = _nonempty(
            row.get("comparison_id"), f"diagnostics[{index}].comparison_id"
        )
        comparison = by_comparison.get(comparison_id)
        if comparison is None or comparison.alignment_status != "SUPPORTED":
            raise _error(
                f"diagnostic {diagnostic_id} requires a supported comparison"
            )
        target = _nonempty(
            row.get("target_cell"), f"diagnostics[{index}].target_cell"
        )
        reference = _nonempty(
            row.get("reference_cell"), f"diagnostics[{index}].reference_cell"
        )
        if {target, reference} != {comparison.cell_a, comparison.cell_b}:
            raise _error(
                f"diagnostic {diagnostic_id} endpoints differ from its comparison"
            )
        diagnostic = DiagnosticSpec(
                diagnostic_id,
                comparison_id,
                target,
                reference,
                _integer(
                    row.get("min_phoneme_length"),
                    f"diagnostics[{index}].min_phoneme_length",
                    positive=True,
                ),
                _number(
                    row.get("max_training_expected_count"),
                    f"diagnostics[{index}].max_training_expected_count",
                    nonnegative=True,
                ),
                _number(
                    row.get("min_context_top1_share"),
                    f"diagnostics[{index}].min_context_top1_share",
                    nonnegative=True,
                ),
                _number(
                    row.get("max_context_effective_support"),
                    f"diagnostics[{index}].max_context_effective_support",
                    nonnegative=True,
                ),
                _number(
                    row.get("min_context_top1_delta"),
                    f"diagnostics[{index}].min_context_top1_delta",
                    nonnegative=True,
                ),
                _integer(
                    row.get("limit_per_category"),
                    f"diagnostics[{index}].limit_per_category",
                    positive=True,
                ),
            )
        if diagnostic.min_context_top1_share > 1.0:
            raise _error(
                f"diagnostics[{index}].min_context_top1_share must not exceed one"
            )
        if diagnostic.min_context_top1_delta > 1.0:
            raise _error(
                f"diagnostics[{index}].min_context_top1_delta must not exceed one"
            )
        if diagnostic.max_context_effective_support < 1.0:
            raise _error(
                f"diagnostics[{index}].max_context_effective_support must be at least one"
            )
        diagnostics.append(diagnostic)

    parameters = _object(raw.get("parameters"), "parameters")
    bins = _object(parameters.get("bins"), "parameters.bins")
    return AnalysisSpec(
        path,
        analysis_id,
        tuple(cells),
        tuple(comparisons),
        tuple(diagnostics),
        _integer(
            parameters.get("association_top_k"),
            "parameters.association_top_k",
            positive=True,
        ),
        _parse_bins(
            bins.get("phoneme_length"),
            "parameters.bins.phoneme_length",
            integer_bounds=True,
        ),
        _parse_bins(
            bins.get("training_expected_count"),
            "parameters.bins.training_expected_count",
            integer_bounds=False,
        ),
        compact_schema,
        exporter_id,
        commits,
    )


def _parse_checksum_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise _error(f"cannot read checksum manifest: {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        parts = line.split("  ", 1)
        if (
            len(parts) != 2
            or len(parts[0]) != 64
            or any(c not in "0123456789abcdef" for c in parts[0])
        ):
            raise _error(f"invalid SHA256SUMS row at {path}:{line_number}")
        name = parts[1]
        if not name or name in result or Path(name).name != name:
            raise _error(
                f"invalid/duplicate SHA256SUMS name at {path}:{line_number}"
            )
        result[name] = parts[0]
    return result


@dataclass(frozen=True, slots=True)
class CompactInput:
    spec: CellSpec
    manifest: Mapping[str, Any]
    table_identity: Mapping[str, Mapping[str, Any]]
    provenance: Mapping[str, Any]
    manifest_sha256: str
    checksums_sha256: str

    @classmethod
    def load(cls, spec: CellSpec, analysis: AnalysisSpec) -> "CompactInput":
        root = spec.compact_dir
        manifest_path = root / "manifest.json"
        checksums_path = root / "SHA256SUMS"
        manifest = _read_json(manifest_path, f"{spec.cell_id} compact manifest")
        if manifest.get("schema_version") != analysis.compact_schema:
            raise _error(f"{spec.cell_id}: compact schema mismatch")
        if manifest.get("cell_id") != spec.cell_id:
            raise _error(f"{spec.cell_id}: compact manifest cell_id mismatch")
        consistency = _object(
            manifest.get("consistency"), f"{spec.cell_id}.consistency"
        )
        if not consistency or not all(value is True for value in consistency.values()):
            raise _error(
                f"{spec.cell_id}: compact consistency checks are not all true"
            )
        exporter = _object(
            manifest.get("exporter_provenance"),
            f"{spec.cell_id}.exporter_provenance",
        )
        if exporter.get("implementation_id") != analysis.exporter_implementation_id:
            raise _error(
                f"{spec.cell_id}: exporter implementation identity mismatch"
            )
        if exporter.get("git_commit_sha") not in analysis.allowed_exporter_commits:
            raise _error(f"{spec.cell_id}: exporter Git commit is not allowed")

        artifacts: dict[str, Mapping[str, Any]] = {}
        for item in _array(
            manifest.get("compact_artifacts"),
            f"{spec.cell_id}.compact_artifacts",
        ):
            row = _object(item, f"{spec.cell_id}.compact_artifacts[]")
            name = _nonempty(
                row.get("name"), f"{spec.cell_id} compact artifact name"
            )
            if name in artifacts:
                raise _error(f"{spec.cell_id}: duplicate compact artifact {name}")
            artifacts[name] = row
        required_names = {value[0] for value in TABLES.values()}
        if set(artifacts) != required_names:
            raise _error(
                f"{spec.cell_id}: compact artifact set must be exactly "
                f"{sorted(required_names)}"
            )
        sums = _parse_checksum_file(checksums_path)
        if set(sums) != required_names | {"manifest.json"}:
            raise _error(f"{spec.cell_id}: SHA256SUMS file set is not exact")
        manifest_sha = _sha256(manifest_path)
        if sums["manifest.json"] != manifest_sha:
            raise _error(f"{spec.cell_id}: compact manifest SHA-256 mismatch")

        readback = _object(manifest.get("readback"), f"{spec.cell_id}.readback")
        table_identity: dict[str, Mapping[str, Any]] = {}
        for table, (filename, _fields, numeric_field) in TABLES.items():
            artifact = artifacts[filename]
            table_path = root / filename
            if not table_path.is_file():
                raise _error(f"{spec.cell_id}: missing compact table: {table_path}")
            size = _integer(
                artifact.get("size_bytes"), f"{spec.cell_id} {filename} size"
            )
            sha = _nonempty(
                artifact.get("sha256"), f"{spec.cell_id} {filename} sha256"
            )
            if table_path.stat().st_size != size:
                raise _error(
                    f"{spec.cell_id}: compact table size mismatch: {filename}"
                )
            if sums[filename] != sha:
                raise _error(
                    f"{spec.cell_id}: compact hash identities disagree: {filename}"
                )
            table_readback = _object(
                readback.get(table), f"{spec.cell_id}.readback.{table}"
            )
            table_identity[table] = {
                "filename": filename,
                "size_bytes": size,
                "sha256": sha,
                "rows": _integer(
                    table_readback.get("rows"), f"{spec.cell_id} {table} rows"
                ),
                f"sum_{numeric_field}": _number(
                    table_readback.get(f"sum_{numeric_field}"),
                    f"{spec.cell_id} {table} mass",
                    nonnegative=True,
                ),
            }
        return cls(
            spec,
            manifest,
            table_identity,
            exporter,
            manifest_sha,
            _sha256(checksums_path),
        )

    def identity_payload(self, repository_root: Path) -> dict[str, Any]:
        return {
            "cell_id": self.spec.cell_id,
            "compact_dir": _relative_or_absolute(
                self.spec.compact_dir, repository_root
            ),
            "compact_schema_version": self.manifest["schema_version"],
            "compact_manifest_sha256": self.manifest_sha256,
            "sha256sums_sha256": self.checksums_sha256,
            "checksum_status": self.spec.checksum_status,
            "payload_hash_validation": (
                "referenced_from_preverified_SHA256SUMS_not_recomputed"
            ),
            "form_key_namespace": self.spec.form_key_namespace,
            "exporter_provenance": self.provenance,
            "tables": self.table_identity,
        }


@dataclass(slots=True)
class CompensatedSum:
    total: float = 0.0
    compensation: float = 0.0

    def add(self, value: float) -> None:
        adjusted = value - self.compensation
        updated = self.total + adjusted
        self.compensation = (updated - self.total) - adjusted
        self.total = updated


@dataclass(frozen=True, slots=True)
class AxisMetrics:
    association_rows: int
    observed_support: int
    total_expected_mass: float
    top1_share: float | None
    topk_share: float | None
    entropy_nats: float | None
    normalized_entropy: float | None
    effective_support_shannon: float | None
    herfindahl: float | None
    effective_support_simpson: float | None
    top_items: tuple[tuple[str, float, float], ...]

    def metric(self, name: str) -> float | None:
        return getattr(self, name)


@dataclass(frozen=True, slots=True)
class FormMetrics:
    cell_id: str
    form_key: str
    phoneme_length: int
    training_expected_count: float | None
    probability: float | None
    context: AxisMetrics
    surface: AxisMetrics


def _empty_axis() -> AxisMetrics:
    return AxisMetrics(0, 0, 0.0, None, None, None, None, None, None, None, ())


class _ScorerStream:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = gzip.open(path, "rt", encoding="utf-8", newline="")
        self.reader = csv.reader(self.handle, delimiter="\t")
        try:
            header = tuple(next(self.reader))
        except StopIteration as exc:
            raise _error(f"empty scorer table: {path}") from exc
        if header != TABLES["final_scorer"][1]:
            raise _error(f"unexpected scorer header in {path}: {header}")
        self.previous_key = ""
        self.row_count = 0
        self.count_total = CompensatedSum()
        self.probability_total = CompensatedSum()

    def __iter__(self) -> "_ScorerStream":
        return self

    def __next__(self) -> tuple[str, float, float]:
        row = next(self.reader)
        line = self.row_count + 2
        if len(row) != 3:
            raise _error(f"{self.path}:{line}: scorer row must have three fields")
        key = row[0]
        if not key or (self.previous_key and key <= self.previous_key):
            raise _error(
                f"{self.path}:{line}: scorer form_key order is not strictly increasing"
            )
        count = _number(
            row[1], f"{self.path}:{line} training_expected_count", nonnegative=True
        )
        probability = _number(
            row[2], f"{self.path}:{line} probability", nonnegative=True
        )
        if probability > 1.0 + 1e-12:
            raise _error(f"{self.path}:{line}: probability exceeds one")
        self.previous_key = key
        self.row_count += 1
        self.count_total.add(count)
        self.probability_total.add(probability)
        return key, count, probability

    def close(self) -> None:
        self.handle.close()


class _AssociationStream:
    def __init__(self, path: Path, axis: str, top_k: int) -> None:
        self.path = path
        self.axis = axis
        self.top_k = top_k
        self.handle = gzip.open(path, "rt", encoding="utf-8", newline="")
        self.reader = csv.reader(self.handle, delimiter="\t")
        try:
            header = tuple(next(self.reader))
        except StopIteration as exc:
            raise _error(f"empty association table: {path}") from exc
        if header != TABLES[f"{axis}_usage"][1]:
            raise _error(f"unexpected {axis} header in {path}: {header}")
        self.buffer: tuple[str, str, float] | None = None
        self.previous_pair: tuple[str, str] | None = None
        self.row_count = 0
        self.mass_total = CompensatedSum()

    def _read(self) -> tuple[str, str, float] | None:
        try:
            row = next(self.reader)
        except StopIteration:
            return None
        line = self.row_count + 2
        if len(row) != 3:
            raise _error(
                f"{self.path}:{line}: association row must have three fields"
            )
        key, item = row[0], row[1]
        if not key or not item:
            raise _error(
                f"{self.path}:{line}: form_key and association value must be nonempty"
            )
        pair = (key, item)
        if self.previous_pair is not None and pair <= self.previous_pair:
            detail = (
                "duplicate pair" if pair == self.previous_pair else "input is not sorted"
            )
            raise _error(
                f"{self.path}:{line}: {detail} for ({key!r}, {item!r})"
            )
        mass = _number(
            row[2], f"{self.path}:{line} expected_mass", nonnegative=True
        )
        self.previous_pair = pair
        self.row_count += 1
        self.mass_total.add(mass)
        return key, item, mass

    def __iter__(self) -> "_AssociationStream":
        return self

    def __next__(self) -> tuple[str, AxisMetrics]:
        first = self.buffer if self.buffer is not None else self._read()
        self.buffer = None
        if first is None:
            raise StopIteration
        key = first[0]
        rows = support = 0
        total = CompensatedSum()
        mass_log_mass = CompensatedSum()
        square_mass = CompensatedSum()
        top: list[tuple[float, str]] = []
        current: tuple[str, str, float] | None = first
        while current is not None and current[0] == key:
            _, item, mass = current
            rows += 1
            total.add(mass)
            if mass > 0.0:
                support += 1
                mass_log_mass.add(mass * math.log(mass))
                square_mass.add(mass * mass)
                candidate = (mass, item)
                if len(top) < self.top_k:
                    heapq.heappush(top, candidate)
                elif candidate > top[0]:
                    heapq.heapreplace(top, candidate)
            current = self._read()
        self.buffer = current
        if total.total <= 0.0:
            return key, AxisMetrics(
                rows, 0, 0.0, None, None, None, None, None, None, None, ()
            )

        entropy = math.log(total.total) - mass_log_mass.total / total.total
        if entropy < -1e-10:
            raise _error(
                f"{self.path}: negative entropy for form_key {key!r}: {entropy}"
            )
        entropy = max(0.0, entropy)
        herfindahl = square_mass.total / (total.total * total.total)
        top_rows = sorted(top, reverse=True)
        top1 = top_rows[0][0] / total.total
        topk = sum(item[0] for item in top_rows) / total.total
        normalized = 0.0 if support == 1 else entropy / math.log(support)
        shannon_support = math.exp(entropy)
        simpson_support = 1.0 / herfindahl
        for label, value in (
            ("top1", top1),
            ("topk", topk),
            ("normalized entropy", normalized),
            ("Herfindahl", herfindahl),
        ):
            if value < -1e-10 or value > 1.0 + 1e-10:
                raise _error(
                    f"{self.path}: {label} out of range for {key!r}: {value}"
                )
        if shannon_support < 1.0 - 1e-10 or simpson_support < 1.0 - 1e-10:
            raise _error(
                f"{self.path}: effective support below one for form_key {key!r}"
            )
        top_items = tuple(
            (item, mass, mass / total.total) for mass, item in top_rows
        )
        return key, AxisMetrics(
            rows,
            support,
            total.total,
            min(1.0, max(0.0, top1)),
            min(1.0, max(0.0, topk)),
            entropy,
            min(1.0, max(0.0, normalized)),
            max(1.0, shannon_support),
            min(1.0, max(0.0, herfindahl)),
            max(1.0, simpson_support),
            top_items,
        )

    def close(self) -> None:
        self.handle.close()


def _next_or_none(iterator: Iterator[Any]) -> Any | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


def _phoneme_length(form_key: str, label: str) -> int:
    parts = form_key.split(".")
    if not parts or any(part not in _VALID_PHONEME_IDS for part in parts):
        raise _error(
            f"{label}: invalid script-neutral phonological form_key {form_key!r}"
        )
    return len(parts)


class CellFormStream:
    def __init__(self, compact: CompactInput, top_k: int) -> None:
        self.compact = compact
        root = compact.spec.compact_dir
        self.scorer = _ScorerStream(root / TABLES["final_scorer"][0])
        self.surface = _AssociationStream(
            root / TABLES["surface_usage"][0], "surface", top_k
        )
        self.context = _AssociationStream(
            root / TABLES["context_usage"][0], "context", top_k
        )
        self.scorer_current = _next_or_none(self.scorer)
        self.surface_current = _next_or_none(self.surface)
        self.context_current = _next_or_none(self.context)
        self.complete = False

    def __iter__(self) -> "CellFormStream":
        return self

    def __next__(self) -> FormMetrics:
        values = [
            item[0]
            for item in (
                self.scorer_current,
                self.surface_current,
                self.context_current,
            )
            if item is not None
        ]
        if not values:
            if not self.complete:
                self._validate_complete()
                self.complete = True
            raise StopIteration
        key = min(values)
        scorer = (
            self.scorer_current
            if self.scorer_current is not None and self.scorer_current[0] == key
            else None
        )
        surface = (
            self.surface_current
            if self.surface_current is not None and self.surface_current[0] == key
            else None
        )
        context = (
            self.context_current
            if self.context_current is not None and self.context_current[0] == key
            else None
        )
        if scorer is not None:
            self.scorer_current = _next_or_none(self.scorer)
        if surface is not None:
            self.surface_current = _next_or_none(self.surface)
        if context is not None:
            self.context_current = _next_or_none(self.context)
        return FormMetrics(
            self.compact.spec.cell_id,
            key,
            _phoneme_length(key, self.compact.spec.cell_id),
            None if scorer is None else scorer[1],
            None if scorer is None else scorer[2],
            _empty_axis() if context is None else context[1],
            _empty_axis() if surface is None else surface[1],
        )

    def _validate_complete(self) -> None:
        for table, stream, total_name in (
            ("final_scorer", self.scorer, "count_total"),
            ("surface_usage", self.surface, "mass_total"),
            ("context_usage", self.context, "mass_total"),
        ):
            identity = self.compact.table_identity[table]
            if stream.row_count != identity["rows"]:
                raise _error(
                    f"{self.compact.spec.cell_id}: {table} row count differs "
                    "from compact manifest"
                )
            field = TABLES[table][2]
            actual = getattr(stream, total_name).total
            if not math.isclose(
                actual,
                float(identity[f"sum_{field}"]),
                rel_tol=1e-10,
                abs_tol=1e-6,
            ):
                raise _error(
                    f"{self.compact.spec.cell_id}: {table} mass differs from "
                    "compact manifest"
                )
        database = _object(
            _object(self.compact.manifest.get("statistics"), "statistics").get(
                "database"
            ),
            "statistics.database",
        )
        scorer_stats = _object(
            database.get("final_scorer"), "statistics.database.final_scorer"
        )
        expected_probability = _number(
            scorer_stats.get("database_probability_sum"),
            "database_probability_sum",
            nonnegative=True,
        )
        if not math.isclose(
            self.scorer.probability_total.total,
            expected_probability,
            rel_tol=1e-10,
            abs_tol=1e-8,
        ):
            raise _error(
                f"{self.compact.spec.cell_id}: scorer probability sum differs "
                "from compact manifest"
            )

    def close(self) -> None:
        self.scorer.close()
        self.surface.close()
        self.context.close()


@dataclass(slots=True)
class MetricAggregate:
    eligible_forms: int = 0
    type_sum: CompensatedSum = field(default_factory=CompensatedSum)
    training_weight: CompensatedSum = field(default_factory=CompensatedSum)
    training_weighted_sum: CompensatedSum = field(default_factory=CompensatedSum)
    association_weight: CompensatedSum = field(default_factory=CompensatedSum)
    association_weighted_sum: CompensatedSum = field(default_factory=CompensatedSum)

    def add(
        self,
        value: float | None,
        training_count: float | None,
        association_mass: float,
    ) -> None:
        if value is None:
            return
        self.eligible_forms += 1
        self.type_sum.add(value)
        if training_count is not None and training_count > 0.0:
            self.training_weight.add(training_count)
            self.training_weighted_sum.add(training_count * value)
        if association_mass > 0.0:
            self.association_weight.add(association_mass)
            self.association_weighted_sum.add(association_mass * value)

    def payload(self) -> dict[str, Any]:
        return {
            "eligible_forms": self.eligible_forms,
            "type_mean": (
                None
                if not self.eligible_forms
                else self.type_sum.total / self.eligible_forms
            ),
            "training_expected_count_weight": self.training_weight.total,
            "training_expected_count_weighted_mean": (
                None
                if self.training_weight.total <= 0.0
                else self.training_weighted_sum.total / self.training_weight.total
            ),
            "association_expected_mass_weight": self.association_weight.total,
            "association_expected_mass_weighted_mean": (
                None
                if self.association_weight.total <= 0.0
                else self.association_weighted_sum.total
                / self.association_weight.total
            ),
        }


@dataclass(slots=True)
class AxisAccumulator:
    forms_with_rows: int = 0
    forms_with_positive_support: int = 0
    association_rows: int = 0
    total_expected_mass: CompensatedSum = field(default_factory=CompensatedSum)
    metrics: dict[str, MetricAggregate] = field(
        default_factory=lambda: {name: MetricAggregate() for name in AXIS_METRICS}
    )

    def add(self, axis: AxisMetrics, training_count: float | None) -> None:
        if axis.association_rows:
            self.forms_with_rows += 1
        if axis.observed_support:
            self.forms_with_positive_support += 1
        self.association_rows += axis.association_rows
        self.total_expected_mass.add(axis.total_expected_mass)
        if not axis.observed_support:
            return
        for name in AXIS_METRICS:
            self.metrics[name].add(
                axis.metric(name), training_count, axis.total_expected_mass
            )

    def payload(self) -> dict[str, Any]:
        return {
            "forms_with_rows": self.forms_with_rows,
            "forms_with_positive_support": self.forms_with_positive_support,
            "association_rows": self.association_rows,
            "total_expected_mass": self.total_expected_mass.total,
            "metrics": {
                name: self.metrics[name].payload() for name in AXIS_METRICS
            },
        }


@dataclass(slots=True)
class Bucket:
    forms_total: int = 0
    forms_with_training_count: int = 0
    training_expected_count_total: CompensatedSum = field(
        default_factory=CompensatedSum
    )
    context: AxisAccumulator = field(default_factory=AxisAccumulator)
    surface: AxisAccumulator = field(default_factory=AxisAccumulator)

    def add(self, form: FormMetrics) -> None:
        self.forms_total += 1
        if form.training_expected_count is not None:
            self.forms_with_training_count += 1
            self.training_expected_count_total.add(form.training_expected_count)
        self.context.add(form.context, form.training_expected_count)
        self.surface.add(form.surface, form.training_expected_count)

    def payload(self) -> dict[str, Any]:
        return {
            "forms_total": self.forms_total,
            "forms_with_training_count": self.forms_with_training_count,
            "training_expected_count_total": self.training_expected_count_total.total,
            "context": self.context.payload(),
            "surface": self.surface.payload(),
        }


@dataclass(slots=True)
class WeightedCorrelation:
    observations: int = 0
    weight_sum: float = 0.0
    mean_x: float = 0.0
    mean_y: float = 0.0
    sum_xx: float = 0.0
    sum_yy: float = 0.0
    sum_xy: float = 0.0

    def add(self, x: float, y: float, weight: float) -> None:
        if weight <= 0.0:
            return
        self.observations += 1
        new_weight = self.weight_sum + weight
        dx = x - self.mean_x
        dy = y - self.mean_y
        new_mean_x = self.mean_x + weight * dx / new_weight
        new_mean_y = self.mean_y + weight * dy / new_weight
        self.sum_xx += weight * dx * (x - new_mean_x)
        self.sum_yy += weight * dy * (y - new_mean_y)
        self.sum_xy += weight * dx * (y - new_mean_y)
        self.mean_x = new_mean_x
        self.mean_y = new_mean_y
        self.weight_sum = new_weight

    def pearson(self) -> float | None:
        denominator = math.sqrt(
            max(0.0, self.sum_xx) * max(0.0, self.sum_yy)
        )
        if self.observations < 2 or denominator == 0.0:
            return None
        return self.sum_xy / denominator


@dataclass(slots=True)
class CellAccumulator:
    cell_id: str
    all_forms: Bucket = field(default_factory=Bucket)
    length: dict[str, Bucket] = field(
        default_factory=lambda: defaultdict(Bucket)
    )
    count: dict[str, Bucket] = field(
        default_factory=lambda: defaultdict(Bucket)
    )
    joint: dict[tuple[str, str], Bucket] = field(
        default_factory=lambda: defaultdict(Bucket)
    )
    relationships: dict[
        tuple[str, str, str, str], WeightedCorrelation
    ] = field(default_factory=lambda: defaultdict(WeightedCorrelation))

    def add(self, form: FormMetrics, length_bin: str, count_bin: str) -> None:
        self.all_forms.add(form)
        self.length[length_bin].add(form)
        self.count[count_bin].add(form)
        self.joint[(length_bin, count_bin)].add(form)
        predictors: list[tuple[str, float]] = [
            ("phoneme_length", float(form.phoneme_length))
        ]
        if form.training_expected_count is not None:
            predictors.append(
                (
                    "log1p_training_expected_count",
                    math.log1p(form.training_expected_count),
                )
            )
        for predictor, x in predictors:
            for axis_name, axis in (
                ("context", form.context),
                ("surface", form.surface),
            ):
                if not axis.observed_support:
                    continue
                for metric in AXIS_METRICS:
                    y = axis.metric(metric)
                    if y is None:
                        continue
                    self.relationships[
                        (predictor, axis_name, metric, "type")
                    ].add(x, y, 1.0)
                    if form.training_expected_count is not None:
                        self.relationships[
                            (
                                predictor,
                                axis_name,
                                metric,
                                "training_expected_count",
                            )
                        ].add(x, y, form.training_expected_count)


@dataclass(slots=True)
class DeltaAggregate:
    eligible_forms: int = 0
    type_sum: CompensatedSum = field(default_factory=CompensatedSum)
    a_weight: CompensatedSum = field(default_factory=CompensatedSum)
    a_weighted_sum: CompensatedSum = field(default_factory=CompensatedSum)
    b_weight: CompensatedSum = field(default_factory=CompensatedSum)
    b_weighted_sum: CompensatedSum = field(default_factory=CompensatedSum)

    def add(
        self,
        delta: float | None,
        a_count: float | None,
        b_count: float | None,
    ) -> None:
        if delta is None:
            return
        self.eligible_forms += 1
        self.type_sum.add(delta)
        if a_count is not None and a_count > 0.0:
            self.a_weight.add(a_count)
            self.a_weighted_sum.add(a_count * delta)
        if b_count is not None and b_count > 0.0:
            self.b_weight.add(b_count)
            self.b_weighted_sum.add(b_count * delta)

    def payload(self) -> dict[str, Any]:
        return {
            "eligible_forms": self.eligible_forms,
            "type_mean_delta": (
                None
                if not self.eligible_forms
                else self.type_sum.total / self.eligible_forms
            ),
            "cell_a_training_mass": self.a_weight.total,
            "cell_a_training_mass_weighted_mean_delta": (
                None
                if self.a_weight.total <= 0.0
                else self.a_weighted_sum.total / self.a_weight.total
            ),
            "cell_b_training_mass": self.b_weight.total,
            "cell_b_training_mass_weighted_mean_delta": (
                None
                if self.b_weight.total <= 0.0
                else self.b_weighted_sum.total / self.b_weight.total
            ),
        }


def _metric_value(form: FormMetrics, name: str) -> float | None:
    if name in {"training_expected_count", "probability"}:
        return getattr(form, name)
    axis_name, metric = name.split("_", 1)
    return getattr(form, axis_name).metric(metric)


@dataclass(slots=True)
class ComparisonAccumulator:
    spec: ComparisonSpec
    membership_counts: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    membership_a_mass: dict[str, CompensatedSum] = field(
        default_factory=lambda: defaultdict(CompensatedSum)
    )
    membership_b_mass: dict[str, CompensatedSum] = field(
        default_factory=lambda: defaultdict(CompensatedSum)
    )
    deltas: dict[str, DeltaAggregate] = field(
        default_factory=lambda: {
            name: DeltaAggregate() for name in COMPARISON_METRICS
        }
    )
    strata: dict[tuple[str, str], Bucket] = field(
        default_factory=lambda: defaultdict(Bucket)
    )
    output_rows: int = 0

    def add(
        self, a: FormMetrics | None, b: FormMetrics | None
    ) -> str:
        if a is not None and b is not None:
            membership = "shared"
        elif a is not None:
            membership = "cell_a_only"
        else:
            membership = "cell_b_only"
        self.membership_counts[membership] += 1
        if a is not None:
            self.strata[(membership, "cell_a")].add(a)
            if a.training_expected_count is not None:
                self.membership_a_mass[membership].add(
                    a.training_expected_count
                )
        if b is not None:
            self.strata[(membership, "cell_b")].add(b)
            if b.training_expected_count is not None:
                self.membership_b_mass[membership].add(
                    b.training_expected_count
                )
        if a is not None and b is not None:
            for name in COMPARISON_METRICS:
                av, bv = _metric_value(a, name), _metric_value(b, name)
                delta = None if av is None or bv is None else bv - av
                self.deltas[name].add(
                    delta,
                    a.training_expected_count,
                    b.training_expected_count,
                )
            if self._stronger(b.training_expected_count, a.training_expected_count):
                self.strata[
                    ("shared_cell_b_strong_count_increase", "cell_a")
                ].add(a)
                self.strata[
                    ("shared_cell_b_strong_count_increase", "cell_b")
                ].add(b)
            if self._stronger(a.training_expected_count, b.training_expected_count):
                self.strata[
                    ("shared_cell_a_strong_count_increase", "cell_a")
                ].add(a)
                self.strata[
                    ("shared_cell_a_strong_count_increase", "cell_b")
                ].add(b)
        self.output_rows += 1
        return membership

    def _stronger(
        self, current: float | None, reference: float | None
    ) -> bool:
        return (
            current is not None
            and reference is not None
            and current > reference
            and current >= self.spec.strong_count_increase_ratio * reference
        )

    def payload(self) -> dict[str, Any]:
        return {
            "comparison_id": self.spec.comparison_id,
            "direction": "cell_b_minus_cell_a",
            "cell_a": self.spec.cell_a,
            "cell_b": self.spec.cell_b,
            "form_alignment": {
                "status": self.spec.alignment_status,
                "reason": self.spec.alignment_reason,
                "namespace": self.spec.namespace,
            },
            "membership": {
                name: {
                    "forms": self.membership_counts[name],
                    "cell_a_training_expected_count": (
                        self.membership_a_mass[name].total
                    ),
                    "cell_b_training_expected_count": (
                        self.membership_b_mass[name].total
                    ),
                }
                for name in ("shared", "cell_a_only", "cell_b_only")
            },
            "matched_deltas": {
                name: self.deltas[name].payload()
                for name in COMPARISON_METRICS
            },
            "strong_count_increase_ratio": (
                self.spec.strong_count_increase_ratio
            ),
        }


def _top_items_json(axis: AxisMetrics) -> str:
    return json.dumps(
        [
            {"value": item, "expected_mass": mass, "share": share}
            for item, mass, share in axis.top_items
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _diagnostic_payload(
    spec: DiagnosticSpec,
    category: str,
    target: FormMetrics,
    reference: FormMetrics | None,
    primary: float,
    selection_tuple: tuple[float, ...],
) -> dict[str, Any]:
    def value(
        form: FormMetrics | None, axis: str, metric: str
    ) -> float | None:
        return (
            None
            if form is None
            else getattr(form, axis).metric(metric)
        )

    delta = (
        None
        if reference is None
        or reference.context.top1_share is None
        or target.context.top1_share is None
        else target.context.top1_share - reference.context.top1_share
    )
    return {
        "diagnostic_id": spec.diagnostic_id,
        "category": category,
        "form_key": target.form_key,
        "target_cell": spec.target_cell,
        "reference_cell": spec.reference_cell,
        "phoneme_length": target.phoneme_length,
        "target_training_expected_count": target.training_expected_count,
        "reference_training_expected_count": (
            None if reference is None else reference.training_expected_count
        ),
        "target_context_top1_share": target.context.top1_share,
        "reference_context_top1_share": value(
            reference, "context", "top1_share"
        ),
        "delta_context_top1_share": delta,
        "target_context_entropy_nats": target.context.entropy_nats,
        "reference_context_entropy_nats": value(
            reference, "context", "entropy_nats"
        ),
        "target_context_effective_support": (
            target.context.effective_support_shannon
        ),
        "reference_context_effective_support": value(
            reference, "context", "effective_support_shannon"
        ),
        "target_surface_top1_share": target.surface.top1_share,
        "reference_surface_top1_share": value(
            reference, "surface", "top1_share"
        ),
        "target_surface_effective_support": (
            target.surface.effective_support_shannon
        ),
        "reference_surface_effective_support": value(
            reference, "surface", "effective_support_shannon"
        ),
        "target_top_contexts_json": _top_items_json(target.context),
        "reference_top_contexts_json": (
            "[]" if reference is None else _top_items_json(reference.context)
        ),
        "target_top_surfaces_json": _top_items_json(target.surface),
        "reference_top_surfaces_json": (
            "[]" if reference is None else _top_items_json(reference.surface)
        ),
        "selection_primary_score": primary,
        "selection_tuple_json": json.dumps(
            selection_tuple, separators=(",", ":")
        ),
    }


@dataclass(slots=True)
class DiagnosticReservoir:
    spec: DiagnosticSpec
    categories: dict[
        str, list[tuple[tuple[float, ...], str, dict[str, Any]]]
    ] = field(default_factory=lambda: defaultdict(list))

    def _base_filter(self, target: FormMetrics) -> bool:
        return (
            target.training_expected_count is not None
            and target.phoneme_length >= self.spec.min_phoneme_length
            and target.training_expected_count
            <= self.spec.max_training_expected_count
            and target.context.top1_share is not None
            and target.context.effective_support_shannon is not None
            and target.context.top1_share
            >= self.spec.min_context_top1_share
            and target.context.effective_support_shannon
            <= self.spec.max_context_effective_support
        )

    def consider(
        self,
        a: FormMetrics | None,
        b: FormMetrics | None,
        comparison: ComparisonSpec,
    ) -> None:
        target = a if self.spec.target_cell == comparison.cell_a else b
        reference = b if self.spec.reference_cell == comparison.cell_b else a
        if target is None or not self._base_filter(target):
            return
        if reference is None:
            category = "target_only_specialized"
            primary = target.context.top1_share or 0.0
        else:
            if reference.context.top1_share is None:
                return
            delta = (
                (target.context.top1_share or 0.0)
                - reference.context.top1_share
            )
            if delta < self.spec.min_context_top1_delta:
                return
            category = "shared_more_specialized"
            primary = delta
        assert target.context.effective_support_shannon is not None
        assert target.training_expected_count is not None
        selection_tuple = (
            primary,
            target.context.top1_share or 0.0,
            -target.context.effective_support_shannon,
            float(target.phoneme_length),
            -target.training_expected_count,
        )
        payload = _diagnostic_payload(
            self.spec,
            category,
            target,
            reference,
            primary,
            selection_tuple,
        )
        rows = self.categories[category]
        item = (selection_tuple, target.form_key, payload)
        if len(rows) < self.spec.limit_per_category:
            heapq.heappush(rows, item)
        elif item[:2] > rows[0][:2]:
            heapq.heapreplace(rows, item)

    def rows(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for category in (
            "shared_more_specialized",
            "target_only_specialized",
        ):
            ordered = sorted(
                self.categories.get(category, ()), reverse=True
            )
            for rank, (_selection, _key, payload) in enumerate(
                ordered, start=1
            ):
                result.append({**payload, "selection_rank": rank})
        return result


class _DigestSink:
    def __init__(self, path: Path) -> None:
        self.handle = path.open("xb")
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, data: bytes) -> int:
        self.digest.update(data)
        written = self.handle.write(data)
        self.size += written
        return written

    def flush(self) -> None:
        self.handle.flush()

    def tell(self) -> int:
        return self.handle.tell()

    def close(self) -> None:
        self.handle.close()


class GzipTsvWriter:
    def __init__(self, path: Path, fields: Sequence[str]) -> None:
        self.path = path
        self.fields = tuple(fields)
        self.sink: _DigestSink | None = None
        self.text: io.TextIOWrapper | None = None
        self.writer: csv.DictWriter[str] | None = None
        self.sha256: str | None = None
        self.size_bytes: int | None = None

    def __enter__(self) -> "GzipTsvWriter":
        self.sink = _DigestSink(self.path)
        compressed = gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=6,
            fileobj=self.sink,
            mtime=0,
        )
        self.text = io.TextIOWrapper(
            compressed, encoding="utf-8", newline=""
        )
        self.writer = csv.DictWriter(
            self.text,
            fieldnames=self.fields,
            delimiter="\t",
            lineterminator="\n",
        )
        self.writer.writeheader()
        return self

    def writerow(self, row: Mapping[str, Any]) -> None:
        assert self.writer is not None
        self.writer.writerow(
            {name: _tsv_value(row.get(name)) for name in self.fields}
        )

    def __exit__(
        self, exc_type: object, exc: object, traceback: object
    ) -> None:
        assert self.text is not None and self.sink is not None
        self.text.close()
        self.sink.close()
        self.sha256 = self.sink.digest.hexdigest()
        self.size_bytes = self.sink.size

    def artifact(self) -> dict[str, Any]:
        assert self.sha256 is not None and self.size_bytes is not None
        return {
            "name": self.path.name,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


def _tsv_value(value: object) -> object:
    return "N/A" if value is None else value


PER_FORM_FIELDS = (
    "cell_id",
    "form_key",
    "phoneme_length",
    "training_expected_count",
    "probability",
) + tuple(
    f"{axis}_{name}"
    for axis in ("context", "surface")
    for name in (
        "total_expected_mass",
        "association_rows",
        "observed_support",
        *AXIS_METRICS,
    )
)


def _form_row(form: FormMetrics) -> dict[str, Any]:
    row: dict[str, Any] = {
        "cell_id": form.cell_id,
        "form_key": form.form_key,
        "phoneme_length": form.phoneme_length,
        "training_expected_count": form.training_expected_count,
        "probability": form.probability,
    }
    for axis_name in ("context", "surface"):
        axis = getattr(form, axis_name)
        row[f"{axis_name}_total_expected_mass"] = axis.total_expected_mass
        row[f"{axis_name}_association_rows"] = axis.association_rows
        row[f"{axis_name}_observed_support"] = axis.observed_support
        for metric in AXIS_METRICS:
            row[f"{axis_name}_{metric}"] = axis.metric(metric)
    return row


COMPARISON_FIELDS = (
    "comparison_id",
    "form_key",
    "membership",
    "cell_a",
    "cell_b",
) + tuple(
    field
    for metric in COMPARISON_METRICS
    for field in (
        f"cell_a_{metric}",
        f"cell_b_{metric}",
        f"delta_{metric}",
    )
)


def _comparison_row(
    spec: ComparisonSpec,
    key: str,
    membership: str,
    a: FormMetrics | None,
    b: FormMetrics | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "comparison_id": spec.comparison_id,
        "form_key": key,
        "membership": membership,
        "cell_a": spec.cell_a,
        "cell_b": spec.cell_b,
    }
    for metric in COMPARISON_METRICS:
        av = None if a is None else _metric_value(a, metric)
        bv = None if b is None else _metric_value(b, metric)
        row[f"cell_a_{metric}"] = av
        row[f"cell_b_{metric}"] = bv
        row[f"delta_{metric}"] = (
            None if av is None or bv is None else bv - av
        )
    return row


def _flatten_bucket(
    prefix: Mapping[str, Any], bucket: Bucket
) -> dict[str, Any]:
    payload = bucket.payload()
    row = dict(prefix)
    row.update(
        {
            "forms_total": payload["forms_total"],
            "forms_with_training_count": payload[
                "forms_with_training_count"
            ],
            "training_expected_count_total": payload[
                "training_expected_count_total"
            ],
        }
    )
    for axis in ("context", "surface"):
        axis_payload = payload[axis]
        for name in (
            "forms_with_rows",
            "forms_with_positive_support",
            "association_rows",
            "total_expected_mass",
        ):
            row[f"{axis}_{name}"] = axis_payload[name]
        for metric in AXIS_METRICS:
            metric_payload = axis_payload["metrics"][metric]
            row[f"{axis}_{metric}_type_mean"] = metric_payload[
                "type_mean"
            ]
            row[
                f"{axis}_{metric}_training_count_weighted_mean"
            ] = metric_payload[
                "training_expected_count_weighted_mean"
            ]
            row[
                f"{axis}_{metric}_association_mass_weighted_mean"
            ] = metric_payload[
                "association_expected_mass_weighted_mean"
            ]
    return row


BUCKET_VALUE_FIELDS = tuple(_flatten_bucket({}, Bucket()).keys())


def _write_tsv(
    path: Path,
    fields: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=tuple(fields),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {name: _tsv_value(row.get(name)) for name in fields}
            )
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _definitions(top_k: int) -> dict[str, Any]:
    return {
        "association_distribution": (
            "For each form and axis, p_i = expected_mass_i / sum_i "
            "expected_mass_i over strictly positive exported rows."
        ),
        "top1_share": "max_i p_i",
        "topk_share": (
            f"sum of the largest min({top_k}, n) shares; configured "
            f"k={top_k}"
        ),
        "entropy_nats": (
            "H = -sum_i p_i ln(p_i), using the natural logarithm"
        ),
        "normalized_entropy": (
            "0 for support size 1; otherwise H / ln(n); N/A for zero "
            "positive support"
        ),
        "effective_support_shannon": "exp(H)",
        "herfindahl": (
            "sum_i p_i^2 (also called Simpson concentration)"
        ),
        "effective_support_simpson": "1 / sum_i p_i^2",
        "observed_support": (
            "number of distinct exported association values with "
            "strictly positive expected mass"
        ),
        "phoneme_length": (
            "number of validated canonical Phoneme IDs in dot-separated "
            "script-neutral form_key; not Unicode or morphological length"
        ),
        "type_weighting": (
            "arithmetic mean over forms for which the metric is defined"
        ),
        "training_expected_count_weighting": (
            "mean weighted by final-scorer training_expected_count"
        ),
        "association_expected_mass_weighting": (
            "axis-specific mean weighted by the form's association mass"
        ),
        "matched_delta_direction": "cell_b minus cell_a",
        "scorer_association_equality": (
            "not required: scorer values are final-training-pass state; "
            "surface associations are thresholded inspection expected "
            "counts; context associations come from retained top-K "
            "inspection analyses above the usage threshold"
        ),
        "zero_mass_rows": (
            "allowed by numeric contract and excluded from positive "
            "support; zero-total groups receive N/A metrics"
        ),
        "sorting_contract": (
            "scorer form_key strictly increasing; association "
            "(form_key, value) strictly increasing; violations and "
            "duplicates fail without sorting"
        ),
    }


def _small_output_rows(
    analysis: AnalysisSpec,
    cells: Mapping[str, CellAccumulator],
    comparisons: Mapping[str, ComparisonAccumulator],
    diagnostics: Sequence[DiagnosticReservoir],
) -> tuple[
    dict[str, Any],
    dict[str, tuple[tuple[str, ...], list[dict[str, Any]]]],
]:
    length_rows: list[dict[str, Any]] = []
    count_rows: list[dict[str, Any]] = []
    joint_rows: list[dict[str, Any]] = []
    relationship_rows: list[dict[str, Any]] = []
    for cell_spec in analysis.cells:
        cell = cells[cell_spec.cell_id]
        for label in analysis.length_bins.labels:
            length_rows.append(
                _flatten_bucket(
                    {"cell_id": cell.cell_id, "length_bin": label},
                    cell.length.get(label, Bucket()),
                )
            )
        count_labels = list(analysis.count_bins.labels) + [
            "MISSING_SCORER"
        ]
        for label in count_labels:
            count_rows.append(
                _flatten_bucket(
                    {"cell_id": cell.cell_id, "count_bin": label},
                    cell.count.get(label, Bucket()),
                )
            )
        for length_label in analysis.length_bins.labels:
            for count_label in count_labels:
                joint_rows.append(
                    _flatten_bucket(
                        {
                            "cell_id": cell.cell_id,
                            "length_bin": length_label,
                            "count_bin": count_label,
                        },
                        cell.joint.get(
                            (length_label, count_label), Bucket()
                        ),
                    )
                )
        for key, value in sorted(cell.relationships.items()):
            predictor, axis, metric, weighting = key
            relationship_rows.append(
                {
                    "cell_id": cell.cell_id,
                    "predictor": predictor,
                    "axis": axis,
                    "metric": metric,
                    "weighting": weighting,
                    "observations": value.observations,
                    "weight_sum": value.weight_sum,
                    "pearson": value.pearson(),
                }
            )

    comparison_rows: list[dict[str, Any]] = []
    stratum_rows: list[dict[str, Any]] = []
    comparison_payloads: list[dict[str, Any]] = []
    for spec in analysis.comparisons:
        accumulator = comparisons.get(spec.comparison_id)
        if accumulator is None:
            comparison_payloads.append(
                {
                    "comparison_id": spec.comparison_id,
                    "cell_a": spec.cell_a,
                    "cell_b": spec.cell_b,
                    "form_alignment": {
                        "status": "UNSUPPORTED",
                        "reason": spec.alignment_reason,
                        "namespace": None,
                    },
                    "direction": "cell_b_minus_cell_a",
                    "membership": None,
                    "matched_deltas": None,
                }
            )
            comparison_rows.append(
                {
                    "comparison_id": spec.comparison_id,
                    "record_type": "scientific_na",
                    "reason": spec.alignment_reason,
                }
            )
            continue
        comparison_payloads.append(accumulator.payload())
        for membership in ("shared", "cell_a_only", "cell_b_only"):
            comparison_rows.append(
                {
                    "comparison_id": spec.comparison_id,
                    "record_type": "membership",
                    "membership": membership,
                    "form_count": accumulator.membership_counts[
                        membership
                    ],
                    "cell_a_training_mass": (
                        accumulator.membership_a_mass[membership].total
                    ),
                    "cell_b_training_mass": (
                        accumulator.membership_b_mass[membership].total
                    ),
                }
            )
        for metric in COMPARISON_METRICS:
            delta = accumulator.deltas[metric].payload()
            comparison_rows.append(
                {
                    "comparison_id": spec.comparison_id,
                    "record_type": "matched_delta",
                    "membership": "shared",
                    "metric": metric,
                    "cell_a_training_mass": delta[
                        "cell_a_training_mass"
                    ],
                    "cell_b_training_mass": delta[
                        "cell_b_training_mass"
                    ],
                    "eligible_forms": delta["eligible_forms"],
                    "type_mean_delta": delta["type_mean_delta"],
                    "cell_a_training_mass_weighted_mean_delta": delta[
                        "cell_a_training_mass_weighted_mean_delta"
                    ],
                    "cell_b_training_mass_weighted_mean_delta": delta[
                        "cell_b_training_mass_weighted_mean_delta"
                    ],
                }
            )
        for (stratum, side), bucket in sorted(
            accumulator.strata.items()
        ):
            cell_id = spec.cell_a if side == "cell_a" else spec.cell_b
            stratum_rows.append(
                _flatten_bucket(
                    {
                        "comparison_id": spec.comparison_id,
                        "stratum": stratum,
                        "side": side,
                        "cell_id": cell_id,
                    },
                    bucket,
                )
            )

    diagnostic_rows = [
        row for reservoir in diagnostics for row in reservoir.rows()
    ]
    summary = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "analysis_id": analysis.analysis_id,
        "definitions": _definitions(analysis.top_k),
        "cells": [
            {
                "cell_id": cell.cell_id,
                **cells[cell.cell_id].all_forms.payload(),
            }
            for cell in analysis.cells
        ],
        "comparisons": comparison_payloads,
    }
    bucket_fields = BUCKET_VALUE_FIELDS
    tables = {
        "length_bins.tsv": (
            ("cell_id", "length_bin", *bucket_fields),
            length_rows,
        ),
        "count_bins.tsv": (
            ("cell_id", "count_bin", *bucket_fields),
            count_rows,
        ),
        "joint_bins.tsv": (
            ("cell_id", "length_bin", "count_bin", *bucket_fields),
            joint_rows,
        ),
        "relationship_summary.tsv": (
            (
                "cell_id",
                "predictor",
                "axis",
                "metric",
                "weighting",
                "observations",
                "weight_sum",
                "pearson",
            ),
            relationship_rows,
        ),
        "comparison_summary.tsv": (
            (
                "comparison_id",
                "record_type",
                "membership",
                "metric",
                "form_count",
                "cell_a_training_mass",
                "cell_b_training_mass",
                "eligible_forms",
                "type_mean_delta",
                "cell_a_training_mass_weighted_mean_delta",
                "cell_b_training_mass_weighted_mean_delta",
                "reason",
            ),
            comparison_rows,
        ),
        "comparison_strata.tsv": (
            (
                "comparison_id",
                "stratum",
                "side",
                "cell_id",
                *bucket_fields,
            ),
            stratum_rows,
        ),
        "diagnostic_examples.tsv": (
            (
                "diagnostic_id",
                "category",
                "selection_rank",
                "form_key",
                "target_cell",
                "reference_cell",
                "phoneme_length",
                "target_training_expected_count",
                "reference_training_expected_count",
                "target_context_top1_share",
                "reference_context_top1_share",
                "delta_context_top1_share",
                "target_context_entropy_nats",
                "reference_context_entropy_nats",
                "target_context_effective_support",
                "reference_context_effective_support",
                "target_surface_top1_share",
                "reference_surface_top1_share",
                "target_surface_effective_support",
                "reference_surface_effective_support",
                "target_top_contexts_json",
                "reference_top_contexts_json",
                "target_top_surfaces_json",
                "reference_top_surfaces_json",
                "selection_primary_score",
                "selection_tuple_json",
            ),
            diagnostic_rows,
        ),
    }
    return summary, tables


def analyze_manifest(manifest_path: Path, output_dir: Path) -> None:
    """Validate, stream, summarize, and atomically publish one analysis."""

    analysis = _parse_manifest(manifest_path)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(
            f"refusing to overwrite output directory: {output_dir}"
        )
    compact_inputs = {
        cell.cell_id: CompactInput.load(cell, analysis)
        for cell in analysis.cells
    }
    provenance, repository_root = _implementation_provenance()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.", dir=output_dir.parent
        )
    )
    streams: dict[str, CellFormStream] = {}
    try:
        streams = {
            cell.cell_id: CellFormStream(
                compact_inputs[cell.cell_id], analysis.top_k
            )
            for cell in analysis.cells
        }
        current = {
            cell_id: _next_or_none(stream)
            for cell_id, stream in streams.items()
        }
        cells = {
            cell.cell_id: CellAccumulator(cell.cell_id)
            for cell in analysis.cells
        }
        comparisons = {
            spec.comparison_id: ComparisonAccumulator(spec)
            for spec in analysis.comparisons
            if spec.alignment_status == "SUPPORTED"
        }
        diagnostics = [
            DiagnosticReservoir(spec) for spec in analysis.diagnostics
        ]
        diagnostics_by_comparison: dict[
            str, list[DiagnosticReservoir]
        ] = defaultdict(list)
        for reservoir in diagnostics:
            diagnostics_by_comparison[
                reservoir.spec.comparison_id
            ].append(reservoir)

        per_form_rows = 0
        comparison_rows = 0
        per_form_output = GzipTsvWriter(
            temporary / "per_form_metrics.tsv.gz", PER_FORM_FIELDS
        )
        comparison_output = GzipTsvWriter(
            temporary / "comparison.tsv.gz", COMPARISON_FIELDS
        )
        with per_form_output, comparison_output:
            while any(item is not None for item in current.values()):
                key = min(
                    item.form_key
                    for item in current.values()
                    if item is not None
                )
                forms: dict[str, FormMetrics] = {}
                for cell_id, item in tuple(current.items()):
                    if item is not None and item.form_key == key:
                        forms[cell_id] = item
                        count_bin = (
                            "MISSING_SCORER"
                            if item.training_expected_count is None
                            else analysis.count_bins.label(
                                item.training_expected_count
                            )
                        )
                        cells[cell_id].add(
                            item,
                            analysis.length_bins.label(
                                float(item.phoneme_length)
                            ),
                            count_bin,
                        )
                        per_form_output.writerow(_form_row(item))
                        per_form_rows += 1
                        current[cell_id] = _next_or_none(
                            streams[cell_id]
                        )
                for spec in analysis.comparisons:
                    if spec.alignment_status != "SUPPORTED":
                        continue
                    a, b = forms.get(spec.cell_a), forms.get(spec.cell_b)
                    if a is None and b is None:
                        continue
                    accumulator = comparisons[spec.comparison_id]
                    membership = accumulator.add(a, b)
                    comparison_output.writerow(
                        _comparison_row(
                            spec, key, membership, a, b
                        )
                    )
                    comparison_rows += 1
                    for reservoir in diagnostics_by_comparison.get(
                        spec.comparison_id, ()
                    ):
                        reservoir.consider(a, b, spec)

        summary, tables = _small_output_rows(
            analysis, cells, comparisons, diagnostics
        )
        artifacts = [
            per_form_output.artifact(),
            comparison_output.artifact(),
        ]
        summary_path = temporary / "cell_summary.json"
        summary_path.write_text(
            json.dumps(
                summary, ensure_ascii=False, indent=2, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
            newline="",
        )
        artifacts.append(
            {
                "name": summary_path.name,
                "size_bytes": summary_path.stat().st_size,
                "sha256": _sha256(summary_path),
            }
        )
        for name, (fields, rows) in tables.items():
            artifacts.append(
                _write_tsv(temporary / name, fields, rows)
            )

        output_manifest = {
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "analysis_id": analysis.analysis_id,
            "analysis_implementation_provenance": provenance,
            "analysis_input_manifest": {
                "path": _relative_or_absolute(
                    analysis.manifest_path, repository_root
                ),
                "sha256": _sha256(analysis.manifest_path),
                "schema_version": INPUT_SCHEMA_VERSION,
            },
            "input_cells": [
                compact_inputs[cell.cell_id].identity_payload(
                    repository_root
                )
                for cell in analysis.cells
            ],
            "parameters": {
                "association_top_k": analysis.top_k,
                "bins": {
                    "phoneme_length": analysis.length_bins.payload(),
                    "training_expected_count": (
                        analysis.count_bins.payload()
                    ),
                    "interval_rule": (
                        "successive bins use <= upper bound; final bin "
                        "is above the last bound"
                    ),
                    "missing_scorer_bin": "MISSING_SCORER",
                },
                "comparisons": [
                    {
                        "comparison_id": item.comparison_id,
                        "cell_a": item.cell_a,
                        "cell_b": item.cell_b,
                        "form_alignment_status": (
                            item.alignment_status
                        ),
                        "form_alignment_reason": (
                            item.alignment_reason
                        ),
                        "form_key_namespace": item.namespace,
                        "strong_count_increase_ratio": (
                            item.strong_count_increase_ratio
                        ),
                    }
                    for item in analysis.comparisons
                ],
                "diagnostics": [
                    item.payload() for item in analysis.diagnostics
                ],
                "diagnostic_selection_order": (
                    "primary score DESC, target context top1 DESC, "
                    "target effective support ASC, phoneme length DESC, "
                    "target training count ASC, form_key DESC"
                ),
            },
            "definitions": _definitions(analysis.top_k),
            "row_counts": {
                "per_form_metrics": per_form_rows,
                "comparison": comparison_rows,
                "diagnostic_examples": sum(
                    len(reservoir.rows()) for reservoir in diagnostics
                ),
            },
            "output_artifacts": sorted(
                artifacts, key=lambda item: item["name"]
            ),
            "publication": "atomic_non_overwriting_directory",
        }
        manifest_output_path = temporary / "manifest.json"
        manifest_output_path.write_text(
            json.dumps(
                output_manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="",
        )
        manifest_artifact = {
            "name": "manifest.json",
            "size_bytes": manifest_output_path.stat().st_size,
            "sha256": _sha256(manifest_output_path),
        }
        with (temporary / "SHA256SUMS").open(
            "x", encoding="utf-8", newline=""
        ) as handle:
            for artifact in sorted(
                [*artifacts, manifest_artifact],
                key=lambda item: item["name"],
            ):
                handle.write(
                    f"{artifact['sha256']}  {artifact['name']}\n"
                )
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        for stream in streams.values():
            stream.close()
