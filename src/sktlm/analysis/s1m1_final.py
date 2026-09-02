"""Final S1M1 analysis contract and validation.

The scientific analysis plan is frozen in
reports/core_methods/latent_lexicon/s1m1_final_analysis_plan.md.

This implementation remains provisional until complete real-data execution
and the S1M1 result freeze.
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import tempfile

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .s1m1_archival import (
    EVIDENCE_LIMIT,
    LENGTH_MASS_THRESHOLDS,
    REUSE_THRESHOLDS,
    SOURCE_FILES,
    BoundaryReduction,
    LexiconReduction,
    _integer,
    _number,
    _reduce_analyses,
    _reduce_boundaries,
    _reduce_lexicon,
    _reduce_passes,
    _reduce_rules,
    _reduce_runtime,
    _relative_path,
    _source_entry,
    _write_tsv,
)

from .six_representation_gate import (
    CellSpec,
    GateValidationError,
    LoadedCell,
    PairSpec,
    _file_sha256,
    _load_cell,
    _validate_cross_cell_contract,
    _is_full_sha,
    _read_json_object,
    _resolve_local_path,
)

INPUT_SCHEMA_VERSION = "sktlm-s1m1-final-analysis-input/v1"
OUTPUT_SCHEMA_VERSION = "sktlm-s1m1-final-analysis/v1"

FINAL_VALID_CELLS = (
    ("iast", "surface_word"),
    ("iast", "legacy_joined"),
    ("devanagari", "surface_word"),
    ("devanagari", "legacy_joined"),
    ("devanagari", "continuous"),
)

INVALIDATED_CELL = ("iast", "continuous")

INVALIDATION_REASON_CODE = "iast_whitespace_deletion_not_phoneme_preserving"
INVALIDATION_SCIENTIFIC_COMMIT = (
    "375178ba50bd1a1644d65525907692b31413b33d"
)
INVALIDATION_ARCHIVE_SHA256 = (
    "386c94233ead7f569d0a7cdc1436a874d165dd1e0cede349f943c0196fafaa9d"
)

class FinalValidationError(GateValidationError):
    """Final S1M1 manifest/reduction validation failure."""

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "validation": {
                "valid": False,
                "errors": list(self.errors),
            },
        }


FORMAL_COMPARISONS = (
    PairSpec(
        "script_surface_word",
        "controlled_script",
        ("iast", "surface_word"),
        ("devanagari", "surface_word"),
    ),
    PairSpec(
        "script_legacy_joined",
        "controlled_script",
        ("iast", "legacy_joined"),
        ("devanagari", "legacy_joined"),
    ),
    PairSpec(
        "spacing_iast_surface_to_legacy",
        "controlled_spacing",
        ("iast", "surface_word"),
        ("iast", "legacy_joined"),
    ),
    PairSpec(
        "spacing_devanagari_surface_to_legacy",
        "controlled_spacing",
        ("devanagari", "surface_word"),
        ("devanagari", "legacy_joined"),
    ),
    PairSpec(
        "stress_devanagari_surface_to_continuous",
        "continuous_stress",
        ("devanagari", "surface_word"),
        ("devanagari", "continuous"),
    ),
    PairSpec(
        "stress_devanagari_legacy_to_continuous",
        "continuous_stress",
        ("devanagari", "legacy_joined"),
        ("devanagari", "continuous"),
    ),
)


@dataclass(frozen=True, slots=True)
class InvalidatedCellSpec:
    script: str
    condition: str
    scientific_status: str
    runtime_status: str
    formal_comparison: str
    diagnostic_evidence: str
    rerun_repair: str
    reason_code: str
    completed_passes: int
    termination_pass: int
    next_document_index: int
    scientific_commit: str
    termination_archive_sha256: str

    @property
    def key(self) -> tuple[str, str]:
        return self.script, self.condition


def _parse_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _parse_valid_cells(
    payload: dict[str, Any],
    *,
    base: Path,
    errors: list[str],
) -> tuple[CellSpec, ...]:
    raw_cells = payload.get("cells")
    if not isinstance(raw_cells, list):
        errors.append("cells must be a JSON array")
        raw_cells = []

    required = (
        "script",
        "condition",
        "run_id",
        "metrics_id",
        "scientific_commit",
        "run_dir",
        "metrics_dir",
        "audit_path",
    )

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

        if any(
            not isinstance(raw[field], str) or not raw[field]
            for field in required
        ):
            errors.append(f"{label} fields must all be nonempty strings")
            continue

        if not _is_full_sha(raw["scientific_commit"]):
            errors.append(
                f"{label}.scientific_commit must be a lowercase full SHA"
            )
            continue

        specs.append(
            CellSpec(
                script=raw["script"],
                condition=raw["condition"],
                run_id=raw["run_id"],
                metrics_id=raw["metrics_id"],
                scientific_commit=raw["scientific_commit"],
                run_dir=_resolve_local_path(
                    base, raw["run_dir"], f"{label}.run_dir"
                ),
                metrics_dir=_resolve_local_path(
                    base, raw["metrics_dir"], f"{label}.metrics_dir"
                ),
                audit_path=_resolve_local_path(
                    base, raw["audit_path"], f"{label}.audit_path"
                ),
            )
        )

    keys = [spec.key for spec in specs]
    actual = set(keys)
    expected = set(FINAL_VALID_CELLS)

    duplicates = sorted(key for key in actual if keys.count(key) > 1)
    if duplicates:
        errors.append(f"duplicate valid cells: {duplicates}")

    if INVALIDATED_CELL in actual:
        errors.append(
            "IAST continuous is scientifically invalidated and cannot appear "
            "as a valid completed cell"
        )

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        errors.append(f"missing valid cells: {missing}")
    if unexpected:
        errors.append(f"unexpected valid cells: {unexpected}")
    if len(specs) != len(FINAL_VALID_CELLS):
        errors.append(
            f"exactly {len(FINAL_VALID_CELLS)} valid cell records are required"
        )

    for name, values in (
        ("run_id", [spec.run_id for spec in specs]),
        ("metrics_id", [spec.metrics_id for spec in specs]),
    ):
        repeated = sorted(
            value for value in set(values) if values.count(value) > 1
        )
        if repeated:
            errors.append(f"duplicate {name} values: {repeated}")

    by_key = {spec.key: spec for spec in specs}
    if expected <= actual and len(specs) == len(FINAL_VALID_CELLS):
        return tuple(by_key[key] for key in FINAL_VALID_CELLS)
    return tuple(specs)


def _validate_approved_commits(
    payload: dict[str, Any],
    specs: tuple[CellSpec, ...],
    errors: list[str],
) -> None:
    approved = payload.get("approved_scientific_commits")
    if not isinstance(approved, list) or not approved:
        errors.append(
            "approved_scientific_commits must be a nonempty array"
        )
        return

    if any(not _is_full_sha(item) for item in approved):
        errors.append(
            "approved_scientific_commits must contain lowercase full SHAs"
        )
        return

    if approved != sorted(set(approved)):
        errors.append(
            "approved_scientific_commits must be unique and sorted"
        )
        return

    actual = sorted({spec.scientific_commit for spec in specs})
    if approved != actual:
        errors.append(
            "approved_scientific_commits does not exactly match valid-cell "
            f"provenance: approved={approved}, cells={actual}"
        )

    if len(actual) > 1:
        compatibility = payload.get("cross_commit_compatibility")
        if not isinstance(compatibility, dict):
            errors.append(
                "multiple scientific commits require "
                "cross_commit_compatibility"
            )
            return
        if compatibility.get("status") != "approved":
            errors.append(
                "cross_commit_compatibility.status must be 'approved'"
            )
        if (
            not isinstance(compatibility.get("basis"), str)
            or not compatibility["basis"].strip()
        ):
            errors.append(
                "cross_commit_compatibility.basis must be explicit"
            )
        evidence = compatibility.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(
                not isinstance(item, str) or not item
                for item in evidence
            )
        ):
            errors.append(
                "cross_commit_compatibility.evidence must list tracked evidence"
            )


def _parse_invalidated_cell(
    payload: dict[str, Any],
    errors: list[str],
) -> InvalidatedCellSpec | None:
    raw_records = payload.get("invalidated_cells")
    if not isinstance(raw_records, list):
        errors.append("invalidated_cells must be a JSON array")
        return None
    if len(raw_records) != 1:
        errors.append(
            "exactly one invalidated cell record is required"
        )
        return None

    raw = raw_records[0]
    if not isinstance(raw, dict):
        errors.append("invalidated_cells[0] must be an object")
        return None

    required = (
        "script",
        "condition",
        "scientific_status",
        "runtime_status",
        "formal_comparison",
        "diagnostic_evidence",
        "rerun_repair",
        "reason_code",
        "completed_passes",
        "termination_pass",
        "next_document_index",
        "scientific_commit",
        "termination_archive_sha256",
    )
    missing = [field for field in required if field not in raw]
    if missing:
        errors.append(
            f"invalidated_cells[0] is missing fields: {missing}"
        )
        return None

    string_fields = (
        "script",
        "condition",
        "scientific_status",
        "runtime_status",
        "formal_comparison",
        "diagnostic_evidence",
        "rerun_repair",
        "reason_code",
        "scientific_commit",
        "termination_archive_sha256",
    )
    if any(
        not isinstance(raw[field], str) or not raw[field]
        for field in string_fields
    ):
        errors.append(
            "invalidated_cells[0] string fields must be nonempty strings"
        )
        return None

    completed_passes = _parse_integer(raw["completed_passes"])
    termination_pass = _parse_integer(raw["termination_pass"])
    next_document_index = _parse_integer(raw["next_document_index"])
    if completed_passes is None:
        errors.append(
            "invalidated_cells[0].completed_passes must be a "
            "nonnegative integer"
        )
    if termination_pass is None:
        errors.append(
            "invalidated_cells[0].termination_pass must be a "
            "nonnegative integer"
        )
    if next_document_index is None:
        errors.append(
            "invalidated_cells[0].next_document_index must be a "
            "nonnegative integer"
        )
    if None in (completed_passes, termination_pass, next_document_index):
        return None

    record = InvalidatedCellSpec(
        script=raw["script"],
        condition=raw["condition"],
        scientific_status=raw["scientific_status"],
        runtime_status=raw["runtime_status"],
        formal_comparison=raw["formal_comparison"],
        diagnostic_evidence=raw["diagnostic_evidence"],
        rerun_repair=raw["rerun_repair"],
        reason_code=raw["reason_code"],
        completed_passes=completed_passes,
        termination_pass=termination_pass,
        next_document_index=next_document_index,
        scientific_commit=raw["scientific_commit"],
        termination_archive_sha256=raw["termination_archive_sha256"],
    )

    expected = {
        "key": INVALIDATED_CELL,
        "scientific_status": "INVALIDATED",
        "runtime_status": "TERMINATED_EARLY_BY_RESEARCHER",
        "formal_comparison": "EXCLUDED",
        "diagnostic_evidence": "RETAINED",
        "rerun_repair": "NONE",
        "reason_code": INVALIDATION_REASON_CODE,
        "completed_passes": 2,
        "termination_pass": 3,
        "next_document_index": 86,
        "scientific_commit": INVALIDATION_SCIENTIFIC_COMMIT,
        "termination_archive_sha256": INVALIDATION_ARCHIVE_SHA256,
    }

    actual = {
        "key": record.key,
        "scientific_status": record.scientific_status,
        "runtime_status": record.runtime_status,
        "formal_comparison": record.formal_comparison,
        "diagnostic_evidence": record.diagnostic_evidence,
        "rerun_repair": record.rerun_repair,
        "reason_code": record.reason_code,
        "completed_passes": record.completed_passes,
        "termination_pass": record.termination_pass,
        "next_document_index": record.next_document_index,
        "scientific_commit": record.scientific_commit,
        "termination_archive_sha256": record.termination_archive_sha256,
    }

    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            errors.append(
                "invalidated IAST-continuous provenance mismatch for "
                f"{field}: expected={expected_value!r}, "
                f"actual={actual[field]!r}"
            )

    return record


def parse_final_manifest(
    path: Path,
) -> tuple[
    dict[str, Any],
    tuple[CellSpec, ...],
    InvalidatedCellSpec,
]:
    """Parse and validate the frozen final S1M1 input contract.

    This validates manifest structure and provenance declarations only.
    Complete artifact/audit loading is performed by the later reduction layer.
    """

    path = path.resolve()
    try:
        payload = _read_json_object(path, "S1M1 final analysis manifest")
    except GateValidationError as exc:
        raise FinalValidationError(exc.errors) from exc

    errors: list[str] = []

    if payload.get("schema_version") != INPUT_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {INPUT_SCHEMA_VERSION!r}"
        )

    for field in ("analysis_id", "scientific_contract_id"):
        if (
            not isinstance(payload.get(field), str)
            or not payload[field].strip()
        ):
            errors.append(f"{field} must be a nonempty string")

    specs = _parse_valid_cells(
        payload,
        base=path.parent.resolve(),
        errors=errors,
    )
    _validate_approved_commits(payload, specs, errors)
    invalidated = _parse_invalidated_cell(payload, errors)

    if errors:
        raise FinalValidationError(errors)
    if invalidated is None:
        raise AssertionError(
            "validated manifest unexpectedly lacks invalidated cell"
        )

    return payload, specs, invalidated



def load_final_input(
    path: Path,
) -> tuple[
    dict[str, Any],
    tuple[LoadedCell, ...],
    InvalidatedCellSpec,
]:
    """Load and fully validate the five valid final S1M1 collections.

    Manifest structure is validated first. Each valid cell must then satisfy
    the existing completed-run/final-audit contract, followed by the common
    cross-cell scientific configuration and M0 provenance contract.
    """

    payload, specs, invalidated = parse_final_manifest(path)

    try:
        loaded = tuple(_load_cell(spec) for spec in specs)
        _validate_cross_cell_contract(loaded)
    except GateValidationError as exc:
        raise FinalValidationError(exc.errors) from exc

    return payload, loaded, invalidated


PER_CELL_TABLE_NAMES = (
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
)


@dataclass(slots=True)
class FinalPerCellReduction:
    manifest_payload: dict[str, Any]
    invalidated: InvalidatedCellSpec
    loaded: tuple[LoadedCell, ...]
    tables: dict[str, list[dict[str, Any]]]
    evidence: list[dict[str, Any]]
    lexicons: dict[str, LexiconReduction]
    boundaries: dict[str, BoundaryReduction]


def reduce_final_per_cell(path: Path) -> FinalPerCellReduction:
    """Reduce the five audited final cells without cross-cell comparisons."""

    manifest_payload, loaded, invalidated = load_final_input(path)

    tables: dict[str, list[dict[str, Any]]] = {
        name: [] for name in PER_CELL_TABLE_NAMES
    }
    evidence: list[dict[str, Any]] = []
    lexicons: dict[str, LexiconReduction] = {}
    boundaries: dict[str, BoundaryReduction] = {}

    try:
        for cell in loaded:
            cell_id = cell.spec.cell_id

            pass_rows, _pass_count = _reduce_passes(cell)
            lexicon = _reduce_lexicon(cell)
            analyses = _reduce_analyses(cell)
            boundary = _reduce_boundaries(cell)

            if analyses.id_digest != boundary.id_digest:
                raise GateValidationError(
                    (
                        f"{cell_id}: analyses and boundary "
                        "segment identities/order differ",
                    )
                )

            rules, rule_count = _reduce_rules(
                cell,
                segments=analyses.row_count,
                expected_boundaries=boundary.expected_boundary_total,
                phonemes=analyses.phoneme_count,
                topk_rule_mass=analyses.topk_rule_mass,
            )
            runtime = _reduce_runtime(
                cell,
                phonemes=analyses.phoneme_count,
            )

            lexicons[cell_id] = lexicon
            boundaries[cell_id] = boundary

            tables["pass_dynamics"].extend(pass_rows)
            tables["lexicon_distribution"].extend(
                lexicon.distribution_rows
            )
            tables["lexical_length"].extend(lexicon.length_rows)
            tables["reuse_distribution"].extend(lexicon.reuse_rows)
            tables["ambiguity_distribution"].extend(
                analyses.ambiguity_rows
            )
            tables["boundary_distribution"].extend(boundary.rows)
            tables["rule_usage"].extend(rules)
            tables["candidate_scaling"].extend(
                analyses.candidate_rows
            )
            tables["document_distribution"].extend(
                analyses.document_rows
            )
            tables["length_strata"].extend(analyses.length_rows)
            tables["runtime_breakdown"].extend(runtime)

            evidence.extend(lexicon.evidence)
            evidence.extend(analyses.evidence)
            evidence.extend(boundary.evidence)

            exact_rule_rows = [
                row
                for row in rules
                if row.get("family") == "exact_global_rule"
            ]
            for category, ordered_rules in (
                (
                    "common_rules",
                    exact_rule_rows[:EVIDENCE_LIMIT],
                ),
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
                    "expected_boundaries": (
                        boundary.expected_boundary_total
                    ),
                    "rules": rule_count,
                }
            )

    except GateValidationError as exc:
        raise FinalValidationError(exc.errors) from exc

    evidence.sort(
        key=lambda row: (
            str(row.get("cell_id", "")),
            str(row.get("category", "")),
            str(row.get("source_id", "")),
        )
    )

    return FinalPerCellReduction(
        manifest_payload=manifest_payload,
        invalidated=invalidated,
        loaded=loaded,
        tables=tables,
        evidence=evidence,
        lexicons=lexicons,
        boundaries=boundaries,
    )


FORMAL_SCALAR_TABLES = {
    "cells": "scientific_summary",
    "pass_dynamics": "training_dynamics",
    "lexicon_distribution": "scientific",
    "lexical_length": "scientific",
    "reuse_distribution": "scientific",
    "ambiguity_distribution": "scientific",
    "boundary_distribution": "scientific",
    "rule_usage": "scientific",
    "candidate_scaling": "computational_diagnostic",
    "runtime_breakdown": "engineering",
}

FORMAL_ROW_IDENTITY_FIELDS = {
    "cells": (),
    "pass_dynamics": ("pass", "metric"),
    "lexicon_distribution": ("family", "metric"),
    "lexical_length": ("weighting", "threshold"),
    "reuse_distribution": ("family", "metric"),
    "ambiguity_distribution": ("family", "metric"),
    "boundary_distribution": ("family", "metric"),
    "rule_usage": ("family", "metric"),
    "candidate_scaling": ("family", "metric"),
    "runtime_breakdown": ("family", "metric"),
}

FORMAL_SCOPE_FIELDS = (
    "estimate_scope",
    "scope",
    "quantile_method",
    "formula",
    "usage_semantics",
    "interpretation",
    "inclusion_note",
)

FORMAL_NONVALUE_FIELDS = {
    "cell_id",
    "script",
    "condition",
    "run_id",
    "metrics_id",
    "scientific_git_sha",
    "rank",
}


def _formal_row_identity(
    table_name: str,
    row: dict[str, Any],
) -> str:
    fields = FORMAL_ROW_IDENTITY_FIELDS[table_name]
    if not fields:
        return "summary"
    return "|".join(
        f"{field}={row.get(field)!s}"
        for field in fields
        if field in row
    )


def _formal_scope(row: dict[str, Any]) -> str:
    return "; ".join(
        f"{field}={row[field]}"
        for field in FORMAL_SCOPE_FIELDS
        if field in row and row[field] not in (None, "")
    )


def _collect_formal_scalars(
    reduction: FinalPerCellReduction,
) -> dict[
    str,
    dict[tuple[str, str, str], tuple[float, str, str]],
]:
    known_cells = {
        cell.spec.cell_id
        for cell in reduction.loaded
    }
    values: dict[
        str,
        dict[tuple[str, str, str], tuple[float, str, str]],
    ] = {
        cell_id: {}
        for cell_id in known_cells
    }

    for table_name, domain in FORMAL_SCALAR_TABLES.items():
        for row in reduction.tables[table_name]:
            cell_id = row.get("cell_id")
            if cell_id not in known_cells:
                raise FinalValidationError(
                    (
                        f"{table_name}: unknown or missing cell_id "
                        f"{cell_id!r}",
                    )
                )

            identity = _formal_row_identity(table_name, row)
            identity_fields = set(
                FORMAL_ROW_IDENTITY_FIELDS[table_name]
            )
            scope = _formal_scope(row)

            for field, raw_value in row.items():
                if (
                    field in FORMAL_NONVALUE_FIELDS
                    or field in identity_fields
                    or field in FORMAL_SCOPE_FIELDS
                    or isinstance(raw_value, bool)
                    or not isinstance(raw_value, (int, float))
                ):
                    continue

                value = float(raw_value)
                if not math.isfinite(value):
                    raise FinalValidationError(
                        (
                            f"{cell_id}: non-finite formal scalar "
                            f"{table_name}/{identity}/{field}",
                        )
                    )

                key = (table_name, identity, field)
                if key in values[cell_id]:
                    raise FinalValidationError(
                        (
                            f"{cell_id}: duplicate formal scalar "
                            f"{table_name}/{identity}/{field}",
                        )
                    )
                values[cell_id][key] = (value, scope, domain)

    return values


def build_formal_comparisons(
    reduction: FinalPerCellReduction,
) -> list[dict[str, Any]]:
    """Build exactly the six frozen designated scalar contrasts."""

    cell_ids = {
        cell.spec.key: cell.spec.cell_id
        for cell in reduction.loaded
    }
    if set(cell_ids) != set(FINAL_VALID_CELLS):
        raise FinalValidationError(
            ("formal comparison input is not the exact five-cell set",)
        )

    scalars = _collect_formal_scalars(reduction)
    rows: list[dict[str, Any]] = []

    for pair in FORMAL_COMPARISONS:
        cell_a = cell_ids[pair.cell_a]
        cell_b = cell_ids[pair.cell_b]
        shared = sorted(
            set(scalars[cell_a]) & set(scalars[cell_b])
        )

        if not shared:
            raise FinalValidationError(
                (
                    f"{pair.pair_id}: no shared scalar quantities "
                    "available for formal comparison",
                )
            )

        for table_name, identity, field in shared:
            value_a, scope_a, domain_a = scalars[cell_a][
                (table_name, identity, field)
            ]
            value_b, scope_b, domain_b = scalars[cell_b][
                (table_name, identity, field)
            ]
            if domain_a != domain_b:
                raise FinalValidationError(
                    (
                        f"{pair.pair_id}: scalar domain mismatch for "
                        f"{table_name}/{identity}/{field}",
                    )
                )

            difference = value_b - value_a
            rows.append(
                {
                    "pair_id": pair.pair_id,
                    "comparison_kind": pair.kind,
                    "cell_a": cell_a,
                    "cell_b": cell_b,
                    "source_table": table_name,
                    "domain": domain_a,
                    "row_identity": identity,
                    "value_field": field,
                    "value_a": value_a,
                    "value_b": value_b,
                    "signed_difference_b_minus_a": difference,
                    "relative_change_from_a": (
                        None
                        if value_a == 0.0
                        else difference / abs(value_a)
                    ),
                    "ratio_b_over_a": (
                        None
                        if value_a == 0.0
                        else value_b / value_a
                    ),
                    "scope_a": scope_a,
                    "scope_b": scope_b,
                }
            )

    return rows


FINAL_TABLE_NAMES = PER_CELL_TABLE_NAMES + (
    "formal_comparisons",
    "failure_mode_indicators",
)

FAILURE_EFFECT_TABLES = {
    "cells",
    "lexicon_distribution",
    "lexical_length",
    "reuse_distribution",
    "ambiguity_distribution",
    "boundary_distribution",
    "rule_usage",
}


def _lexicon_failure_rows(cell: LoadedCell) -> list[dict[str, Any]]:
    path = cell.spec.run_dir / "latent_lexicon.tsv"
    long_stats = {t: [0.0, 0.0] for t in LENGTH_MASS_THRESHOLDS}
    low_context = {t: [0.0, 0.0] for t in REUSE_THRESHOLDS}
    low_surface = {t: [0.0, 0.0] for t in REUSE_THRESHOLDS}
    long_low_context = {(l, r): [0.0, 0.0] for l in LENGTH_MASS_THRESHOLDS for r in REUSE_THRESHOLDS}
    long_low_surface = {(l, r): [0.0, 0.0] for l in LENGTH_MASS_THRESHOLDS for r in REUSE_THRESHOLDS}
    total_types = 0
    total_mass = 0.0

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"form_key", "phoneme_ids", "expected_count", "number_of_surface_variants", "number_of_contexts"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise GateValidationError((f"{cell.spec.cell_id}: latent lexicon header lacks fields needed for final indicators",))
        for line_number, row in enumerate(reader, start=2):
            label = f"{path}:{line_number}"
            phoneme_ids = row.get("phoneme_ids", "").split()
            if not phoneme_ids:
                raise GateValidationError((f"{label}: phoneme_ids must be nonempty",))
            count = _number(row.get("expected_count"), f"{label} expected_count", nonnegative=True)
            contexts = _integer(row.get("number_of_contexts"), f"{label} contexts")
            variants = _integer(row.get("number_of_surface_variants"), f"{label} surface variants")
            length = len(phoneme_ids)
            total_types += 1
            total_mass += count
            for t in LENGTH_MASS_THRESHOLDS:
                if length >= t:
                    long_stats[t][0] += 1
                    long_stats[t][1] += count
            for t in REUSE_THRESHOLDS:
                if contexts < t:
                    low_context[t][0] += 1
                    low_context[t][1] += count
                if variants < t:
                    low_surface[t][0] += 1
                    low_surface[t][1] += count
            for l in LENGTH_MASS_THRESHOLDS:
                if length < l:
                    continue
                for r in REUSE_THRESHOLDS:
                    if contexts < r:
                        long_low_context[(l, r)][0] += 1
                        long_low_context[(l, r)][1] += count
                    if variants < r:
                        long_low_surface[(l, r)][0] += 1
                        long_low_surface[(l, r)][1] += count

    if total_types <= 0 or total_mass <= 0.0:
        raise GateValidationError((f"{cell.spec.cell_id}: final lexicon indicators require positive lexical support",))

    def emit(family: str, metric: str, values: list[float], **extra: Any) -> dict[str, Any]:
        return {
            "indicator_family": family,
            "cell_id": cell.spec.cell_id,
            "metric": metric,
            "type_count": int(values[0]),
            "type_fraction": values[0] / total_types,
            "expected_mass": values[1],
            "expected_mass_fraction": values[1] / total_mass,
            "scope": "exact_final_lexicon_stream",
            **extra,
        }

    rows: list[dict[str, Any]] = []
    rows.extend(emit("long_form_lexicalization", f"phoneme_length>={t}", long_stats[t], length_threshold=t) for t in LENGTH_MASS_THRESHOLDS)
    for t in REUSE_THRESHOLDS:
        rows.append(emit("low_reuse_memorization", f"contexts<{t}", low_context[t], reuse_axis="contexts", reuse_threshold=t))
        rows.append(emit("low_reuse_memorization", f"surface_variants<{t}", low_surface[t], reuse_axis="surface_variants", reuse_threshold=t))
    for l in LENGTH_MASS_THRESHOLDS:
        for r in REUSE_THRESHOLDS:
            rows.append(emit("long_low_reuse_memorization", f"phoneme_length>={l};contexts<{r}", long_low_context[(l, r)], length_threshold=l, reuse_axis="contexts", reuse_threshold=r))
            rows.append(emit("long_low_reuse_memorization", f"phoneme_length>={l};surface_variants<{r}", long_low_surface[(l, r)], length_threshold=l, reuse_axis="surface_variants", reuse_threshold=r))
    return rows


def _formal_effect_relevant(row: dict[str, Any]) -> bool:
    if row.get("domain") != "scientific" or row.get("source_table") not in FAILURE_EFFECT_TABLES:
        return False
    if row.get("source_table") == "rule_usage":
        identity = str(row.get("row_identity", ""))
        return identity.startswith("family=exact_global_summary") or identity.startswith("family=exact_global_top_n")
    return True


def build_failure_mode_indicators(reduction: FinalPerCellReduction, formal_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for cell in reduction.loaded:
            rows.extend(_lexicon_failure_rows(cell))
    except GateValidationError as exc:
        raise FinalValidationError(exc.errors) from exc

    for row in reduction.tables["ambiguity_distribution"]:
        if row.get("family") == "segment_posterior" and row.get("metric") in {"identity_mass", "latent_mass"}:
            rows.append({"indicator_family": "identity_latent_concentration", "source_table": "ambiguity_distribution", **row})

    spacing_pairs = {"spacing_iast_surface_to_legacy", "spacing_devanagari_surface_to_legacy"}
    stress_pairs = {"stress_devanagari_surface_to_continuous", "stress_devanagari_legacy_to_continuous"}
    for row in formal_rows:
        pair_id = row["pair_id"]
        if pair_id in spacing_pairs and _formal_effect_relevant(row):
            rows.append({"indicator_family": "spacing_removal_lexicalization", **row})
        if pair_id in stress_pairs and _formal_effect_relevant(row):
            rows.append({"indicator_family": "devanagari_continuous_stress", **row})
        if row.get("source_table") == "rule_usage" and str(row.get("row_identity", "")).startswith("family=exact_global_summary"):
            rows.append({"indicator_family": "sandhi_use_displacement", **row})

    rows.sort(key=lambda row: (str(row.get("indicator_family", "")), str(row.get("cell_id", "")), str(row.get("pair_id", "")), str(row.get("metric", "")), str(row.get("row_identity", "")), str(row.get("value_field", ""))))
    return rows


def _designated_difference_evidence(formal_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for pair in FORMAL_COMPARISONS:
        candidates: list[tuple[float, str, str, str, dict[str, Any]]] = []
        for row in formal_rows:
            if row["pair_id"] != pair.pair_id or row.get("domain") != "scientific":
                continue
            relative = row.get("relative_change_from_a")
            if isinstance(relative, (int, float)):
                score = abs(float(relative)); score_kind = "absolute_relative_change"
            else:
                score = abs(float(row["signed_difference_b_minus_a"])); score_kind = "absolute_signed_difference"
            candidates.append((score, str(row["source_table"]), str(row["row_identity"]), str(row["value_field"]), {
                "cell_id": "cross_cell",
                "category": f"designated_cross_condition_differences:{pair.pair_id}",
                "source_id": f"{pair.pair_id}:{row['source_table']}:{row['row_identity']}:{row['value_field']}",
                "source_artifact": "derived_formal_comparisons",
                "pair_id": pair.pair_id,
                "comparison_kind": pair.kind,
                "source_table": row["source_table"],
                "row_identity": row["row_identity"],
                "value_field": row["value_field"],
                "value_a": row["value_a"],
                "value_b": row["value_b"],
                "signed_difference_b_minus_a": row["signed_difference_b_minus_a"],
                "relative_change_from_a": row["relative_change_from_a"],
                "ratio_b_over_a": row["ratio_b_over_a"],
                "selection_score": score,
                "selection_score_kind": score_kind,
                "scope_a": row["scope_a"],
                "scope_b": row["scope_b"],
            }))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))
        evidence.extend(item[4] for item in candidates[:EVIDENCE_LIMIT])
    return evidence


def _compact_effect_rows(formal_rows: list[dict[str, Any]], *, kind: str) -> list[dict[str, Any]]:
    return [row for row in formal_rows if row.get("comparison_kind") == kind and _formal_effect_relevant(row)]


def build_decision_inputs(reduction: FinalPerCellReduction, formal_rows: list[dict[str, Any]], failure_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "status": "objective_evidence_only",
        "interpretation_contract": "Machine-readable evidence for human scientific interpretation.",
        "valid_cells": [{"cell_id": cell.spec.cell_id, "script": cell.spec.script, "condition": cell.spec.condition, "scientific_git_sha": cell.spec.scientific_commit} for cell in reduction.loaded],
        "invalidated_cell": asdict(reduction.invalidated),
        "lexicon_economy": [row for row in reduction.tables["lexicon_distribution"] if row.get("family") in {"diversity", "mass_support", "top_mass"}],
        "long_form_and_reuse": [row for row in failure_rows if row.get("indicator_family") in {"long_form_lexicalization", "low_reuse_memorization", "long_low_reuse_memorization"}],
        "posterior_balance": [row for row in failure_rows if row.get("indicator_family") == "identity_latent_concentration"],
        "sandhi_use": [row for row in reduction.tables["rule_usage"] if row.get("family") == "exact_global_summary"],
        "designated_effects": {
            "controlled_script": _compact_effect_rows(formal_rows, kind="controlled_script"),
            "controlled_spacing": _compact_effect_rows(formal_rows, kind="controlled_spacing"),
            "continuous_stress": _compact_effect_rows(formal_rows, kind="continuous_stress"),
        },
        "computational_diagnostics": [row for row in formal_rows if row.get("domain") == "computational_diagnostic"],
        "engineering_evidence": [row for row in formal_rows if row.get("domain") == "engineering"],
        "s1m2_relevance": {
            "evidence_families": ["long_form_lexicalization", "low_reuse_memorization", "long_low_reuse_memorization", "identity_latent_concentration", "spacing_removal_lexicalization", "devanagari_continuous_stress", "sandhi_use_displacement"],
            "interpretation": "These indicators bear on later S1M2 motivation without encoding a scientific conclusion.",
        },
    }


def _build_sources(path: Path, reduction: FinalPerCellReduction) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    cells_by_id = {row["cell_id"]: row for row in reduction.tables["cells"]}
    for cell in reduction.loaded:
        cell_id = cell.spec.cell_id
        summary_row = cells_by_id[cell_id]
        pass_count = len({int(row["pass"]) for row in reduction.tables["pass_dynamics"] if row.get("cell_id") == cell_id})
        row_counts = {
            "iteration_metrics.json": pass_count,
            "summary.json": 1,
            "analyses.jsonl": int(summary_row["segments"]),
            "boundary_posteriors.jsonl": reduction.boundaries[cell_id].row_count,
            "latent_lexicon.tsv": reduction.lexicons[cell_id].row_count,
            "rule_usage.tsv": int(summary_row["rules"]),
            "config.json": 1,
            "checkpoint.json": 1,
            "provenance.json": 1,
            "timing_metrics.json": 1,
            "inspection_report.md": None,
        }
        sources.extend(_source_entry(cell, name, base=path.parent, row_count=row_counts.get(name)) for name in SOURCE_FILES)
        process_path = cell.spec.metrics_dir / "process_tree_summary.json"
        sources.append({
            "cell_id": cell_id, "run_id": cell.spec.run_id, "metrics_id": cell.spec.metrics_id,
            "script": cell.spec.script, "condition": cell.spec.condition,
            "relative_path": _relative_path(process_path, path.parent), "bytes": process_path.stat().st_size,
            "row_count": 1, "sha256": _file_sha256(process_path), "scientific_git_sha": cell.spec.scientific_commit,
            "artifact_schema_or_header": cell.process.get("schema_version"), "config_signature": cell.provenance.get("config_signature"),
        })
        sources.append({
            "cell_id": cell_id, "run_id": cell.spec.run_id, "metrics_id": cell.spec.metrics_id,
            "script": cell.spec.script, "condition": cell.spec.condition,
            "relative_path": _relative_path(cell.spec.audit_path, path.parent), "bytes": cell.spec.audit_path.stat().st_size,
            "row_count": 1, "sha256": _file_sha256(cell.spec.audit_path), "scientific_git_sha": cell.spec.scientific_commit,
            "artifact_schema_or_header": cell.audit.get("schema_version"), "config_signature": cell.provenance.get("config_signature"),
            "identity_role": "completed_collection_final_audit",
        })
    return sources


def render_final_summary(result: dict[str, Any]) -> str:
    tables = result["tables"]; manifest = result["manifest"]
    lines = [
        "# S1M1 final analysis", "",
        "> **Implementation status:** PROVISIONAL until the complete real five-cell execution and S1M1 result freeze.", "",
        "The final reduction contains five completed/audited scientific cells and the frozen IAST-continuous invalidation record.", "",
        "| Cell | Segments | Phonemes | Lexical types | Expected boundaries |",
        "|---|---:|---:|---:|---:|",
    ]
    for cell in tables["cells"]:
        lines.append(f"| {cell['cell_id']} | {cell['segments']} | {cell['surface_phonemes']} | {cell['lexical_types']} | {cell['expected_boundaries']:.6g} |")
    lines.extend(("", "## Designated formal comparisons", ""))
    pair_counts: dict[str, int] = {}
    for row in tables["formal_comparisons"]:
        pair_counts[row["pair_id"]] = pair_counts.get(row["pair_id"], 0) + 1
    for pair in FORMAL_COMPARISONS:
        lines.append(f"- `{pair.pair_id}` ({pair.kind}): {pair_counts.get(pair.pair_id, 0)} scalar rows")
    invalidated = manifest["invalidated_cells"][0]
    lines.extend(("", "## Invalidated representation", "", f"- IAST `continuous`: {invalidated['scientific_status']}; {invalidated['formal_comparison']}.", "", "## Interpretation contract", "", "Formal comparisons and failure-mode indicators are objective evidence. Runtime/resource quantities remain separate engineering evidence. Scientific conclusions are assigned during the S1M1 result review.", ""))
    return "\n".join(lines)


def reduce_final_manifest(path: Path) -> dict[str, Any]:
    path = path.resolve(); reduction = reduce_final_per_cell(path)
    formal_rows = build_formal_comparisons(reduction)
    failure_rows = build_failure_mode_indicators(reduction, formal_rows)
    tables = {name: list(rows) for name, rows in reduction.tables.items()}
    tables["formal_comparisons"] = formal_rows; tables["failure_mode_indicators"] = failure_rows
    evidence = list(reduction.evidence); evidence.extend(_designated_difference_evidence(formal_rows))
    evidence.sort(key=lambda row: (str(row.get("cell_id", "")), str(row.get("category", "")), str(row.get("source_id", ""))))
    decision_inputs = build_decision_inputs(reduction, formal_rows, failure_rows)
    try:
        sources = _build_sources(path, reduction); input_sha256 = _file_sha256(path)
    except GateValidationError as exc:
        raise FinalValidationError(exc.errors) from exc
    except OSError as exc:
        raise FinalValidationError((f"final source provenance collection failed: {exc}",)) from exc
    payload = reduction.manifest_payload
    manifest = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "analysis_id": payload["analysis_id"],
        "scientific_contract_id": payload["scientific_contract_id"],
        "analysis_plan_status": "FROZEN",
        "implementation_status": "PROVISIONAL",
        "result_status": "NOT_YET_FROZEN",
        "source_manifest": _relative_path(path, path.parent),
        "source_manifest_sha256": input_sha256,
        "approved_scientific_commits": payload["approved_scientific_commits"],
        "cross_commit_compatibility": payload.get("cross_commit_compatibility"),
        "valid_cells": [{"cell_id": cell.spec.cell_id, "script": cell.spec.script, "condition": cell.spec.condition, "run_id": cell.spec.run_id, "metrics_id": cell.spec.metrics_id, "scientific_git_sha": cell.spec.scientific_commit} for cell in reduction.loaded],
        "invalidated_cells": [asdict(reduction.invalidated)],
        "formal_comparisons": [{"pair_id": pair.pair_id, "kind": pair.kind, "cell_a": list(pair.cell_a), "cell_b": list(pair.cell_b)} for pair in FORMAL_COMPARISONS],
        "retained_evidence_limit_per_category": EVIDENCE_LIMIT,
        "sources": sources,
    }
    result = {"schema_version": OUTPUT_SCHEMA_VERSION, "manifest": manifest, "tables": tables, "evidence_samples": evidence, "decision_inputs": decision_inputs}
    result["summary"] = render_final_summary(result)
    return result


def write_final_outputs(result: dict[str, Any], output_dir: Path) -> None:
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        (temporary / "manifest.json").write_text(json.dumps(result["manifest"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="")
        for name in FINAL_TABLE_NAMES:
            _write_tsv(temporary / f"{name}.tsv", result["tables"][name])
        with (temporary / "evidence_samples.jsonl").open("x", encoding="utf-8", newline="") as handle:
            for row in result["evidence_samples"]:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        (temporary / "decision_inputs.json").write_text(json.dumps(result["decision_inputs"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="")
        (temporary / "summary.md").write_text(result["summary"], encoding="utf-8", newline="")
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
