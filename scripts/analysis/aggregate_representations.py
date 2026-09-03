#!/usr/bin/env python3
"""Validate and aggregate a declared representation-analysis manifest locally."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sktlm.analysis.representation_protocol import (
    OUTPUT_SCHEMA_VERSION, aggregate_manifest, write_outputs,
)
from sktlm.analysis.six_representation_gate import GateValidationError


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail-closed local representation analysis (v2).")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = aggregate_manifest(args.manifest)
        write_outputs(result, args.output_dir)
    except (GateValidationError, FileExistsError) as exc:
        errors = list(exc.errors) if isinstance(exc, GateValidationError) else [str(exc)]
        print(json.dumps({
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "validation": {"valid": False, "errors": errors},
        }, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(2) from exc
    print(json.dumps({"valid": True, "output_dir": str(args.output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
