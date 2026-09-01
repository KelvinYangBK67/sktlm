"""Fail-closed local aggregation for the unrestricted six-representation M0 gate.

No function in this module contacts a remote host or mutates source artifacts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "sktlm-six-representation-gate-input/v1"
OUTPUT_SCHEMA_VERSION = "sktlm-six-representation-gate-aggregation/v1"
FORMAL_CELLS = (
    ("iast", "surface_word"),
    ("iast", "legacy_joined"),
    ("iast", "continuous"),
    ("devanagari", "surface_word"),
    ("devanagari", "legacy_joined"),
    ("devanagari", "continuous"),
)
SCIENTIFIC_FILES = (
    "iteration_metrics.json", "summary.json", "analyses.jsonl",
    "boundary_posteriors.jsonl", "latent_lexicon.tsv", "rule_usage.tsv",
)
REQUIRED_RUN_FILES = (
    "checkpoint.json", "config.json", "provenance.json", "timing_metrics.json",
    "inspection_report.md", *SCIENTIFIC_FILES,
)
MASS_THRESHOLDS = (0.9, 0.95, 0.99, 0.999, 0.9999)
COMMON_PROVENANCE_FIELDS = (
    "implementation", "freeze_id", "manifest_sha256", "rules_sha256",
    "external_rule_count", "document_count", "seed",
)
CONFIG_IDENTITY_FIELDS = frozenset({"run_id", "script", "condition", "output_root"})


class GateValidationError(ValueError):
    """One or more prerequisites for scientific aggregation failed."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "validation": {"valid": False, "errors": list(self.errors)},
        }


@dataclass(frozen=True, slots=True)
class CellSpec:
    script: str
    condition: str
    run_id: str
    metrics_id: str
    scientific_commit: str
    run_dir: Path
    metrics_dir: Path
    audit_path: Path

    @property
    def key(self) -> tuple[str, str]:
        return self.script, self.condition

    @property
    def cell_id(self) -> str:
        return f"{self.script}__{self.condition}"


@dataclass(frozen=True, slots=True)
class LoadedCell:
    spec: CellSpec
    config: dict[str, Any]
    checkpoint: dict[str, Any]
    provenance: dict[str, Any]
    summary: dict[str, Any]
    timing: dict[str, Any]
    process: dict[str, Any]
    audit: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PairSpec:
    pair_id: str
    kind: str
    cell_a: tuple[str, str]
    cell_b: tuple[str, str]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateValidationError((f"{label} is unreadable JSON: {path}: {exc}",)) from exc
    if not isinstance(value, dict):
        raise GateValidationError((f"{label} must be a JSON object: {path}",))
    return value


