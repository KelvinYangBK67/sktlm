"""Generic fail-closed aggregation for declared representation cells.

V2 separates the declared universe from supplied scientific artifacts. Missing
cells are explicit N/A; supplied cells retain the historical strict validator.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .six_representation_gate import (
    CellSpec, GateValidationError, _cell_scalar_metrics, _is_full_sha,
    _load_cell, _read_json_object, _resolve_local_path,
    _validate_cross_cell_contract, jensen_shannon_nats,
    scalar_comparison, total_variation,
)

SCHEMA_VERSION = "sktlm-representation-analysis-input/v2"
OUTPUT_SCHEMA_VERSION = "sktlm-representation-analysis-aggregation/v2"
DEFAULT_TOP_K = (100, 1000, 10000)


class CellStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NA_NOT_PROVIDED = "NA_NOT_PROVIDED"
    NA_SCIENTIFICALLY_EXCLUDED = "NA_SCIENTIFICALLY_EXCLUDED"
    NA_EXECUTION_INCOMPLETE = "NA_EXECUTION_INCOMPLETE"
    NA_NOT_APPLICABLE = "NA_NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class CellDeclaration:
    cell_id: str
    script: str
    representation: str
    status: CellStatus
    reason: str | None
    provenance_evidence: Mapping[str, Any] | None
    runtime_evidence: Mapping[str, Any] | None
    termination_evidence: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class DeclaredPair:
    pair_id: str
    kind: str
    cell_a: str
    cell_b: str


@dataclass(frozen=True, slots=True)
class ProtocolInput:
    manifest: Mapping[str, Any]
    analysis_id: str
    declarations: tuple[CellDeclaration, ...]
    supplied: Mapping[str, CellSpec]
    pairs: tuple[DeclaredPair, ...]
    top_k_values: tuple[int, ...]


def _nonempty(value: object, label: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a nonempty string")
        return ""
    return value.strip()


def _parse_manifest(path: Path) -> ProtocolInput:
    raw = _read_json_object(path, "representation analysis manifest")
    errors: list[str] = []
    if raw.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    analysis_id = _nonempty(raw.get("analysis_id"), "analysis_id", errors)
    universe = raw.get("cell_universe")
    if not isinstance(universe, list):
        errors.append("cell_universe must be a list")
        universe = []

    declarations: list[CellDeclaration] = []
    cell_ids: set[str] = set()
    dimensions: set[tuple[str, str]] = set()
    for index, item in enumerate(universe):
        label = f"cell_universe[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        cell_id = _nonempty(item.get("cell_id"), f"{label}.cell_id", errors)
        script = _nonempty(item.get("script"), f"{label}.script", errors)
        representation = _nonempty(
            item.get("representation", item.get("spacing")),
            f"{label}.representation", errors,
        )
        try:
            status = CellStatus(item.get("status"))
        except (TypeError, ValueError):
            errors.append(f"{label}.status is unknown: {item.get('status')!r}")
            continue
        reason = item.get("reason")
        if status is not CellStatus.AVAILABLE and (
            not isinstance(reason, str) or not reason.strip()
        ):
            errors.append(f"{label}.reason is required for N/A status")
        if reason is not None and not isinstance(reason, str):
            errors.append(f"{label}.reason must be a string or null")
            reason = None
        if cell_id in cell_ids:
            errors.append(f"duplicate declared cell_id: {cell_id}")
        cell_ids.add(cell_id)
        dimension = (script, representation)
        if dimension in dimensions:
            errors.append(f"duplicate script/representation cell: {dimension!r}")
        dimensions.add(dimension)
        provenance_evidence = item.get("provenance_evidence")
        runtime = item.get("runtime_evidence")
        termination = item.get("termination_evidence")
        if provenance_evidence is not None and not isinstance(provenance_evidence, dict):
            errors.append(f"{label}.provenance_evidence must be an object or null")
            provenance_evidence = None
        if runtime is not None and not isinstance(runtime, dict):
            errors.append(f"{label}.runtime_evidence must be an object or null")
            runtime = None
        if termination is not None and not isinstance(termination, dict):
            errors.append(f"{label}.termination_evidence must be an object or null")
            termination = None
        declarations.append(CellDeclaration(
            cell_id, script, representation, status,
            reason.strip() if isinstance(reason, str) else None,
            provenance_evidence, runtime, termination,
        ))

    supplied_raw = raw.get("supplied_cells", [])
    if not isinstance(supplied_raw, list):
        errors.append("supplied_cells must be a list")
        supplied_raw = []
    base = path.parent
    supplied: dict[str, CellSpec] = {}
    declaration_by_id = {cell.cell_id: cell for cell in declarations}
    for index, item in enumerate(supplied_raw):
        label = f"supplied_cells[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        cell_id = _nonempty(item.get("cell_id"), f"{label}.cell_id", errors)
        declaration = declaration_by_id.get(cell_id)
        if cell_id in supplied:
            errors.append(f"duplicate supplied cell_id: {cell_id}")
            continue
        if declaration is None:
            errors.append(f"supplied cell is not in cell_universe: {cell_id}")
            continue
        if declaration.status is not CellStatus.AVAILABLE:
            errors.append(f"N/A cell must not be supplied as complete: {cell_id}")
            continue
        commit = item.get("scientific_commit", item.get("expected_commit"))
        if not _is_full_sha(commit):
            errors.append(f"{label}.scientific_commit must be a full lowercase SHA-1")
            commit = ""
        try:
            supplied[cell_id] = CellSpec(
                script=declaration.script,
                condition=declaration.representation,
                run_id=_nonempty(item.get("run_id"), f"{label}.run_id", errors),
                metrics_id=_nonempty(item.get("metrics_id"), f"{label}.metrics_id", errors),
                scientific_commit=str(commit),
                run_dir=_resolve_local_path(base, item.get("run_dir", item.get("collected_dir")), f"{label}.run_dir"),
                metrics_dir=_resolve_local_path(base, item.get("metrics_dir"), f"{label}.metrics_dir"),
                audit_path=_resolve_local_path(base, item.get("audit_path"), f"{label}.audit_path"),
            )
        except GateValidationError as exc:
            errors.extend(exc.errors)

    for declaration in declarations:
        if declaration.status is CellStatus.AVAILABLE and declaration.cell_id not in supplied:
            errors.append(f"AVAILABLE cell lacks supplied artifacts: {declaration.cell_id}")

    for name, values in (
        ("run_id", [spec.run_id for spec in supplied.values()]),
        ("metrics_id", [spec.metrics_id for spec in supplied.values()]),
    ):
        repeated = sorted(value for value in set(values) if values.count(value) > 1)
        if repeated:
            errors.append(f"duplicate {name} values: {repeated}")

    approved = raw.get("approved_scientific_commits")
    if not isinstance(approved, list):
        errors.append("approved_scientific_commits must be a list")
        approved = []
    approved_set = set(approved)
    if any(not _is_full_sha(value) for value in approved):
        errors.append("approved_scientific_commits contains an invalid SHA-1")
    elif approved != sorted(approved_set):
        errors.append("approved_scientific_commits must be unique and sorted")
    for cell_id, spec in supplied.items():
        if spec.scientific_commit not in approved_set:
            errors.append(f"{cell_id}: scientific_commit is not approved")
    supplied_commits = {spec.scientific_commit for spec in supplied.values()}
    if approved_set != supplied_commits:
        errors.append("approved_scientific_commits must exactly match supplied cell provenance")
    if len(supplied_commits) > 1:
        compatibility = raw.get("cross_commit_compatibility")
        if not isinstance(compatibility, dict):
            errors.append("cross_commit_compatibility is required for multiple supplied commits")
        else:
            if compatibility.get("status") != "approved":
                errors.append("cross_commit_compatibility.status must be 'approved'")
            if not isinstance(compatibility.get("basis"), str) or not compatibility["basis"].strip():
                errors.append("cross_commit_compatibility.basis must be explicit")
            evidence = compatibility.get("evidence")
            if not isinstance(evidence, list) or not evidence or not all(isinstance(value, str) and value for value in evidence):
                errors.append("cross_commit_compatibility.evidence must list tracked evidence")

    pairs_raw = raw.get("pairwise_comparisons", [])
    if not isinstance(pairs_raw, list):
        errors.append("pairwise_comparisons must be a list")
        pairs_raw = []
    pairs: list[DeclaredPair] = []
    pair_ids: set[str] = set()
    for index, item in enumerate(pairs_raw):
        label = f"pairwise_comparisons[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        pair_id = _nonempty(item.get("pair_id"), f"{label}.pair_id", errors)
        kind = _nonempty(item.get("kind"), f"{label}.kind", errors)
        cell_a = _nonempty(item.get("cell_a"), f"{label}.cell_a", errors)
        cell_b = _nonempty(item.get("cell_b"), f"{label}.cell_b", errors)
        if pair_id in pair_ids:
            errors.append(f"duplicate pair_id: {pair_id}")
        pair_ids.add(pair_id)
        if cell_a not in declaration_by_id or cell_b not in declaration_by_id:
            errors.append(f"{label} references an undeclared cell")
        if cell_a == cell_b:
            errors.append(f"{label} endpoints must differ")
        pairs.append(DeclaredPair(pair_id, kind, cell_a, cell_b))

    top_k_raw = raw.get("top_k_values", list(DEFAULT_TOP_K))
    if not isinstance(top_k_raw, list) or not top_k_raw or any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in top_k_raw
    ):
        errors.append("top_k_values must be a nonempty list of positive integers")
        top_k = DEFAULT_TOP_K
    else:
        top_k = tuple(sorted(set(top_k_raw)))
    if errors:
        raise GateValidationError(errors)
    return ProtocolInput(raw, analysis_id, tuple(declarations), supplied, tuple(pairs), top_k)


SCIENTIFIC_METRICS = (
    "active_lexical_types", "expected_lexical_tokens",
    "lexical_expected_count_total", "identity_posterior_mass_total",
    "latent_posterior_mass_total", "mean_identity_mass", "mean_latent_mass",
    "mean_top1_posterior", "mean_posterior_entropy",
    "low_count_lexical_types", "low_count_fraction", "complexity_raw",
    "complexity_penalty", "documents", "segments", "characters",
    "candidate_factors", "candidate_nodes", "candidate_edges",
    "overflowed_tokens", "overflow_frequency_per_segment",
    "external_rule_expected_usage_total", "external_rule_nonzero_count",
    "external_rule_zero_count", "external_rule_nonzero_coverage",
) + tuple(f"lexical_types_for_{value}_mass" for value in ("90%", "95%", "99%", "99.9%", "99.99%"))

ENGINEERING_METRICS = (
    "wall_seconds", "peak_process_tree_rss_bytes",
    "sampled_process_tree_cpu_seconds", "peak_process_count",
    "sampled_process_tree_read_bytes", "sampled_process_tree_write_bytes",
    "logical_cpu_count",
)


def _top_forms(path: Path, maximum: int) -> tuple[str, ...]:
    forms: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or "form_key" not in reader.fieldnames:
            raise GateValidationError((f"latent lexicon has invalid header: {path}",))
        for row in reader:
            if len(forms) == maximum:
                break
            forms.append(row["form_key"])
    return tuple(forms)


def _na_metric_row(reason: str) -> dict[str, Any]:
    return {
        "comparison_status": "N/A", "reason": reason,
        "value_a": None, "value_b": None, "absolute_difference": None,
        "signed_difference_b_minus_a": None,
        "relative_difference_b_minus_a_over_abs_a": None,
        "ratio_b_over_a": None, "denominator_zero": None,
    }


def aggregate_manifest(manifest_path: Path) -> dict[str, Any]:
    """Validate supplied cells and aggregate only AVAILABLE scientific cells."""

    protocol = _parse_manifest(manifest_path.resolve())
    declarations = {cell.cell_id: cell for cell in protocol.declarations}
    loaded_by_id: dict[str, Any] = {}
    errors: list[str] = []
    for cell_id, spec in protocol.supplied.items():
        try:
            loaded_by_id[cell_id] = _load_cell(spec)
        except GateValidationError as exc:
            errors.extend(f"{cell_id}: {error}" for error in exc.errors)
    if errors:
        raise GateValidationError(errors)
    loaded = tuple(loaded_by_id.values())
    if loaded:
        _validate_cross_cell_contract(loaded)

    cell_payloads: dict[str, dict[str, Any]] = {}
    scientific_scalars: dict[str, dict[str, Any]] = {}
    top_forms: dict[str, tuple[str, ...]] = {}
    for declaration in protocol.declarations:
        if declaration.status is CellStatus.AVAILABLE:
            loaded_cell = loaded_by_id[declaration.cell_id]
            payload, _ = _cell_scalar_metrics(loaded_cell)
            payload.update({
                "cell_id": declaration.cell_id,
                "representation": declaration.representation,
                "status": declaration.status.value,
                "reason": None,
                "provenance_evidence": declaration.provenance_evidence,
                "runtime_evidence": declaration.runtime_evidence,
                "termination_evidence": declaration.termination_evidence,
            })
            scientific_scalars[declaration.cell_id] = payload["scientific_metrics"]
            top_forms[declaration.cell_id] = _top_forms(
                loaded_cell.spec.run_dir / "latent_lexicon.tsv",
                max(protocol.top_k_values),
            )
        else:
            payload = {
                "cell_id": declaration.cell_id,
                "script": declaration.script,
                "condition": declaration.representation,
                "representation": declaration.representation,
                "status": declaration.status.value,
                "reason": declaration.reason,
                "run_id": None, "metrics_id": None, "scientific_commit": None,
                "config_signature": None,
                "scientific_metrics": {key: None for key in SCIENTIFIC_METRICS},
                "lexical_mass_support": None,
                "rule_usage": None,
                "engineering_metrics": {key: None for key in ENGINEERING_METRICS},
                "provenance_evidence": declaration.provenance_evidence,
                "runtime_evidence": declaration.runtime_evidence,
                "termination_evidence": declaration.termination_evidence,
            }
            scientific_scalars[declaration.cell_id] = payload["scientific_metrics"]
        cell_payloads[declaration.cell_id] = payload

    pair_payloads: list[dict[str, Any]] = []
    for pair in protocol.pairs:
        left_decl, right_decl = declarations[pair.cell_a], declarations[pair.cell_b]
        available = (
            left_decl.status is CellStatus.AVAILABLE
            and right_decl.status is CellStatus.AVAILABLE
        )
        unavailable_reason = None if available else (
            f"pair requires two AVAILABLE cells; {pair.cell_a}={left_decl.status.value}, "
            f"{pair.cell_b}={right_decl.status.value}"
        )
        scalar_rows: dict[str, dict[str, Any]] = {}
        for metric in SCIENTIFIC_METRICS:
            left = scientific_scalars[pair.cell_a].get(metric)
            right = scientific_scalars[pair.cell_b].get(metric)
            if available and left is not None and right is not None:
                scalar_rows[metric] = {
                    "comparison_status": "AVAILABLE", "reason": None,
                    **scalar_comparison(left, right),
                }
            else:
                scalar_rows[metric] = _na_metric_row(
                    unavailable_reason or f"metric {metric} is unavailable"
                )

        if available:
            left_rules = cell_payloads[pair.cell_a]["rule_usage"]["normalized_distribution"]
            right_rules = cell_payloads[pair.cell_b]["rule_usage"]["normalized_distribution"]
            rule_distance = {
                "comparison_status": "AVAILABLE", "reason": None,
                "total_variation": total_variation(left_rules, right_rules),
                "jensen_shannon_divergence": jensen_shannon_nats(left_rules, right_rules),
                "jsd_log_base": "e", "jsd_units": "nats",
            }
            overlaps = []
            for k in protocol.top_k_values:
                left_set, right_set = set(top_forms[pair.cell_a][:k]), set(top_forms[pair.cell_b][:k])
                intersection, union = len(left_set & right_set), len(left_set | right_set)
                overlaps.append({
                    "k": k, "comparison_status": "AVAILABLE", "reason": None,
                    "overlap_count": intersection,
                    "jaccard": intersection / union if union else None,
                    "fraction_of_a": intersection / len(left_set) if left_set else None,
                    "fraction_of_b": intersection / len(right_set) if right_set else None,
                })
        else:
            rule_distance = {
                "comparison_status": "N/A", "reason": unavailable_reason,
                "total_variation": None, "jensen_shannon_divergence": None,
                "jsd_log_base": "e", "jsd_units": "nats",
            }
            overlaps = [{
                "k": k, "comparison_status": "N/A", "reason": unavailable_reason,
                "overlap_count": None, "jaccard": None,
                "fraction_of_a": None, "fraction_of_b": None,
            } for k in protocol.top_k_values]
        pair_payloads.append({
            "pair_id": pair.pair_id, "kind": pair.kind,
            "cell_a": pair.cell_a, "cell_b": pair.cell_b,
            "comparison_status": "AVAILABLE" if available else "N/A",
            "reason": unavailable_reason,
            "scalar_metrics": scalar_rows,
            "rule_distribution": rule_distance,
            "top_k_overlap": overlaps,
        })

    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "analysis_id": protocol.analysis_id,
        "validation": {"valid": True, "errors": []},
        "cell_counts": {
            "declared": len(protocol.declarations),
            "available": len(loaded_by_id),
            "n_a": len(protocol.declarations) - len(loaded_by_id),
        },
        "cells": [cell_payloads[cell.cell_id] for cell in protocol.declarations],
        "pairs": pair_payloads,
    }


def _display(value: object) -> object:
    return "N/A" if value is None else value


def _write_outputs(root: Path, result: Mapping[str, Any]) -> None:
    with (root / "cells.tsv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("cell_id", "script", "representation", "status", "reason", "metric_group", "metric", "value"))
        for cell in result["cells"]:
            for group in ("scientific_metrics", "engineering_metrics"):
                for metric, value in sorted(cell[group].items()):
                    writer.writerow((
                        cell["cell_id"], cell["script"], cell["representation"],
                        cell["status"], _display(cell["reason"]), group, metric,
                        _display(value),
                    ))
    with (root / "pairs.tsv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow((
            "pair_id", "kind", "cell_a", "cell_b", "comparison_status",
            "reason", "metric", "value_a", "value_b", "absolute_difference",
            "signed_difference_b_minus_a", "relative_difference", "ratio_b_over_a",
        ))
        for pair in result["pairs"]:
            for metric, row in sorted(pair["scalar_metrics"].items()):
                writer.writerow((
                    pair["pair_id"], pair["kind"], pair["cell_a"], pair["cell_b"],
                    row["comparison_status"], _display(row["reason"]), metric,
                    *(_display(row[key]) for key in (
                        "value_a", "value_b", "absolute_difference",
                        "signed_difference_b_minus_a",
                        "relative_difference_b_minus_a_over_abs_a", "ratio_b_over_a",
                    )),
                ))
    with (root / "rule_usage.tsv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("cell_id", "status", "rule_id", "expected_usage", "normalized_usage"))
        for cell in result["cells"]:
            if cell["rule_usage"] is None:
                writer.writerow((cell["cell_id"], "N/A", "N/A", "N/A", "N/A"))
                continue
            usage = cell["rule_usage"]
            for rule_id, value in usage["expected_usage"].items():
                writer.writerow((cell["cell_id"], "AVAILABLE", rule_id, value, usage["normalized_distribution"][rule_id]))
    with (root / "rule_distances.tsv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("pair_id", "comparison_status", "reason", "total_variation", "jensen_shannon_divergence", "jsd_units"))
        for pair in result["pairs"]:
            row = pair["rule_distribution"]
            writer.writerow((pair["pair_id"], row["comparison_status"], _display(row["reason"]), _display(row["total_variation"]), _display(row["jensen_shannon_divergence"]), row["jsd_units"]))
    with (root / "top_k_overlap.tsv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("pair_id", "k", "comparison_status", "reason", "overlap_count", "jaccard", "fraction_of_a", "fraction_of_b"))
        for pair in result["pairs"]:
            for row in pair["top_k_overlap"]:
                writer.writerow((pair["pair_id"], row["k"], row["comparison_status"], _display(row["reason"]), _display(row["overlap_count"]), _display(row["jaccard"]), _display(row["fraction_of_a"]), _display(row["fraction_of_b"])))

    counts = result["cell_counts"]
    lines = [
        f"# Representation analysis: {result['analysis_id']}", "",
        f"Validation: **valid**", "",
        f"Declared cells: {counts['declared']}; AVAILABLE: {counts['available']}; N/A: {counts['n_a']}", "",
        "## Cells", "",
    ]
    for cell in result["cells"]:
        suffix = "" if cell["reason"] is None else f" — {cell['reason']}"
        lines.append(f"- `{cell['cell_id']}`: {cell['status']}{suffix}")
    lines.extend(["", "## Comparisons", ""])
    for pair in result["pairs"]:
        suffix = "" if pair["reason"] is None else f" — {pair['reason']}"
        lines.append(f"- `{pair['pair_id']}`: {pair['comparison_status']}{suffix}")
    (root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def write_outputs(result: Mapping[str, Any], output_dir: Path) -> None:
    """Write all outputs atomically and refuse to overwrite an existing result."""

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
        _write_outputs(temporary, result)
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
