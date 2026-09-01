#!/usr/bin/env python3
"""Validate and aggregate six already-collected unrestricted M0 runs locally."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sktlm.analysis.six_representation_gate import (
    GateValidationError,
    aggregate_manifest,
    write_outputs,
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
    try:
        result = aggregate_manifest(args.manifest)
        write_outputs(result, args.output_dir)
    except (GateValidationError, FileExistsError) as exc:
        payload = (
            exc.payload()
            if isinstance(exc, GateValidationError)
            else {
                "schema_version": "sktlm-six-representation-gate-aggregation/v1",
                "validation": {"valid": False, "errors": [str(exc)]},
            }
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(2) from exc
    print(json.dumps({"valid": True, "output_dir": str(args.output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()