def _resolve_local_path(base: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise GateValidationError((f"{label} must be a nonempty local path",))
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _is_full_sha(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _parse_manifest(path: Path) -> tuple[dict[str, Any], tuple[CellSpec, ...]]:
    payload = _read_json_object(path, "gate manifest")
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    for field in ("gate_id", "scientific_contract_id"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(f"{field} must be a nonempty string")

    raw_cells = payload.get("cells")
    if not isinstance(raw_cells, list):
        errors.append("cells must be a JSON array")
        raw_cells = []
    required = (
        "script", "condition", "run_id", "metrics_id", "scientific_commit",
        "run_dir", "metrics_dir", "audit_path",
    )
    base = path.parent.resolve()
    specs: list[CellSpec] = []
    for index, raw in enumerate(raw_cells):
        label = f"cells[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = [field for field in required if field not in raw]
        if missing:
            errors.append(f"{label} is missing fields: {missing}")
            continue
        if any(not isinstance(raw[field], str) or not raw[field] for field in required):
            errors.append(f"{label} fields must all be nonempty strings")
            continue
        if not _is_full_sha(raw["scientific_commit"]):
            errors.append(f"{label}.scientific_commit must be a lowercase full SHA")
            continue
        specs.append(CellSpec(
            script=raw["script"], condition=raw["condition"],
            run_id=raw["run_id"], metrics_id=raw["metrics_id"],
            scientific_commit=raw["scientific_commit"],
            run_dir=_resolve_local_path(base, raw["run_dir"], f"{label}.run_dir"),
            metrics_dir=_resolve_local_path(base, raw["metrics_dir"], f"{label}.metrics_dir"),
            audit_path=_resolve_local_path(base, raw["audit_path"], f"{label}.audit_path"),
        ))

    keys = [spec.key for spec in specs]
    expected = set(FORMAL_CELLS)
    actual = set(keys)
    duplicates = sorted(key for key in actual if keys.count(key) > 1)
    if duplicates:
        errors.append(f"duplicate formal cells: {duplicates}")
    if expected - actual:
        errors.append(f"missing formal cells: {sorted(expected - actual)}")
    if actual - expected:
        errors.append(f"unexpected formal cells: {sorted(actual - expected)}")
    if len(specs) != len(FORMAL_CELLS):
        errors.append(f"exactly {len(FORMAL_CELLS)} cell records are required")
    for name, values in (
        ("run_id", [spec.run_id for spec in specs]),
        ("metrics_id", [spec.metrics_id for spec in specs]),
    ):
        repeated = sorted(value for value in set(values) if values.count(value) > 1)
        if repeated:
            errors.append(f"duplicate {name} values: {repeated}")

    approved = payload.get("approved_scientific_commits")
    if not isinstance(approved, list) or not approved:
        errors.append("approved_scientific_commits must be a nonempty array")
        approved = []
    elif any(not _is_full_sha(item) for item in approved):
        errors.append("approved_scientific_commits must contain lowercase full SHAs")
    elif approved != sorted(set(approved)):
        errors.append("approved_scientific_commits must be unique and sorted")
    actual_commits = sorted({spec.scientific_commit for spec in specs})
    if approved and approved != actual_commits:
        errors.append(
            "approved_scientific_commits does not exactly match cell provenance: "
            f"approved={approved}, cells={actual_commits}"
        )
    if len(actual_commits) > 1:
        compatibility = payload.get("cross_commit_compatibility")
        if not isinstance(compatibility, dict):
            errors.append("multiple scientific commits require cross_commit_compatibility")
        else:
            if compatibility.get("status") != "approved":
                errors.append("cross_commit_compatibility.status must be 'approved'")
            if not isinstance(compatibility.get("basis"), str) or not compatibility["basis"].strip():
                errors.append("cross_commit_compatibility.basis must be explicit")
            evidence = compatibility.get("evidence")
            if not isinstance(evidence, list) or not evidence or any(
                not isinstance(item, str) or not item for item in evidence
            ):
                errors.append("cross_commit_compatibility.evidence must list tracked evidence")
    if errors:
        raise GateValidationError(errors)
    by_key = {spec.key: spec for spec in specs}
    return payload, tuple(by_key[key] for key in FORMAL_CELLS)


def _load_cell(spec: CellSpec) -> LoadedCell:
    errors: list[str] = []
    if not spec.run_dir.is_dir():
        errors.append(f"{spec.cell_id}: run directory is missing: {spec.run_dir}")
    if not spec.metrics_dir.is_dir():
        errors.append(f"{spec.cell_id}: metrics directory is missing: {spec.metrics_dir}")
    if not spec.audit_path.is_file():
        errors.append(f"{spec.cell_id}: final audit is missing: {spec.audit_path}")
    for name in REQUIRED_RUN_FILES:
        if not (spec.run_dir / name).is_file():
            errors.append(f"{spec.cell_id}: required run artifact is missing: {name}")
    process_path = spec.metrics_dir / "process_tree_summary.json"
    if not process_path.is_file():
        errors.append(f"{spec.cell_id}: process_tree_summary.json is missing")
    if errors:
        raise GateValidationError(errors)

    config = _read_json_object(spec.run_dir / "config.json", f"{spec.cell_id} config")
    checkpoint = _read_json_object(spec.run_dir / "checkpoint.json", f"{spec.cell_id} checkpoint")
    provenance = _read_json_object(spec.run_dir / "provenance.json", f"{spec.cell_id} provenance")
    summary = _read_json_object(spec.run_dir / "summary.json", f"{spec.cell_id} summary")
    timing = _read_json_object(spec.run_dir / "timing_metrics.json", f"{spec.cell_id} timing")
    process = _read_json_object(process_path, f"{spec.cell_id} process summary")
    audit = _read_json_object(spec.audit_path, f"{spec.cell_id} final audit")

    if config.get("run_id") != spec.run_id:
        errors.append(f"{spec.cell_id}: config run_id does not match manifest")
    if config.get("script") != spec.script or config.get("condition") != spec.condition:
        errors.append(f"{spec.cell_id}: config representation identity does not match")
    if config.get("vocab_budget") is not None:
        errors.append(f"{spec.cell_id}: fixed-vocabulary input cannot replace unrestricted")
    for field in ("document_list", "max_documents", "max_lines_per_document"):
        if config.get(field) is not None:
            errors.append(f"{spec.cell_id}: scoped config field {field} must be null")
    if provenance.get("script") != spec.script or provenance.get("condition") != spec.condition:
        errors.append(f"{spec.cell_id}: provenance representation identity does not match")
    if provenance.get("git_commit") != spec.scientific_commit:
        errors.append(f"{spec.cell_id}: provenance Git SHA does not match manifest")
    if process.get("return_code") != 0:
        errors.append(f"{spec.cell_id}: process-tree return_code is not zero")
    if checkpoint.get("inspection_complete") is not True:
        errors.append(f"{spec.cell_id}: checkpoint inspection is incomplete")
    if checkpoint.get("completed_passes") != config.get("passes"):
        errors.append(f"{spec.cell_id}: completed passes do not match config")
    if audit.get("valid") is not True:
        errors.append(f"{spec.cell_id}: final audit is not valid")
    if audit.get("failures") not in (None, []):
        errors.append(f"{spec.cell_id}: final audit contains failures")
    if audit.get("provenance") != provenance:
        errors.append(f"{spec.cell_id}: collected provenance differs from final audit")
    if audit.get("process_metrics") != process:
        errors.append(f"{spec.cell_id}: collected process summary differs from final audit")
    audit_run = audit.get("run_dir")
    if not isinstance(audit_run, str) or PurePosixPath(audit_run.replace("\\", "/")).name != spec.run_id:
        errors.append(f"{spec.cell_id}: final audit run identity does not match run_id")
    completion = audit.get("completion")
    if not isinstance(completion, dict):
        errors.append(f"{spec.cell_id}: final audit completion block is missing")
    else:
        expected_completion = {
            "script": spec.script, "condition": spec.condition,
            "workers": config.get("workers"), "documents": summary.get("documents"),
            "segments": summary.get("segments"), "characters": summary.get("characters"),
            "overflowed_tokens": summary.get("overflowed_tokens"),
        }
        for field, expected_value in expected_completion.items():
            if completion.get(field) != expected_value:
                errors.append(f"{spec.cell_id}: audit completion {field} differs from local artifacts")

    scientific = audit.get("scientific_artifacts")
    if not isinstance(scientific, dict):
        errors.append(f"{spec.cell_id}: final audit scientific_artifacts is missing")
    else:
        for name in SCIENTIFIC_FILES:
            expected_file = scientific.get(name)
            local_path = spec.run_dir / name
            if not isinstance(expected_file, dict):
                errors.append(f"{spec.cell_id}: audit lacks scientific identity for {name}")
                continue
            if (
                expected_file.get("bytes") != local_path.stat().st_size
                or expected_file.get("sha256") != _file_sha256(local_path)
            ):
                errors.append(f"{spec.cell_id}: collected artifact differs from audit: {name}")
    if errors:
        raise GateValidationError(errors)
    return LoadedCell(spec, config, checkpoint, provenance, summary, timing, process, audit)


def _validate_cross_cell_contract(cells: tuple[LoadedCell, ...]) -> None:
    errors: list[str] = []
    reference_config = {
        key: value for key, value in cells[0].config.items()
        if key not in CONFIG_IDENTITY_FIELDS
    }
    reference_provenance = {
        key: cells[0].provenance.get(key) for key in COMMON_PROVENANCE_FIELDS
    }
    for cell in cells[1:]:
        common_config = {
            key: value for key, value in cell.config.items()
            if key not in CONFIG_IDENTITY_FIELDS
        }
        if common_config != reference_config:
            errors.append(f"{cell.spec.cell_id}: non-identity scientific configuration differs")
        common_provenance = {
            key: cell.provenance.get(key) for key in COMMON_PROVENANCE_FIELDS
        }
        if common_provenance != reference_provenance:
            errors.append(f"{cell.spec.cell_id}: common M0 provenance differs")
    if errors:
        raise GateValidationError(errors)

def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GateValidationError((f"{label} must be numeric",))
    number = float(value)
    if not math.isfinite(number):
        raise GateValidationError((f"{label} must be finite",))
    return number


def _parse_float(value: object, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise GateValidationError((f"{label} is not a float: {value!r}",)) from exc
    if not math.isfinite(number):
        raise GateValidationError((f"{label} must be finite",))
    return number


def _kahan_add(total: float, compensation: float, value: float) -> tuple[float, float]:
    adjusted = value - compensation
    updated = total + adjusted
    return updated, (updated - total) - adjusted


def _threshold_key(value: float) -> str:
    return f"{value * 100:g}%"


def lexical_mass_summary(path: Path, low_count_threshold: float) -> dict[str, Any]:
    """Stream a deterministic lexicon twice without materializing its rows."""

    total = compensation = 0.0
    active = low_count = 0
    previous_count = math.inf
    previous_key = ""
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or not {"form_key", "expected_count"}.issubset(reader.fieldnames):
            raise GateValidationError((f"latent lexicon has invalid header: {path}",))
        for line_number, row in enumerate(reader, start=2):
            key = row.get("form_key", "")
            if not key:
                raise GateValidationError((f"empty form_key at {path}:{line_number}",))
            count = _parse_float(row.get("expected_count"), f"{path}:{line_number} expected_count")
            if count < 0.0:
                raise GateValidationError((f"negative expected_count at {path}:{line_number}",))
            if count > previous_count or (
                count == previous_count and previous_key and key < previous_key
            ):
                raise GateValidationError((
                    "latent lexicon is not sorted by expected_count DESC, "
                    f"form_key ASC at {path}:{line_number}",
                ))
            previous_count, previous_key = count, key
            total, compensation = _kahan_add(total, compensation, count)
            active += 1
            low_count += count <= low_count_threshold
    if active == 0 or total <= 0.0:
        raise GateValidationError((f"latent lexicon is empty or has zero mass: {path}",))

    targets = {threshold: threshold * total for threshold in MASS_THRESHOLDS}
    support: dict[str, int] = {}
    cumulative = compensation = 0.0
    with path.open("r", encoding="utf-8", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle, delimiter="\t"), start=1):
            cumulative, compensation = _kahan_add(
                cumulative, compensation, float(row["expected_count"])
            )
            for threshold in MASS_THRESHOLDS:
                key = _threshold_key(threshold)
                if key not in support and cumulative >= targets[threshold]:
                    support[key] = index
    for threshold in MASS_THRESHOLDS:
        support.setdefault(_threshold_key(threshold), active)
    return {
        "active_lexical_types": active,
        "lexical_expected_count_total": total,
        "low_count_lexical_types": low_count,
        "low_count_threshold": low_count_threshold,
        "low_count_fraction": low_count / active,
        "mass_support_type_counts": support,
        "ranking_rule": "expected_count DESC, form_key ASC",
    }


def rule_usage_summary(path: Path, declared_rule_count: int) -> dict[str, Any]:
    usage: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or not {"rule_id", "expected_usage"}.issubset(reader.fieldnames):
            raise GateValidationError((f"rule usage has invalid header: {path}",))
        for line_number, row in enumerate(reader, start=2):
            rule_id = row.get("rule_id", "")
            if not rule_id or rule_id in usage:
                raise GateValidationError((f"duplicate/empty rule_id at {path}:{line_number}",))
            value = _parse_float(row.get("expected_usage"), f"{path}:{line_number} expected_usage")
            if value < 0.0:
                raise GateValidationError((f"negative rule usage at {path}:{line_number}",))
            usage[rule_id] = value
    if len(usage) != declared_rule_count:
        raise GateValidationError((
            f"rule usage row count {len(usage)} differs from provenance "
            f"external_rule_count {declared_rule_count}",
        ))
    total = math.fsum(usage.values())
    normalized = {
        rule_id: (value / total if total > 0.0 else 0.0)
        for rule_id, value in sorted(usage.items())
    }
    nonzero = sum(value > 0.0 for value in usage.values())
    top = sorted(usage.items(), key=lambda item: (-item[1], item[0]))[:20]
    return {
        "total_expected_usage": total,
        "nonzero_rule_count": nonzero,
        "zero_rule_count": len(usage) - nonzero,
        "rule_count": len(usage),
        "nonzero_coverage": nonzero / len(usage) if usage else None,
        "top_used_rules": [
            {"rule_id": rule_id, "expected_usage": value} for rule_id, value in top
        ],
        "expected_usage": dict(sorted(usage.items())),
        "normalized_distribution": normalized,
        "normalization_status": "normalized" if total > 0.0 else "zero_total",
    }


def total_variation(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    support = set(left) | set(right)
    return 0.5 * math.fsum(
        abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in support
    )


def jensen_shannon_nats(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    divergence = 0.0
    for key in set(left) | set(right):
        p, q = left.get(key, 0.0), right.get(key, 0.0)
        midpoint = 0.5 * (p + q)
        if p > 0.0:
            divergence += 0.5 * p * math.log(p / midpoint)
        if q > 0.0:
            divergence += 0.5 * q * math.log(q / midpoint)
    return divergence


def scalar_comparison(value_a: int | float, value_b: int | float) -> dict[str, Any]:
    a, b = float(value_a), float(value_b)
    signed = b - a
    denominator_zero = a == 0.0
    return {
        "value_a": value_a,
        "value_b": value_b,
        "absolute_difference": abs(signed),
        "signed_difference_b_minus_a": signed,
        "relative_difference_b_minus_a_over_abs_a": (
            None if denominator_zero else signed / abs(a)
        ),
        "ratio_b_over_a": None if denominator_zero else b / a,
        "denominator_zero": denominator_zero,
    }


def _cell_scalar_metrics(cell: LoadedCell) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = cell.summary
    complexity = summary.get("complexity")
    if not isinstance(complexity, dict):
        raise GateValidationError((f"{cell.spec.cell_id}: complexity summary is missing",))
    low_threshold = _finite_number(
        complexity.get("low_count_threshold"), f"{cell.spec.cell_id} low_count_threshold"
    )
    lexical = lexical_mass_summary(cell.spec.run_dir / "latent_lexicon.tsv", low_threshold)
    declared_rules = cell.provenance.get("external_rule_count")
    if isinstance(declared_rules, bool) or not isinstance(declared_rules, int):
        raise GateValidationError((f"{cell.spec.cell_id}: invalid external_rule_count",))
    rules = rule_usage_summary(cell.spec.run_dir / "rule_usage.tsv", declared_rules)

    if complexity.get("active_lexical_types") != lexical["active_lexical_types"]:
        raise GateValidationError((f"{cell.spec.cell_id}: lexicon row count differs from summary",))
    if complexity.get("low_count_types") != lexical["low_count_lexical_types"]:
        raise GateValidationError((f"{cell.spec.cell_id}: low-count total differs from summary",))
    if not math.isclose(
        _finite_number(complexity.get("expected_lexical_tokens"), f"{cell.spec.cell_id} complexity total"),
        lexical["lexical_expected_count_total"], rel_tol=1e-9, abs_tol=1e-6,
    ):
        raise GateValidationError((f"{cell.spec.cell_id}: lexical total differs from summary",))
    if not math.isclose(
        _finite_number(summary.get("rule_expected_usage_total"), f"{cell.spec.cell_id} rule total"),
        rules["total_expected_usage"], rel_tol=1e-9, abs_tol=1e-9,
    ):
        raise GateValidationError((f"{cell.spec.cell_id}: rule total differs from summary",))

    number = lambda key: _finite_number(summary.get(key), f"{cell.spec.cell_id} {key}")
    cnumber = lambda key: _finite_number(complexity.get(key), f"{cell.spec.cell_id} {key}")
    segments, overflowed = number("segments"), number("overflowed_tokens")
    scientific: dict[str, int | float | None] = {
        "active_lexical_types": lexical["active_lexical_types"],
        "expected_lexical_tokens": number("expected_lexical_tokens"),
        "lexical_expected_count_total": lexical["lexical_expected_count_total"],
        "identity_posterior_mass_total": number("identity_mass_total"),
        "latent_posterior_mass_total": number("latent_mass_total"),
        "mean_identity_mass": number("mean_identity_mass"),
        "mean_latent_mass": number("mean_latent_mass"),
        "mean_top1_posterior": number("mean_top1_posterior"),
        "mean_posterior_entropy": number("mean_entropy"),
        "low_count_lexical_types": lexical["low_count_lexical_types"],
        "low_count_fraction": lexical["low_count_fraction"],
        "complexity_raw": cnumber("complexity_raw"),
        "complexity_penalty": cnumber("complexity_penalty"),
        "documents": int(number("documents")),
        "segments": int(segments),
        "characters": int(number("characters")),
        "candidate_factors": int(number("candidate_factors")),
        "candidate_nodes": int(number("candidate_nodes")),
        "candidate_edges": int(number("candidate_edges")),
        "overflowed_tokens": int(overflowed),
        "overflow_frequency_per_segment": None if segments == 0.0 else overflowed / segments,
        "external_rule_expected_usage_total": rules["total_expected_usage"],
        "external_rule_nonzero_count": rules["nonzero_rule_count"],
        "external_rule_zero_count": rules["zero_rule_count"],
        "external_rule_nonzero_coverage": rules["nonzero_coverage"],
    }
    for key, value in lexical["mass_support_type_counts"].items():
        scientific[f"lexical_types_for_{key}_mass"] = value

    process = cell.process
    pnumber = lambda key: _finite_number(process.get(key), f"{cell.spec.cell_id} {key}")
    engineering: dict[str, int | float] = {
        "wall_seconds": pnumber("wall_seconds"),
        "peak_process_tree_rss_bytes": int(pnumber("peak_process_tree_rss_bytes")),
        "sampled_process_tree_cpu_seconds": pnumber("sampled_process_tree_cpu_seconds"),
        "peak_process_count": int(pnumber("peak_process_count")),
        "sampled_process_tree_read_bytes": int(pnumber("sampled_process_tree_read_bytes")),
        "sampled_process_tree_write_bytes": int(pnumber("sampled_process_tree_write_bytes")),
        "logical_cpu_count": int(pnumber("logical_cpu_count")),
    }
    payload = {
        "cell_id": cell.spec.cell_id,
        "script": cell.spec.script,
        "condition": cell.spec.condition,
        "run_id": cell.spec.run_id,
        "metrics_id": cell.spec.metrics_id,
        "scientific_commit": cell.spec.scientific_commit,
        "config_signature": cell.provenance.get("config_signature"),
        "scientific_metrics": scientific,
        "lexical_mass_support": lexical,
        "rule_usage": rules,
        "engineering_metrics": engineering,
    }
    return payload, {**scientific, **engineering}


def formal_pairs() -> tuple[PairSpec, ...]:
    pairs: list[PairSpec] = []
    for condition in ("surface_word", "legacy_joined", "continuous"):
        pairs.append(PairSpec(
            f"script__{condition}__iast_vs_devanagari", "script",
            ("iast", condition), ("devanagari", condition),
        ))
    for script in ("iast", "devanagari"):
        for left, right in (
            ("surface_word", "legacy_joined"),
            ("surface_word", "continuous"),
            ("legacy_joined", "continuous"),
        ):
            pairs.append(PairSpec(
                f"spacing__{script}__{left}_vs_{right}", "spacing",
                (script, left), (script, right),
            ))
    return tuple(pairs)

def aggregate_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest, specs = _parse_manifest(manifest_path)
    loaded: list[LoadedCell] = []
    errors: list[str] = []
    for spec in specs:
        try:
            loaded.append(_load_cell(spec))
        except GateValidationError as exc:
            errors.extend(exc.errors)
    if errors:
        raise GateValidationError(errors)
    cells = tuple(loaded)
    _validate_cross_cell_contract(cells)

    cell_payloads: dict[tuple[str, str], dict[str, Any]] = {}
    scalars: dict[tuple[str, str], dict[str, Any]] = {}
    for cell in cells:
        payload, scalar = _cell_scalar_metrics(cell)
        cell_payloads[cell.spec.key] = payload
        scalars[cell.spec.key] = scalar

    pair_payloads: list[dict[str, Any]] = []
    for pair in formal_pairs():
        cell_a, cell_b = cell_payloads[pair.cell_a], cell_payloads[pair.cell_b]
        scalar_rows = {
            metric: scalar_comparison(scalars[pair.cell_a][metric], scalars[pair.cell_b][metric])
            for metric in sorted(set(scalars[pair.cell_a]) & set(scalars[pair.cell_b]))
            if scalars[pair.cell_a][metric] is not None
            and scalars[pair.cell_b][metric] is not None
        }
        left_rules, right_rules = cell_a["rule_usage"], cell_b["rule_usage"]
        if (
            left_rules["normalization_status"] == "normalized"
            and right_rules["normalization_status"] == "normalized"
        ):
            rule_distance = {
                "comparable": True,
                "reason": None,
                "support": "union of rule IDs",
                "total_variation": total_variation(
                    left_rules["normalized_distribution"], right_rules["normalized_distribution"]
                ),
                "jensen_shannon_divergence": jensen_shannon_nats(
                    left_rules["normalized_distribution"], right_rules["normalized_distribution"]
                ),
                "jsd_log_base": "e",
                "jsd_units": "nats",
            }
        else:
            rule_distance = {
                "comparable": False,
                "reason": "at least one cell has zero total expected rule usage",
                "support": "union of rule IDs",
                "total_variation": None,
                "jensen_shannon_divergence": None,
                "jsd_log_base": "e",
                "jsd_units": "nats",
            }
        pair_payloads.append({
            "pair_id": pair.pair_id,
            "kind": pair.kind,
            "cell_a": cell_a["cell_id"],
            "cell_b": cell_b["cell_id"],
            "scalar_metrics": scalar_rows,
            "rule_distribution": rule_distance,
        })

    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "validation": {"valid": True, "errors": []},
        "gate_id": manifest["gate_id"],
        "scientific_contract_id": manifest["scientific_contract_id"],
        "input_manifest": {"path": str(manifest_path), "sha256": _file_sha256(manifest_path)},
        "provenance": {
            "approved_scientific_commits": manifest["approved_scientific_commits"],
            "cross_commit_compatibility": manifest.get("cross_commit_compatibility"),
            "freeze_id": cells[0].provenance.get("freeze_id"),
            "manifest_sha256": cells[0].provenance.get("manifest_sha256"),
            "rules_sha256": cells[0].provenance.get("rules_sha256"),
            "external_rule_count": cells[0].provenance.get("external_rule_count"),
            "aggregation_semantics": (
                "descriptive only; scientific and engineering metrics remain separate"
            ),
        },
        "cells": [cell_payloads[key] for key in FORMAL_CELLS],
        "pairs": pair_payloads,
    }


def _format(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{value:.10g}" if isinstance(value, float) else str(value)


def render_markdown(result: Mapping[str, Any]) -> str:
    cells, pairs = result["cells"], result["pairs"]
    lines = [
        "# Unrestricted six-representation gate aggregation", "",
        "Status: **validated descriptive aggregation**.", "",
        "This report contains deterministic descriptive statistics only. It does not",
        "declare script invariance, spacing dominance, morphology recovery, or an S1M1",
        "freeze decision.", "", "## Six cells", "",
        "| cell | active lexical types | 99% mass support | mean identity mass | mean top-1 | mean entropy |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for cell in cells:
        metric = cell["scientific_metrics"]
        lines.append(
            f"| {cell['cell_id']} | {_format(metric['active_lexical_types'])} | "
            f"{_format(metric['lexical_types_for_99%_mass'])} | "
            f"{_format(metric['mean_identity_mass'])} | {_format(metric['mean_top1_posterior'])} | "
            f"{_format(metric['mean_posterior_entropy'])} |"
        )

    def add_pair_table(title: str, kind: str) -> None:
        lines.extend([
            "", f"## {title}", "",
            "| pair | metric | value A | value B | signed B-A | relative | ratio B/A |",
            "|---|---|---:|---:|---:|---:|---:|",
        ])
        selected = (
            "active_lexical_types", "mean_identity_mass", "mean_top1_posterior",
            "mean_posterior_entropy", "overflow_frequency_per_segment",
        )
        for pair in pairs:
            if pair["kind"] != kind:
                continue
            for metric in selected:
                row = pair["scalar_metrics"].get(metric)
                if row is not None:
                    lines.append(
                        f"| {pair['pair_id']} | {metric} | {_format(row['value_a'])} | "
                        f"{_format(row['value_b'])} | {_format(row['signed_difference_b_minus_a'])} | "
                        f"{_format(row['relative_difference_b_minus_a_over_abs_a'])} | "
                        f"{_format(row['ratio_b_over_a'])} |"
                    )

    add_pair_table("Script comparisons", "script")
    add_pair_table("Spacing comparisons", "spacing")
    lines.extend([
        "", "## Runtime diagnostics", "",
        "| cell | wall seconds | peak process-tree RSS | sampled CPU seconds | peak processes | read bytes | write bytes | logical CPUs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for cell in cells:
        metric = cell["engineering_metrics"]
        lines.append(
            f"| {cell['cell_id']} | {_format(metric['wall_seconds'])} | "
            f"{_format(metric['peak_process_tree_rss_bytes'])} | "
            f"{_format(metric['sampled_process_tree_cpu_seconds'])} | "
            f"{_format(metric['peak_process_count'])} | "
            f"{_format(metric['sampled_process_tree_read_bytes'])} | "
            f"{_format(metric['sampled_process_tree_write_bytes'])} | "
            f"{_format(metric['logical_cpu_count'])} |"
        )
    lines.extend([
        "", "## Candidate overflow", "",
        "| cell | overflowed tokens | segments | frequency per segment |",
        "|---|---:|---:|---:|",
    ])
    for cell in cells:
        metric = cell["scientific_metrics"]
        lines.append(
            f"| {cell['cell_id']} | {_format(metric['overflowed_tokens'])} | "
            f"{_format(metric['segments'])} | {_format(metric['overflow_frequency_per_segment'])} |"
        )
    lines.extend([
        "", "## External-rule distribution distances", "",
        "| pair | TV | JSD (nats, log e) | comparable |",
        "|---|---:|---:|---|",
    ])
    for pair in pairs:
        distance = pair["rule_distribution"]
        lines.append(
            f"| {pair['pair_id']} | {_format(distance['total_variation'])} | "
            f"{_format(distance['jensen_shannon_divergence'])} | "
            f"{str(distance['comparable']).lower()} |"
        )
    return "\n".join(lines) + "\n"


def _write_tsvs(root: Path, result: Mapping[str, Any]) -> None:
    with (root / "cells.tsv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("cell_id", "script", "condition", "metric_group", "metric", "value"))
        for cell in result["cells"]:
            for group in ("scientific_metrics", "engineering_metrics"):
                for metric, value in sorted(cell[group].items()):
                    writer.writerow((cell["cell_id"], cell["script"], cell["condition"], group, metric, "" if value is None else value))
    with (root / "pairs.tsv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("pair_id", "kind", "cell_a", "cell_b", "metric", "value_a", "value_b", "absolute_difference", "signed_difference_b_minus_a", "relative_difference", "ratio_b_over_a", "denominator_zero"))
        for pair in result["pairs"]:
            for metric, row in sorted(pair["scalar_metrics"].items()):
                writer.writerow((pair["pair_id"], pair["kind"], pair["cell_a"], pair["cell_b"], metric, row["value_a"], row["value_b"], row["absolute_difference"], row["signed_difference_b_minus_a"], "" if row["relative_difference_b_minus_a_over_abs_a"] is None else row["relative_difference_b_minus_a_over_abs_a"], "" if row["ratio_b_over_a"] is None else row["ratio_b_over_a"], str(row["denominator_zero"]).lower()))
    with (root / "rule_usage.tsv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("cell_id", "rule_id", "expected_usage", "normalized_usage"))
        for cell in result["cells"]:
            usage = cell["rule_usage"]
            for rule_id, value in usage["expected_usage"].items():
                writer.writerow((cell["cell_id"], rule_id, value, usage["normalized_distribution"][rule_id]))
    with (root / "rule_distances.tsv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("pair_id", "kind", "cell_a", "cell_b", "total_variation", "jensen_shannon_divergence", "jsd_log_base", "jsd_units", "comparable", "reason"))
        for pair in result["pairs"]:
            row = pair["rule_distribution"]
            writer.writerow((pair["pair_id"], pair["kind"], pair["cell_a"], pair["cell_b"], "" if row["total_variation"] is None else row["total_variation"], "" if row["jensen_shannon_divergence"] is None else row["jensen_shannon_divergence"], row["jsd_log_base"], row["jsd_units"], str(row["comparable"]).lower(), row["reason"] or ""))


def write_outputs(result: Mapping[str, Any], output_dir: Path) -> None:
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        (temporary / "aggregation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="",
        )
        _write_tsvs(temporary, result)
        (temporary / "summary.md").write_text(
            render_markdown(result), encoding="utf-8", newline=""
        )
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise