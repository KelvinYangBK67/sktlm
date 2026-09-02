"""Final S1M1 analysis contract and validation.

The scientific analysis plan is frozen in
reports/core_methods/latent_lexicon/s1m1_final_analysis_plan.md.

This implementation remains provisional until complete real-data execution
and the S1M1 result freeze.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .s1m1_archival import (
    EVIDENCE_LIMIT,
    BoundaryReduction,
    LexiconReduction,
    _reduce_analyses,
    _reduce_boundaries,
    _reduce_lexicon,
    _reduce_passes,
    _reduce_rules,
    _reduce_runtime,
)

from .six_representation_gate import (
    CellSpec,
    GateValidationError,
    LoadedCell,
    PairSpec,
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
