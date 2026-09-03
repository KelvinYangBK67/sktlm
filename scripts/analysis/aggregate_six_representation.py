#!/usr/bin/env python3
"""Validate and aggregate six already-collected unrestricted M0 runs locally."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sktlm.analysis.six_representation_gate import (
    GateValidationError,
    aggregate_manifest as aggregate_v1,
    write_outputs as write_v1,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed local aggregation of six audited unrestricted M0 "
            "representation cells; performs no remote operation."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest_schema = None
    try:
        manifest_schema = json.loads(
            args.manifest.read_text(encoding="utf-8")
        ).get("schema_version")
        if manifest_schema == "sktlm-representation-analysis-input/v2":
            from sktlm.analysis.representation_protocol import (
                aggregate_manifest as aggregate_v2,
                write_outputs as write_v2,
            )
            aggregate, write = aggregate_v2, write_v2
        else:
            aggregate, write = aggregate_v1, write_v1
        result = aggregate(args.manifest)
        write(result, args.output_dir)
    except (GateValidationError, FileExistsError, OSError, json.JSONDecodeError) as exc:
        errors = list(exc.errors) if isinstance(exc, GateValidationError) else [str(exc)]
        payload = {
            "schema_version": (
                "sktlm-representation-analysis-aggregation/v2"
                if manifest_schema == "sktlm-representation-analysis-input/v2"
                else "sktlm-six-representation-gate-aggregation/v1"
            ),
            "validation": {"valid": False, "errors": errors},
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(2) from exc
    print(json.dumps({"valid": True, "output_dir": str(args.output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
