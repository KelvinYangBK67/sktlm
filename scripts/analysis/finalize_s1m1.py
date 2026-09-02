#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path
from sktlm.analysis.s1m1_final import OUTPUT_SCHEMA_VERSION, FinalValidationError, reduce_final_manifest, write_final_outputs

def main() -> None:
    parser = argparse.ArgumentParser(description="Fail-closed local final reduction of the five valid audited S1M1 cells plus the frozen IAST-continuous invalidation record.")
    parser.add_argument("--manifest", required=True, type=Path); parser.add_argument("--output-dir", required=True, type=Path); args = parser.parse_args()
    try:
        if args.output_dir.resolve().exists(): raise FileExistsError(f"refusing to overwrite output directory: {args.output_dir.resolve()}")
        result = reduce_final_manifest(args.manifest); write_final_outputs(result, args.output_dir)
    except (FinalValidationError, FileExistsError, OSError) as exc:
        payload = exc.payload() if isinstance(exc, FinalValidationError) else {"schema_version": OUTPUT_SCHEMA_VERSION, "validation": {"valid": False, "errors": [str(exc)]}}
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)); raise SystemExit(2) from exc
    print(json.dumps({"valid": True, "schema_version": OUTPUT_SCHEMA_VERSION, "output_dir": str(args.output_dir.resolve())}, sort_keys=True))

if __name__ == "__main__": main()
