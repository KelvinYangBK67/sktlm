#!/usr/bin/env python3
"""Create a bounded local post-hoc archive from six audited S1M1 cells."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sktlm.analysis.s1m1_archival import (
    SCHEMA_VERSION,
    GateValidationError,
    reduce_manifest,
    write_outputs,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed, local-only, bounded-memory post-hoc archival reduction "
            "of six completed unrestricted S1M1 collections."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.output_dir.resolve().exists():
            raise FileExistsError(
                f"refusing to overwrite output directory: {args.output_dir.resolve()}"
            )
        result = reduce_manifest(args.manifest)
        write_outputs(result, args.output_dir)
    except (GateValidationError, FileExistsError) as exc:
        payload = (
            exc.payload()
            if isinstance(exc, GateValidationError)
            else {
                "schema_version": SCHEMA_VERSION,
                "validation": {"valid": False, "errors": [str(exc)]},
            }
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(2) from exc
    print(
        json.dumps(
            {"valid": True, "output_dir": str(args.output_dir.resolve())},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
