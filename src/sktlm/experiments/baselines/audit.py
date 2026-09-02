"""Post-run audit for the first full M0 baseline production cell."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Callable

from sktlm.experiments.baselines.aggregate import _read_json, _verify_completion
from sktlm.experiments.baselines.matrix import (
    RETIRED,
    BaselineMatrixSettings,
    RetiredConditionError,
)


def _check(
    checks: list[dict[str, Any]],
    name: str,
    function: Callable[[], bool],
) -> None:
    try:
        passed = bool(function())
        detail = "ok" if passed else "invariant returned false"
    except Exception as exc:  # Audit must report the failure category, not hide it.
        passed = False
        detail = f"{type(exc).__name__}: {exc}"
    checks.append({"name": name, "passed": passed, "detail": detail})


def audit_first_production_cell(
    settings: BaselineMatrixSettings,
    condition_id: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    """Classify incomplete engineering state separately from semantic invalidity."""
    record = settings.condition(condition_id)
    if record.status == RETIRED:
        raise RetiredConditionError(
            f"first-cell audit rejects retired condition {condition_id}: {record.reason}"
        )
    engineering: list[dict[str, Any]] = []
    scientific: list[dict[str, Any]] = []
    _check(engineering, "artifact_directory", artifact_dir.is_dir)
    _check(
        engineering,
        "completion_inventory_and_hashes",
        lambda: (_verify_completion(artifact_dir, condition_id) is None),
    )

    payloads: dict[str, dict[str, Any]] = {}

    def load_payload(name: str) -> bool:
        payloads[name] = _read_json(artifact_dir / f"{name}.json")
        return True

    for name in ("provenance", "metrics", "data_fingerprint", "tokenizer_fingerprint", "environment"):
        _check(
            engineering,
            f"read_{name}",
            lambda name=name: load_payload(name),
        )
    provenance = payloads.get("provenance", {})
    metrics = payloads.get("metrics", {})
    _check(
        engineering,
        "formal_production_scope",
        lambda: provenance.get("run_scope") == "formal_production"
        and metrics.get("run_scope") == "formal_production",
    )
    _check(
        engineering,
        "fresh_independent_training",
        lambda: provenance.get("training_initialization") == "fresh_per_cell"
        and bool(provenance.get("training_instance_id")),
    )
    _check(
        engineering,
        "code_data_environment_provenance",
        lambda: all(
            provenance.get(key)
            for key in (
                "code_commit",
                "corpus_freeze_id",
                "data_fingerprint_sha256",
                "tokenizer_fingerprint_sha256",
                "environment_fingerprint_sha256",
            )
        )
        and provenance.get("corpus_freeze_id") == settings.freeze_id,
    )
    _check(
        engineering,
        "runtime_and_peak_memory",
        lambda: float(metrics.get("runtime_seconds", 0)) > 0
        and int(metrics.get("peak_rss_bytes", 0)) > 0,
    )
    checkpoint = metrics.get("common_downstream_checkpoint")
    _check(
        engineering,
        "common_downstream_checkpoint",
        lambda: isinstance(checkpoint, str) and (artifact_dir / checkpoint).is_file(),
    )

    _check(
        scientific,
        "condition_identity_and_status",
        lambda: metrics.get("condition_id") == condition_id
        and metrics.get("condition_status") == "valid"
        and provenance.get("condition_status") == "valid",
    )
    _check(
        scientific,
        "unknown_behavior",
        lambda: isinstance(metrics.get("unk_count"), int)
        and metrics["unk_count"] >= 0
        and math.isfinite(float(metrics.get("unk_rate")))
        and 0.0 <= float(metrics["unk_rate"]) <= 1.0
        and bool(metrics.get("unknown_semantics")),
    )
    _check(
        scientific,
        "common_downstream_likelihood",
        lambda: metrics.get("common_downstream_status") == "complete"
        and metrics.get("common_downstream_finite") is True
        and all(
            math.isfinite(float(metrics.get(key))) and float(metrics[key]) >= 0
            for key in (
                "common_downstream_bits_per_character",
                "common_downstream_bits_per_byte",
                "bits_per_canonical_unit",
            )
        ),
    )
    expected_applicability = "applicable" if record.cell.script == "devanagari" else "not_applicable"
    _check(
        scientific,
        "script_diagnostic_scope",
        lambda: metrics.get("script_specific_diagnostic", {}).get("applicability")
        == expected_applicability,
    )
    if record.cell.method == "surface_lattice":
        _check(
            scientific,
            "surface_lattice_intrinsic_likelihood",
            lambda: math.isfinite(
                float(metrics.get("surface_lattice_intrinsic_bits_per_character"))
            ),
        )

    engineering_ok = all(check["passed"] for check in engineering)
    scientific_ok = all(check["passed"] for check in scientific)
    classification = (
        "pass"
        if engineering_ok and scientific_ok
        else "engineering_failure"
        if not engineering_ok
        else "scientific_semantics_failure"
    )
    return {
        "audit_schema_version": "m0-first-production-cell-audit-v1",
        "condition_id": condition_id,
        "classification": classification,
        "engineering_checks": engineering,
        "scientific_semantics_checks": scientific,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the first M0 production cell")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/baselines/m0_matrix.yaml"),
    )
    parser.add_argument("--condition", required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = BaselineMatrixSettings.from_yaml(args.config)
    audit = audit_first_production_cell(settings, args.condition, args.artifact_dir)
    rendered = json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if audit["classification"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
