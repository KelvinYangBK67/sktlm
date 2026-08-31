#!/usr/bin/env python3
"""Verify frozen M0 and representation provenance before a cloud benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_DOCUMENTS = 240
EXPECTED_CHARACTERS = 57_588_079
EXPECTED_BYTES = 69_864_279
EXPECTED_REPRESENTATIONS = 1_440
EXPECTED_RULES = 1_218


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    from sktlm.corpus.gretil.freeze import validate_freeze
    from sktlm.latent.training import EXPECTED_FREEZE_ID
    from sktlm.representations.generate import validate_representations
    from sktlm.sandhi.rules import load_external_sandhi_rules

    canonical_root = Path("data/canonical/gretil_iast")
    canonical_manifest = Path("data/manifests/canonical_corpus.csv")
    representation_root = Path("data/representations")
    representation_manifest = Path("data/manifests/representations.csv")
    rules_path = Path("data/rules/external_sandhi.tsv")

    frozen = validate_freeze(
        output_root=canonical_root,
        manifest_path=canonical_manifest,
    )
    representations = validate_representations(
        canonical_root=canonical_root,
        output_root=representation_root,
        manifest_path=representation_manifest,
    )
    rules = load_external_sandhi_rules(rules_path)

    expected = {
        "documents": (frozen.files_frozen, EXPECTED_DOCUMENTS),
        "characters": (frozen.char_count, EXPECTED_CHARACTERS),
        "bytes": (frozen.byte_count, EXPECTED_BYTES),
        "freeze_id": (frozen.corpus_sha256, EXPECTED_FREEZE_ID),
        "representation_freeze_id": (
            representations.freeze_id,
            EXPECTED_FREEZE_ID,
        ),
        "representations": (
            representations.representation_files,
            EXPECTED_REPRESENTATIONS,
        ),
        "rules": (len(rules), EXPECTED_RULES),
    }
    failures = [
        f"{name}: found {found!r}, expected {wanted!r}"
        for name, (found, wanted) in expected.items()
        if found != wanted
    ]
    payload = {
        "canonical_documents": frozen.files_frozen,
        "canonical_characters": frozen.char_count,
        "canonical_bytes": frozen.byte_count,
        "freeze_id": frozen.corpus_sha256,
        "representation_files": representations.representation_files,
        "representation_manifest_sha256": file_sha256(representation_manifest),
        "external_rule_count": len(rules),
        "external_rules_sha256": file_sha256(rules_path),
        "failures": failures,
        "valid": not failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
