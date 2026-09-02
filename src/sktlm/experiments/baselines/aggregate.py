"""Fail-closed completeness validation and aggregation for 18 production cells."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml

from sktlm.corpus.dataset import file_sha256
from sktlm.experiments.artifacts import payload_sha256
from sktlm.experiments.baselines.matrix import (
    REQUIRED_PROVENANCE,
    RETIRED,
    BaselineMatrixSettings,
    BaselineRunSpec,
    build_run_specs,
)


class AggregateValidationError(ValueError):
    """One or more artifact invariants failed; no partial aggregate is valid."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AggregateValidationError(f"cannot read valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AggregateValidationError(f"expected JSON object: {path}")
    return value


def _verify_embedded_fingerprint(
    payload: dict[str, Any], key: str, label: str
) -> str:
    actual = payload.get(key)
    if not isinstance(actual, str):
        raise AggregateValidationError(f"{label} lacks {key}")
    unhashed = dict(payload)
    unhashed.pop(key, None)
    expected = payload_sha256(unhashed)
    if actual != expected:
        raise AggregateValidationError(
            f"{label} fingerprint mismatch: expected {expected}, found {actual}"
        )
    return actual


def _verify_completion(artifact_dir: Path, condition_id: str) -> None:
    completion = _read_json(artifact_dir / "COMPLETED.json")
    if completion.get("schema_version") != "m0-baseline-completion-v1":
        raise AggregateValidationError(f"unsupported completion schema: {condition_id}")
    if completion.get("condition_id") != condition_id:
        raise AggregateValidationError(f"completion condition mismatch: {condition_id}")
    if completion.get("condition_status") != "valid":
        raise AggregateValidationError(f"completion status is not valid: {condition_id}")
    if completion.get("run_scope") != "formal_production":
        raise AggregateValidationError(f"non-production artifact: {condition_id}")
    declared = completion.get("files")
    if not isinstance(declared, dict) or not declared:
        raise AggregateValidationError(f"completion file inventory is empty: {condition_id}")
    actual_paths = {
        path.relative_to(artifact_dir).as_posix()
        for path in artifact_dir.rglob("*")
        if path.is_file() and path.name != "COMPLETED.json"
    }
    if actual_paths != set(declared):
        missing = sorted(set(declared) - actual_paths)
        extra = sorted(actual_paths - set(declared))
        raise AggregateValidationError(
            f"completion inventory mismatch for {condition_id}: missing={missing}, extra={extra}"
        )
    for relative_path, expected_hash in declared.items():
        path = artifact_dir / relative_path
        if file_sha256(path) != expected_hash:
            raise AggregateValidationError(
                f"completion hash mismatch for {condition_id}: {relative_path}"
            )


def _category_view(metrics: dict[str, Any]) -> dict[str, Any]:
    def select(prefixes: tuple[str, ...], exact: tuple[str, ...] = ()) -> dict[str, Any]:
        return {
            key: value
            for key, value in metrics.items()
            if key in exact or any(key.startswith(prefix) for prefix in prefixes)
        }

    return {
        "orthographic_diagnostics": select(
            ("dependent_", "virama_", "grapheme_", "invalid_grapheme_", "suspect_", "sandhi_", "script_specific_")
        ),
        "segmentation_statistics": select(
            (), ("token_count", "train_segments", "evaluation_segments", "evaluation_split")
        ),
        "unknown_behavior": select(("unk_", "unknown_")),
        "token_inventory_occupancy": select((), ("vocab_size", "occupied_token_types")),
        "method_specific_likelihood": select(("surface_lattice_intrinsic_", "surface_lattice_arc_", "surface_lattice_ambiguous_")),
        "common_downstream_lm_utility": select(
            ("common_downstream_",),
            ("bits_per_character", "bits_per_byte", "bits_per_canonical_unit"),
        ),
        "runtime_resources": select(("runtime_", "peak_rss_", "resource_measurement_")),
    }


def _comparison_structure(specs: tuple[BaselineRunSpec, ...]) -> dict[str, Any]:
    cells = [spec.cell for spec in specs]
    return {
        "script_pairs": [
            {
                "spacing": spacing,
                "scripts": ["iast", "devanagari"],
                "methods": ["bpe", "unigram", "unicode_codepoint"],
            }
            for spacing in ("surface_word", "legacy_joined")
        ],
        "spacing_comparisons": {
            "iast": ["surface_word", "legacy_joined"],
            "devanagari": ["surface_word", "legacy_joined", "continuous"],
        },
        "tokenizer_comparisons": [
            {
                "script": script,
                "spacing": spacing,
                "methods": sorted(
                    cell.method
                    for cell in cells
                    if cell.script == script and cell.spacing == spacing
                ),
            }
            for script in ("iast", "devanagari")
            for spacing in (
                ("surface_word", "legacy_joined")
                if script == "iast"
                else ("surface_word", "legacy_joined", "continuous")
            )
        ],
        "continuous_script_pair_generated": False,
    }


