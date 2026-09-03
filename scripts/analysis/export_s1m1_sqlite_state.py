#!/usr/bin/env python3
"""Export S1M1 training-final scorer and association state from SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from sktlm.analysis.s1m1_compact import (
    SQLITE_STATE_SCHEMA_VERSION,
    export_sqlite_state,
)
from sktlm.analysis.six_representation_gate import GateValidationError


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only S1M1 SQLite scorer/association export."
    )
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument(
        "--wal",
        type=Path,
        help="Source WAL path; defaults deterministically to <database>-wal.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        export_sqlite_state(
            cell_id=args.cell_id,
            database_path=args.database,
            wal_path=args.wal,
            output_dir=args.output_dir,
        )
    except (GateValidationError, FileExistsError, OSError, sqlite3.Error) as exc:
        errors = list(exc.errors) if isinstance(exc, GateValidationError) else [str(exc)]
        print(
            json.dumps(
                {
                    "schema_version": SQLITE_STATE_SCHEMA_VERSION,
                    "validation": {"valid": False, "errors": errors},
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(2) from exc
    print(json.dumps({"valid": True, "output_dir": str(args.output_dir.resolve())}, sort_keys=True))


if __name__ == "__main__":
    main()
