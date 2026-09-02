"""Fail-closed production queue generation for the 18 valid M0 baseline cells."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from sktlm.experiments.baselines.matrix import (
    RETIRED,
    BaselineMatrixSettings,
    RetiredConditionError,
    build_run_specs,
)


def require_valid_condition(settings: BaselineMatrixSettings, condition_id: str) -> None:
    record = settings.condition(condition_id)
    if record.status == RETIRED:
        raise RetiredConditionError(
            f"production scheduling rejects retired condition {condition_id}: "
            f"{record.reason}; decision_id={record.decision_id}"
        )


def build_production_queue(
    settings: BaselineMatrixSettings,
    *,
    config_path: Path,
    condition_id: str | None = None,
) -> dict[str, Any]:
    """Return commands only; this module never launches an experiment."""
    if condition_id is not None:
        require_valid_condition(settings, condition_id)
    specs = [
        spec for spec in build_run_specs(settings)
        if condition_id is None or spec.cell.condition_id == condition_id
    ]
    jobs = []
    for index, spec in enumerate(specs, 1):
        argv = [
            "python",
            "-m",
            "sktlm.experiments.baselines.runner",
            "--config",
            config_path.as_posix(),
            "--condition",
            spec.cell.condition_id,
        ]
        jobs.append(
            {
                "queue_index": index,
                "condition_id": spec.cell.condition_id,
                "condition_status": "valid",
                "artifact_location": spec.artifact_dir.as_posix(),
                "command_argv": argv,
                "command": shlex.join(argv),
            }
        )
    return {
        "queue_schema_version": "m0-baseline-production-queue-v1",
        "condition_manifest_version": settings.condition_manifest_version,
        "historical_cell_count": len(settings.condition_manifest),
        "valid_production_cell_count": 18,
        "scheduled_job_count": len(jobs),
        "launches_jobs": False,
        "jobs": jobs,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a fail-closed M0 baseline production queue without launching it"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/baselines/m0_matrix.yaml"),
    )
    parser.add_argument("--condition")
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = BaselineMatrixSettings.from_yaml(args.config)
    queue = build_production_queue(
        settings,
        config_path=args.config,
        condition_id=args.condition,
    )
    rendered = json.dumps(queue, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
