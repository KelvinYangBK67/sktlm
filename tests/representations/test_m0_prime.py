from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from sktlm.latent.frontend import (
    parse_devanagari_surface,
    parse_m0_prime_iast_surface,
)
from sktlm.latent.phonology import Phoneme
from sktlm.latent.training import TrainingConfig
from sktlm.representations.devanagari import transliterate_iast_to_devanagari
from sktlm.representations.m0_prime import (
    DERIVATION_ID,
    EXPECTED_M0_FREEZE_ID,
    M0PrimeConfig,
    generate,
    transliterate_devanagari_to_m0_prime_iast,
    validate,
)
from sktlm.representations.spacing import continuous_spacing


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_m0_prime_distinguishes_lexical_diphthongs_from_hiatus() -> None:
    source = continuous_spacing(
        transliterate_iast_to_devanagari("rama iti rama uta maitra pautra"),
        "devanagari",
    )
    output = transliterate_devanagari_to_m0_prime_iast(source)

    assert output == "ramaitiramautamētrapōtra"
    assert "ai" in output and "au" in output
    assert "ē" in output and "ō" in output
    assert (
        parse_m0_prime_iast_surface(output).phonemes
        == parse_devanagari_surface(source).phonemes
    )


def test_m0_prime_frontend_parses_reserved_sequences() -> None:
    parsed = parse_m0_prime_iast_surface("ē ō ai au dʰ dh")
    assert parsed.phonemes == (
        Phoneme.AI,
        Phoneme.AU,
        Phoneme.A,
        Phoneme.I,
        Phoneme.A,
        Phoneme.U,
        Phoneme.DH,
        Phoneme.D,
        Phoneme.H,
    )


def test_m0_prime_distinguishes_aspirates_from_plain_consonant_h_sequences() -> None:
    source = "धद्ह"
    output = transliterate_devanagari_to_m0_prime_iast(source)

    assert output == "dʰadha"
    assert "dʰ" in output and "dh" in output
    assert (
        parse_m0_prime_iast_surface(output).phonemes
        == parse_devanagari_surface(source).phonemes
    )


def test_m0_prime_rejects_unmapped_devanagari() -> None:
    with pytest.raises(ValueError, match="unsupported Devanagari"):
        transliterate_devanagari_to_m0_prime_iast("०")


def test_training_config_exposes_only_the_continuous_m0_prime_frontend() -> None:
    assert TrainingConfig(script="iast_m0_prime", condition="continuous").script == (
        "iast_m0_prime"
    )
    with pytest.raises(ValueError, match="only for continuous"):
        TrainingConfig(script="iast_m0_prime", condition="surface_word")


def test_fixture_generation_and_validation_are_identity_preserving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path
    source_root = repo_root / "data/representations/gretil/devanagari/continuous"
    relative = "sample/doc.txt"
    source_path = source_root / relative
    source_path.parent.mkdir(parents=True)
    source_text = continuous_spacing(
        transliterate_iast_to_devanagari("rama iti rama uta maitra pautra"),
        "devanagari",
    ) + "धद्ह"
    source_path.write_text(source_text, encoding="utf-8", newline="")

    representation_manifest = repo_root / "data/manifests/representations.csv"
    representation_fields = [
        "freeze_id",
        "relative_path",
        "canonical_hash",
        "script",
        "condition",
        "representation_path",
        "representation_hash",
        "byte_count",
        "char_count",
        "line_count",
        "boundary_path",
        "boundary_hash",
        "boundary_count",
        "boundary_semantics",
    ]
    _write_csv(
        representation_manifest,
        representation_fields,
        [
            {
                "freeze_id": EXPECTED_M0_FREEZE_ID,
                "relative_path": relative,
                "canonical_hash": "c" * 64,
                "script": "devanagari",
                "condition": "continuous",
                "representation_path": source_path.relative_to(repo_root).as_posix(),
                "representation_hash": _sha256(source_path),
                "byte_count": str(source_path.stat().st_size),
                "char_count": str(len(source_text)),
                "line_count": "1",
                "boundary_path": "",
                "boundary_hash": "",
                "boundary_count": "0",
                "boundary_semantics": "",
            }
        ],
    )
    canonical_manifest = repo_root / "data/manifests/canonical_corpus.csv"
    _write_csv(
        canonical_manifest,
        ["freeze_input_path", "document_id", "split", "canonical_hash"],
        [
            {
                "freeze_input_path": relative,
                "document_id": "doc_fixture",
                "split": "train",
                "canonical_hash": "c" * 64,
            }
        ],
    )
    config_path = repo_root / "fixture_config.json"
    config_path.write_text(json.dumps({"fixture": True}), encoding="utf-8")
    config = M0PrimeConfig(
        config_path=config_path,
        repo_root=repo_root,
        source_manifest=representation_manifest,
        canonical_manifest=canonical_manifest,
        source_root=source_root,
        output_root=repo_root / "data/derived/m0_prime/iast/continuous",
        artifact_dir=repo_root / "artifacts/m0_prime/fixture",
        expected_source_manifest_sha256=_sha256(representation_manifest),
        expected_canonical_manifest_sha256=_sha256(canonical_manifest),
        expected_documents=1,
        require_clean_git=False,
        require_observed_contrasts=True,
    )
    monkeypatch.setattr(
        "sktlm.representations.m0_prime._git_provenance",
        lambda unused: {
            "git_commit_sha": "f" * 40,
            "git_worktree_clean": True,
            "implementation": "fixture",
            "implementation_file": "fixture.py",
            "implementation_sha256": "e" * 64,
        },
    )

    generated = generate(config)
    validated = validate(config)

    assert generated == validated
    assert generated.documents == 1
    assert generated.lexical_ai > 0 and generated.lexical_au > 0
    assert generated.lexical_aspirates > 0
    assert generated.hiatus_ai > 0 and generated.hiatus_au > 0
    assert generated.plain_consonant_digraphs > 0
    validation = json.loads(
        (config.artifact_dir / "validation.json").read_text(encoding="utf-8")
    )
    assert validation["status"] == "VALID"
    assert all(validation["checks"].values())
    assert (config.artifact_dir / "SHA256SUMS").is_file()
    with pytest.raises(FileExistsError):
        generate(config)
