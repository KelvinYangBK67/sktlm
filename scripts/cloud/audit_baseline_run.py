#!/usr/bin/env python3
"""Produce the generic bridge audit envelope for one full-M0 baseline bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sktlm.corpus.dataset import file_sha256
from sktlm.experiments.baselines.audit import audit_first_production_cell
from sktlm.experiments.baselines.full_m0 import FullM0MatrixSettings, load_matrix_settings


def audit_bundle(config: Path, condition_id: str, artifact_dir: Path) -> dict:
    settings = load_matrix_settings(config)
    if not isinstance(settings, FullM0MatrixSettings):
        raise ValueError("bridge baseline audit requires full-m0-baselines-v1")
    audit = audit_first_production_cell(settings, condition_id, artifact_dir)
    artifacts = {
        path.relative_to(artifact_dir).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in sorted(artifact_dir.rglob("*"))
        if path.is_file()
    }
    return {
        "valid": audit["classification"] == "pass",
        "experiment_contract": "full-m0-baselines-v1",
        "condition_id": condition_id,
        "classification": audit["classification"],
        "artifacts": artifacts,
        "native_audit": audit,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = audit_bundle(args.config, args.condition, args.artifact_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if payload["valid"] is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