def aggregate_formal_results(
    settings: BaselineMatrixSettings,
    artifact_root: Path,
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Validate exactly 18 production bundles, then return a structured aggregate."""
    specs = build_run_specs(settings)
    retired_ids = {
        record.cell.condition_id
        for record in settings.condition_manifest
        if record.status == RETIRED
    }
    for condition_id in retired_ids:
        if (artifact_root / condition_id).exists():
            raise AggregateValidationError(
                f"formal artifact root contains retired condition: {condition_id}"
            )
    if not artifact_root.is_dir():
        raise AggregateValidationError(f"formal artifact root does not exist: {artifact_root}")
    expected_ids = {spec.cell.condition_id for spec in specs}
    actual_condition_dirs = {path.name for path in artifact_root.iterdir() if path.is_dir()}
    if actual_condition_dirs != expected_ids:
        missing = sorted(expected_ids - actual_condition_dirs)
        extra = sorted(actual_condition_dirs - expected_ids)
        raise AggregateValidationError(
            f"formal artifact condition set mismatch: missing={missing}, extra={extra}"
        )

    invariant_values: dict[str, set[Any]] = {
        "code_commit": set(),
        "canonical_manifest_sha256": set(),
        "representation_manifest_sha256": set(),
        "environment_fingerprint_sha256": set(),
        "seed": set(),
    }
    training_instances: set[str] = set()
    results: dict[str, Any] = {}
    for spec in specs:
        condition_id = spec.cell.condition_id
        condition_root = artifact_root / condition_id
        seed_dirs = [path for path in condition_root.iterdir() if path.is_dir()]
        expected_seed = f"seed_{settings.seed}"
        if len(seed_dirs) != 1 or seed_dirs[0].name != expected_seed:
            raise AggregateValidationError(
                f"duplicate or wrong-seed artifacts for {condition_id}: "
                f"{sorted(path.name for path in seed_dirs)}"
            )
        artifact_dir = seed_dirs[0]
        _verify_completion(artifact_dir, condition_id)
        provenance = _read_json(artifact_dir / "provenance.json")
        missing_provenance = set(REQUIRED_PROVENANCE) - set(provenance)
        if missing_provenance:
            raise AggregateValidationError(
                f"incomplete provenance for {condition_id}: {sorted(missing_provenance)}"
            )
        expected_identity = {
            "method": spec.cell.method,
            "script": spec.cell.script,
            "spacing": spec.cell.spacing,
            "condition_status": "valid",
            "retirement_reason": None,
            "condition_manifest_version": settings.condition_manifest_version,
            "run_scope": "formal_production",
            "corpus_freeze_id": settings.freeze_id,
            "seed": settings.seed,
            "training_initialization": "fresh_per_cell",
        }
        for key, expected in expected_identity.items():
            if provenance.get(key) != expected:
                raise AggregateValidationError(
                    f"provenance {key} mismatch for {condition_id}: "
                    f"expected {expected!r}, found {provenance.get(key)!r}"
                )
        config = yaml.safe_load((artifact_dir / "config.yaml").read_text(encoding="utf-8"))
        if config != provenance["config"] or payload_sha256(config) != provenance["config_sha256"]:
            raise AggregateValidationError(f"effective config mismatch for {condition_id}")
        if config.get("condition_id") != condition_id:
            raise AggregateValidationError(f"config condition mismatch for {condition_id}")
        limits = config.get("limits", {})
        downstream = config.get("common_downstream_lm", {})
        if limits != {"max_train_segments": None, "max_eval_segments": None}:
            raise AggregateValidationError(f"bounded artifact cannot be formal: {condition_id}")
        if (
            downstream.get("enabled") is not True
            or downstream.get("contract") != settings.downstream_lm.as_dict()
            or downstream.get("runtime_device_override") is not None
            or downstream.get("runtime_max_steps_override") is not None
        ):
            raise AggregateValidationError(f"downstream contract mismatch for {condition_id}")

        data_fingerprint = _read_json(artifact_dir / "data_fingerprint.json")
        tokenizer_fingerprint = _read_json(artifact_dir / "tokenizer_fingerprint.json")
        data_hash = _verify_embedded_fingerprint(
            data_fingerprint, "fingerprint_sha256", f"data fingerprint {condition_id}"
        )
        tokenizer_hash = _verify_embedded_fingerprint(
            tokenizer_fingerprint, "fingerprint_sha256", f"tokenizer fingerprint {condition_id}"
        )
        if data_hash != provenance["data_fingerprint_sha256"]:
            raise AggregateValidationError(f"data fingerprint provenance mismatch: {condition_id}")
        if tokenizer_hash != provenance["tokenizer_fingerprint_sha256"]:
            raise AggregateValidationError(
                f"tokenizer fingerprint provenance mismatch: {condition_id}"
            )
        if (
            data_fingerprint.get("corpus_freeze_id") != settings.freeze_id
            or data_fingerprint.get("script") != spec.cell.script
            or data_fingerprint.get("spacing") != spec.cell.spacing
        ):
            raise AggregateValidationError(f"data identity mismatch for {condition_id}")

        environment = _read_json(artifact_dir / "environment.json")
        environment_hash = _verify_embedded_fingerprint(
            environment,
            "environment_fingerprint_sha256",
            f"environment {condition_id}",
        )
        if environment_hash != provenance["environment_fingerprint_sha256"]:
            raise AggregateValidationError(f"environment provenance mismatch: {condition_id}")
        requirements = (artifact_dir / "requirements-freeze.txt").read_bytes()
        if hashlib.sha256(requirements).hexdigest() != environment.get(
            "requirements_freeze_sha256"
        ):
            raise AggregateValidationError(f"requirements freeze mismatch: {condition_id}")

        declared_location = Path(str(provenance["artifact_location"]))
        if not declared_location.is_absolute():
            declared_location = repo_root / declared_location
        if declared_location.resolve() != artifact_dir.resolve():
            raise AggregateValidationError(f"artifact location mismatch: {condition_id}")
        git_commit = (artifact_dir / "git_commit.txt").read_text(encoding="utf-8").strip()
        if git_commit != provenance["code_commit"] or git_commit.startswith("unavailable:"):
            raise AggregateValidationError(f"Git provenance mismatch: {condition_id}")

        metrics = _read_json(artifact_dir / "metrics.json")
        if (
            metrics.get("condition_id") != condition_id
            or metrics.get("condition_status") != "valid"
            or metrics.get("run_scope") != "formal_production"
            or metrics.get("common_downstream_status") != "complete"
            or metrics.get("common_downstream_finite") is not True
        ):
            raise AggregateValidationError(f"incomplete common metrics for {condition_id}")
        for key in (
            "common_downstream_bits_per_character",
            "common_downstream_bits_per_byte",
            "bits_per_canonical_unit",
            "unk_count",
            "unk_rate",
            "runtime_seconds",
            "peak_rss_bytes",
        ):
            value = metrics.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise AggregateValidationError(f"invalid metric {key} for {condition_id}")

        training_instance = str(provenance["training_instance_id"])
        if training_instance in training_instances:
            raise AggregateValidationError(
                f"cells do not have independent training instances: {condition_id}"
            )
        training_instances.add(training_instance)
        for key in invariant_values:
            invariant_values[key].add(provenance[key])
        results[condition_id] = {
            "identity": expected_identity,
            **_category_view(metrics),
        }

    mismatches = {
        key: sorted(str(value) for value in values)
        for key, values in invariant_values.items()
        if len(values) != 1
    }
    if mismatches:
        raise AggregateValidationError(f"cross-cell provenance mismatch: {mismatches}")
    return {
        "aggregate_schema_version": "m0-baseline-aggregate-v1",
        "condition_manifest_version": settings.condition_manifest_version,
        "historical_cell_count": 22,
        "valid_production_cell_count": 18,
        "retired_cell_count": 4,
        "complete_valid_cell_count": len(results),
        "freeze_id": settings.freeze_id,
        "shared_provenance": {
            key: next(iter(values)) for key, values in invariant_values.items()
        },
        "comparisons": _comparison_structure(specs),
        "results": results,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and aggregate 18 M0 baseline cells")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/baselines/m0_matrix.yaml"),
    )
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = BaselineMatrixSettings.from_yaml(args.config)
    artifact_root = args.artifact_root or settings.artifact_root
    aggregate = aggregate_formal_results(settings, artifact_root, repo_root=args.repo_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"validated and aggregated 18 production cells: {args.output}")


if __name__ == "__main__":
    main()
