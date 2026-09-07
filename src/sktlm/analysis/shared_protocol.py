"""Experiment-neutral evidence, comparison, and publication protocol."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import yaml


COMPARISON_SCHEMA = "sktlm-shared-analysis-comparisons/v1"
RESULT_SCHEMA = "sktlm-shared-analysis-result/v1"


class SharedAnalysisError(ValueError):
    pass


class CellStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NA_SCIENTIFICALLY_EXCLUDED = "NA_SCIENTIFICALLY_EXCLUDED"
    NA_EXECUTION_INCOMPLETE = "NA_EXECUTION_INCOMPLETE"
    NA_NOT_APPLICABLE = "NA_NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class CellEvidence:
    cell_id: str
    status: CellStatus
    dimensions: Mapping[str, str]
    scientific_metrics: Mapping[str, Any]
    engineering_metrics: Mapping[str, Any]
    provenance: Mapping[str, Any]
    artifacts: Mapping[str, Any]
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.cell_id:
            raise SharedAnalysisError("cell evidence requires a cell_id")
        if self.status is CellStatus.AVAILABLE and self.reason is not None:
            raise SharedAnalysisError(f"AVAILABLE cell cannot carry an N/A reason: {self.cell_id}")
        if self.status is not CellStatus.AVAILABLE and not self.reason:
            raise SharedAnalysisError(f"N/A cell requires a reason: {self.cell_id}")
        required = {"method", "script", "representation", "substrate"}
        if required - set(self.dimensions):
            raise SharedAnalysisError(
                f"cell {self.cell_id} lacks dimensions: {sorted(required - set(self.dimensions))}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "status": self.status.value,
            "reason": self.reason,
            "dimensions": dict(self.dimensions),
            "scientific_metrics": dict(self.scientific_metrics),
            "engineering_metrics": dict(self.engineering_metrics),
            "provenance": dict(self.provenance),
            "artifacts": dict(self.artifacts),
        }


@dataclass(frozen=True, slots=True)
class ComparisonDeclaration:
    comparison_id: str
    kind: str
    cell_a: str
    cell_b: str
    strict_control: bool
    note: str | None = None


def scalar_comparison(left: float, right: float) -> dict[str, Any]:
    absolute = abs(right - left)
    signed = right - left
    denominator_zero = left == 0
    return {
        "value_a": left,
        "value_b": right,
        "absolute_difference": absolute,
        "signed_difference_b_minus_a": signed,
        "relative_difference_b_minus_a_over_abs_a": (
            None if denominator_zero else signed / abs(left)
        ),
        "ratio_b_over_a": None if denominator_zero else right / left,
        "denominator_zero": denominator_zero,
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SharedAnalysisError("comparison manifest must be a mapping")
    if value.get("schema_version") != COMPARISON_SCHEMA:
        raise SharedAnalysisError(
            f"unsupported comparison manifest schema: {value.get('schema_version')}"
        )
    allowed = {"schema_version", "comparison_manifest_id", "adapter_id", "comparison_families"}
    unknown = set(value) - allowed
    if unknown:
        raise SharedAnalysisError(f"unknown comparison manifest fields: {sorted(unknown)}")
    return value


def _selector_index(cells: tuple[CellEvidence, ...]) -> dict[tuple[tuple[str, str], ...], str]:
    index: dict[tuple[tuple[str, str], ...], str] = {}
    for cell in cells:
        key = tuple(sorted(cell.dimensions.items()))
        if key in index:
            raise SharedAnalysisError(f"duplicate dimension identity: {cell.cell_id}")
        index[key] = cell.cell_id
    return index


def _resolve_selector(
    cells: tuple[CellEvidence, ...], selector: Mapping[str, Any]
) -> str:
    matches = [
        cell.cell_id
        for cell in cells
        if all(cell.dimensions.get(str(key)) == str(value) for key, value in selector.items())
    ]
    if len(matches) != 1:
        raise SharedAnalysisError(
            f"comparison selector must match exactly one cell: selector={dict(selector)}, matches={matches}"
        )
    return matches[0]


def expand_comparisons(
    cells: Iterable[CellEvidence], manifest: Mapping[str, Any]
) -> tuple[ComparisonDeclaration, ...]:
    actual = tuple(cells)
    ids = [cell.cell_id for cell in actual]
    if len(ids) != len(set(ids)):
        raise SharedAnalysisError("shared analysis contains duplicate cell IDs")
    _selector_index(actual)
    families = manifest.get("comparison_families")
    if not isinstance(families, list) or not families:
        raise SharedAnalysisError("comparison manifest requires comparison_families")

    declarations: list[ComparisonDeclaration] = []
    for family in families:
        if not isinstance(family, Mapping):
            raise SharedAnalysisError("comparison family must be a mapping")
        allowed = {
            "family_id", "kind", "mode", "dimension", "values", "value_pairs",
            "contexts", "strict_control", "note",
        }
        unknown = set(family) - allowed
        if unknown:
            raise SharedAnalysisError(f"unknown comparison family fields: {sorted(unknown)}")
        family_id = str(family["family_id"])
        kind = str(family["kind"])
        mode = str(family["mode"])
        dimension = str(family["dimension"])
        contexts = family.get("contexts")
        if not isinstance(contexts, list) or not contexts:
            raise SharedAnalysisError(f"comparison family {family_id} requires contexts")
        default_strict = bool(family.get("strict_control", True))
        note = str(family["note"]) if family.get("note") is not None else None
        for context in contexts:
            if not isinstance(context, Mapping) or "context_id" not in context:
                raise SharedAnalysisError(f"invalid context in comparison family {family_id}")
            context_id = str(context["context_id"])
            strict = bool(context.get("strict_control", default_strict))
            context_note = str(context.get("note", note)) if context.get("note", note) else None
            if mode == "same_dimension":
                values = family.get("values")
                if not isinstance(values, list) or not values:
                    raise SharedAnalysisError(f"family {family_id} requires values")
                left = context.get("left")
                right = context.get("right")
                if not isinstance(left, Mapping) or not isinstance(right, Mapping):
                    raise SharedAnalysisError(f"family {family_id} requires left/right contexts")
                pairs = [(str(value), str(value)) for value in values]
            elif mode == "dimension_pairs":
                raw_pairs = family.get("value_pairs")
                selector = context.get("selector")
                if not isinstance(raw_pairs, list) or not raw_pairs or not isinstance(selector, Mapping):
                    raise SharedAnalysisError(f"family {family_id} requires selector/value_pairs")
                pairs = []
                left = right = selector
                for pair in raw_pairs:
                    if not isinstance(pair, list) or len(pair) != 2:
                        raise SharedAnalysisError(f"family {family_id} has invalid value pair")
                    pairs.append((str(pair[0]), str(pair[1])))
            else:
                raise SharedAnalysisError(f"unknown comparison family mode: {mode}")

            for value_a, value_b in pairs:
                selector_a = {**left, dimension: value_a}
                selector_b = {**right, dimension: value_b}
                comparison_id = f"{family_id}__{context_id}__{value_a}_vs_{value_b}"
                declarations.append(
                    ComparisonDeclaration(
                        comparison_id=comparison_id,
                        kind=kind,
                        cell_a=_resolve_selector(actual, selector_a),
                        cell_b=_resolve_selector(actual, selector_b),
                        strict_control=strict,
                        note=context_note,
                    )
                )
    comparison_ids = [row.comparison_id for row in declarations]
    if len(comparison_ids) != len(set(comparison_ids)):
        raise SharedAnalysisError("comparison manifest expands to duplicate comparison IDs")
    return tuple(declarations)


def analyze_evidence(
    *,
    adapter_id: str,
    cells: Iterable[CellEvidence],
    comparison_manifest: Path,
    adapter_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    actual = tuple(cells)
    manifest = _load_manifest(comparison_manifest)
    if manifest.get("adapter_id") != adapter_id:
        raise SharedAnalysisError(
            f"comparison manifest is not declared for adapter {adapter_id}"
        )
    declarations = expand_comparisons(actual, manifest)
    by_id = {cell.cell_id: cell for cell in actual}
    comparisons: list[dict[str, Any]] = []
    for declaration in declarations:
        left = by_id[declaration.cell_a]
        right = by_id[declaration.cell_b]
        available = left.status is CellStatus.AVAILABLE and right.status is CellStatus.AVAILABLE
        metric_rows: dict[str, Any] = {}
        common_metrics = sorted(set(left.scientific_metrics) & set(right.scientific_metrics))
        for metric in common_metrics:
            value_a = left.scientific_metrics[metric]
            value_b = right.scientific_metrics[metric]
            numeric = (
                isinstance(value_a, (int, float)) and not isinstance(value_a, bool)
                and isinstance(value_b, (int, float)) and not isinstance(value_b, bool)
                and math.isfinite(float(value_a)) and math.isfinite(float(value_b))
            )
            if available and numeric:
                metric_rows[metric] = {
                    "status": "AVAILABLE",
                    **scalar_comparison(float(value_a), float(value_b)),
                }
            else:
                metric_rows[metric] = {
                    "status": "N/A",
                    "reason": "both AVAILABLE cells require a shared finite numeric metric",
                    "value_a": value_a,
                    "value_b": value_b,
                    "absolute_difference": None,
                    "signed_difference_b_minus_a": None,
                    "relative_difference_b_minus_a_over_abs_a": None,
                    "ratio_b_over_a": None,
                    "denominator_zero": None,
                }
        comparisons.append(
            {
                "comparison_id": declaration.comparison_id,
                "kind": declaration.kind,
                "cell_a": declaration.cell_a,
                "cell_b": declaration.cell_b,
                "status": "AVAILABLE" if available else "N/A",
                "strict_control": declaration.strict_control,
                "note": declaration.note,
                "scientific_metrics": metric_rows,
            }
        )
    return {
        "schema_version": RESULT_SCHEMA,
        "adapter_id": adapter_id,
        "comparison_manifest_id": manifest["comparison_manifest_id"],
        "cell_counts": {
            "declared": len(actual),
            "available": sum(cell.status is CellStatus.AVAILABLE for cell in actual),
            "n_a": sum(cell.status is not CellStatus.AVAILABLE for cell in actual),
        },
        "cells": [cell.as_dict() for cell in actual],
        "comparisons": comparisons,
        "adapter_provenance": dict(adapter_provenance),
    }


Adapter = Callable[..., Mapping[str, Any]]


def run_adapter(adapter_id: str, adapters: Mapping[str, Adapter], **kwargs: Any) -> Mapping[str, Any]:
    try:
        adapter = adapters[adapter_id]
    except KeyError as exc:
        raise SharedAnalysisError(f"unknown shared-analysis adapter: {adapter_id}") from exc
    return adapter(**kwargs)


def publish_analysis(result: Mapping[str, Any], output_dir: Path) -> None:
    """Atomically publish JSON/TSV/Markdown and refuse any overwrite."""
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite shared-analysis output: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        (temporary / "analysis.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with (temporary / "cells.tsv").open("x", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(("cell_id", "status", "metric_group", "metric", "value"))
            for cell in result["cells"]:
                for group in ("scientific_metrics", "engineering_metrics"):
                    for metric, value in sorted(cell[group].items()):
                        writer.writerow((cell["cell_id"], cell["status"], group, metric, json.dumps(value, ensure_ascii=False)))
        with (temporary / "comparisons.tsv").open("x", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(("comparison_id", "kind", "strict_control", "cell_a", "cell_b", "metric", "status", "value_a", "value_b", "difference", "ratio"))
            for comparison in result["comparisons"]:
                for metric, row in sorted(comparison["scientific_metrics"].items()):
                    writer.writerow((comparison["comparison_id"], comparison["kind"], comparison["strict_control"], comparison["cell_a"], comparison["cell_b"], metric, row["status"], row.get("value_a"), row.get("value_b"), row.get("signed_difference_b_minus_a"), row.get("ratio_b_over_a")))
        lines = [
            f"# Shared analysis: {result['comparison_manifest_id']}",
            "",
            f"Adapter: `{result['adapter_id']}`",
            "",
            f"Cells: {result['cell_counts']['declared']} declared, {result['cell_counts']['available']} AVAILABLE, {result['cell_counts']['n_a']} N/A.",
            "",
            f"Declared comparisons: {len(result['comparisons'])}.",
        ]
        (temporary / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
