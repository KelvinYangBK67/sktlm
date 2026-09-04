#!/usr/bin/env python3
"""Run fail-closed streaming association-specialization analysis."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from sktlm.analysis.association_specialization import (
    OUTPUT_SCHEMA_VERSION,
    analyze_manifest,
)
from sktlm.analysis.six_representation_gate import GateValidationError


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Streaming scorer/context/surface specialization analysis."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        analyze_manifest(args.manifest, args.output_dir)
    except (
        GateValidationError,
        FileExistsError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        errors = (
            list(exc.errors)
            if isinstance(exc, GateValidationError)
            else [str(exc)]
        )
        print(
            json.dumps(
                {
                    "schema_version": OUTPUT_SCHEMA_VERSION,
                    "validation": {"valid": False, "errors": errors},
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(2) from exc
    print(
        json.dumps(
            {
                "valid": True,
                "schema_version": OUTPUT_SCHEMA_VERSION,
                "output_dir": str(args.output_dir.resolve()),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
