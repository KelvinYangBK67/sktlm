"""Thin adapter from fail-closed full-M0 baseline bundles to shared evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from sktlm.analysis.shared_protocol import (
    CellEvidence,
    CellStatus,
    analyze_evidence,
    publish_analysis,
)
from sktlm.experiments.baselines.aggregate import aggregate_formal_results
from sktlm.experiments.baselines.full_m0 import (
    FullM0MatrixSettings,
    load_matrix_settings,
)


ADAPTER_ID = "full-m0-baseline-adapter-v1"


def _flatten(groups: Mapping[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name in names:
        values = groups.get(name, {})
        if isinstance(values, Mapping):
            output.update(values)
    return output


def adapt_full_m0_baselines(
    *,
    settings: FullM0MatrixSettings,
    artifact_root: Path,
    comparison_manifest: Path,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Run native validation first, then expose family-neutral cell evidence."""
    aggregate = aggregate_formal_results(settings, artifact_root, repo_root=repo_root)
    cells: list[CellEvidence] = []
    for condition_id, result in aggregate["results"].items():
        identity = result["identity"]
        provenance = result["provenance"]
        scientific = _flatten(
            result,
            (
                "common_downstream_lm_utility",
                "segmentation_statistics",
                "unknown_behavior",
                "token_inventory_occupancy",
                "orthographic_diagnostics",
                "method_specific_likelihood",
            ),
        )
        engineering = _flatten(result, ("runtime_resources",))
        engineering.update(
            {
                "environment_fingerprint_sha256": provenance["environment_fingerprint_sha256"],
                "software_versions": provenance["software_versions"],
                "code_commit": provenance["code_commit"],
                "data_fingerprint_sha256": provenance["data_fingerprint_sha256"],
                "tokenizer_fingerprint_sha256": provenance["tokenizer_fingerprint_sha256"],
                "training_instance_id": provenance["training_instance_id"],
            }
        )
        cells.append(
            CellEvidence(
                cell_id=condition_id,
                status=CellStatus.AVAILABLE,
                dimensions={
                    "method": identity["method"],
                    "script": identity["script"],
                    "representation": identity["spacing"],
                    "substrate": identity["substrate"],
                },
                scientific_metrics=scientific,
                engineering_metrics=engineering,
                provenance=provenance,
                artifacts={
                    "bundle": provenance["artifact_location"],
                    "files": result["artifacts"],
                },
            )
        )
    return analyze_evidence(
        adapter_id=ADAPTER_ID,
        cells=cells,
        comparison_manifest=comparison_manifest,
        adapter_provenance={
            "native_aggregate_schema": aggregate["aggregate_schema_version"],
            "condition_manifest_version": aggregate["condition_manifest_version"],
            "full_m0_definition_version": aggregate["full_m0_definition_version"],
            "native_validation": "passed",
        },
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Publish shared analysis for full-M0 baselines")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/baselines/full_m0_matrix.yaml"),
    )
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument(
        "--comparisons",
        type=Path,
        default=Path("configs/analysis/full_m0_baseline_comparisons.yaml"),
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    settings = load_matrix_settings(args.config)
    if not isinstance(settings, FullM0MatrixSettings):
        raise ValueError("baseline shared adapter requires full-m0-baselines-v1")
    result = adapt_full_m0_baselines(
        settings=settings,
        artifact_root=args.artifact_root or settings.artifact_root,
        comparison_manifest=args.comparisons,
        repo_root=args.repo_root,
    )
    publish_analysis(result, args.output_dir)
    print(f"shared baseline analysis: {args.output_dir}")


if __name__ == "__main__":
    main()
