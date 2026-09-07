#!/usr/bin/env python3
"""Baseline-specific input adapter used by the generic cloud bridge contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sktlm.corpus.dataset import file_sha256
from sktlm.experiments.baselines.frozen import load_full_m0_catalog
from sktlm.experiments.baselines.full_m0 import (
    M0_PRIME_DERIVATION_ID,
    FullM0MatrixSettings,
    load_matrix_settings,
)


REQUIRED_EVIDENCE = {
    "config.snapshot.json",
    "generation.json",
    "manifest.csv",
    "validation.json",
}


def verify_inputs(config_path: Path, *, repo_root: Path = Path(".")) -> dict:
    settings = load_matrix_settings(config_path)
    if not isinstance(settings, FullM0MatrixSettings):
        raise ValueError("full-M0 input verification requires full-m0-baselines-v1")
    catalog = load_full_m0_catalog(settings, repo_root=repo_root)
    manifest = settings.m0_prime.manifest
    if not manifest.is_absolute():
        manifest = repo_root / manifest
    evidence_root = manifest.parent
    validation = json.loads((evidence_root / "validation.json").read_text(encoding="utf-8"))
    generation = json.loads((evidence_root / "generation.json").read_text(encoding="utf-8"))
    for label, payload in (("generation", generation), ("validation", validation)):
        if payload.get("derivation_id") != M0_PRIME_DERIVATION_ID:
            raise ValueError(f"M0-prime {label} derivation identity mismatch")
        if payload.get("manifest_sha256") != settings.m0_prime.manifest_sha256:
            raise ValueError(f"M0-prime {label} manifest identity mismatch")
        if int(payload.get("documents", -1)) != catalog.document_count:
            raise ValueError(f"M0-prime {label} document count mismatch")
    if validation.get("status") != "VALID":
        raise ValueError("M0-prime validation evidence is not VALID")

    checksum_path = evidence_root / "SHA256SUMS"
    rows = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not name or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("M0-prime SHA256SUMS contains an unsafe or malformed entry")
        rows[name] = digest
    if set(rows) != REQUIRED_EVIDENCE:
        raise ValueError("M0-prime SHA256SUMS inventory mismatch")
    for name, expected in rows.items():
        if file_sha256(evidence_root / name) != expected:
            raise ValueError(f"M0-prime compact evidence hash mismatch: {name}")
    return {
        "valid": True,
        "freeze_id": settings.freeze_id,
        "documents": catalog.document_count,
        "representation_files": catalog.representation_file_count,
        "m0_prime_manifest_sha256": settings.m0_prime.manifest_sha256,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    print(json.dumps(verify_inputs(args.config, repo_root=args.repo_root), sort_keys=True))


if __name__ == "__main__":
    main()
