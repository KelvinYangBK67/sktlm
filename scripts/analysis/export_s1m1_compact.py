#!/usr/bin/env python3
"""Compact archival export for one completed S1M1 cell."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from sktlm.analysis.s1m1_compact import SCHEMA_VERSION, export_compact_cell
from sktlm.analysis.six_representation_gate import GateValidationError


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only streaming compact export; real cells may run for hours.")
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--representation", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--metrics-dir", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        export_compact_cell(
            cell_id=args.cell_id, script=args.script,
            representation=args.representation, run_dir=args.run_dir,
            metrics_dir=args.metrics_dir, database_path=args.database,
            output_dir=args.output_dir,
        )
    except (GateValidationError, FileExistsError, OSError, sqlite3.Error) as exc:
        errors = list(exc.errors) if isinstance(exc, GateValidationError) else [str(exc)]
        print(json.dumps({"schema_version": SCHEMA_VERSION, "validation": {"valid": False, "errors": errors}}, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(2) from exc
    print(json.dumps({"valid": True, "output_dir": str(args.output_dir.resolve())}, sort_keys=True))


if __name__ == "__main__":
    main()
