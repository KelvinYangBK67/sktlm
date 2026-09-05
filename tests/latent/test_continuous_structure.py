from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from sktlm.latent.continuous_structure import (
    ContinuousSelectionConfig,
    scan_continuous_structure,
)
from sktlm.latent.training import EXPECTED_FREEZE_ID
from sktlm.representations.devanagari import transliterate_iast_to_devanagari
from sktlm.representations.m0_prime import (
    transliterate_devanagari_to_m0_prime_iast,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(
    tmp_path: Path,
    *,
    name: str,
    script: str,
    texts: tuple[str, ...],
) -> Path:
    root = tmp_path / name
    root.mkdir()
    path = tmp_path / f"{name}.csv"
    rows = []
    for index, text in enumerate(texts):
        source = root / f"doc-{index}.txt"
        source.write_text(text, encoding="utf-8", newline="")
        rows.append(
            {
                "freeze_id": EXPECTED_FREEZE_ID,
                "relative_path": f"doc-{index}.txt",
                "script": script,
                "condition": "continuous",
                "representation_path": source.as_posix(),
                "representation_hash": _sha256(source),
                "byte_count": source.stat().st_size,
                "char_count": len(text),
                "line_count": len(text.splitlines()),
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    return path


def _config(tmp_path: Path, *, mismatch: bool = False) -> tuple[Path, Path]:
    iast = (
        "rama|tat tvam asi\n",
        "devo'pi||ramani\n",
        "a|aa|aaa|aaaa\n",
        "tattvamasitattvamasi\n",
    )
    devanagari = tuple(transliterate_iast_to_devanagari(text) for text in iast)
    prime = tuple(transliterate_devanagari_to_m0_prime_iast(text) for text in devanagari)
    if mismatch:
        prime = (*prime[:-1], prime[-1] + "a")
    deva_manifest = _manifest(
        tmp_path,
        name="deva",
        script="devanagari",
        texts=devanagari,
    )
    prime_manifest = _manifest(
        tmp_path,
        name="prime",
        script="iast_m0_prime",
        texts=prime,
    )
    config_path = tmp_path / "selection.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "sktlm-s1m2-continuous-selection/v1",
                "require_clean_git": False,
                "inputs": [
                    {
                        "cell_id": "prime",
                        "manifest": prime_manifest.as_posix(),
                        "manifest_sha256": _sha256(prime_manifest),
                        "script": "iast_m0_prime",
                        "condition": "continuous",
                    },
                    {
                        "cell_id": "deva",
                        "manifest": deva_manifest.as_posix(),
                        "manifest_sha256": _sha256(deva_manifest),
                        "script": "devanagari",
                        "condition": "continuous",
                    },
                ],
                "selection": {
                    "basis_cell": "deva",
                    "representative_percentiles": [25, 50, 75],
                    "stress_documents": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    return config_path, deva_manifest


def test_static_selection_is_model_free_deterministic_and_cross_frontend(
    tmp_path: Path,
) -> None:
    config_path, _ = _config(tmp_path)
    config = ContinuousSelectionConfig.load(config_path, repo_root=Path("."))

    first = scan_continuous_structure(
        config,
        repo_root=Path("."),
        config_path=config_path,
    )
    second = scan_continuous_structure(
        config,
        repo_root=Path("."),
        config_path=config_path,
    )

    assert first == second
    assert first["cross_frontend_structure_identity"] == "PASS"
    assert len(first["selection"]["representative"]) == 3
    assert first["selection"]["stress"] == ["doc-3.txt"]
    assert (
        first["cells"]["prime"]["aggregate"]["phonemes"]
        == first["cells"]["deva"]["aggregate"]["phonemes"]
    )
    assert first["cells"]["deva"]["aggregate"]["span_squared_phonemes"] > 0


def test_static_selection_fails_on_cross_frontend_structure_mismatch(
    tmp_path: Path,
) -> None:
    config_path, _ = _config(tmp_path, mismatch=True)
    config = ContinuousSelectionConfig.load(config_path, repo_root=Path("."))
    with pytest.raises(ValueError, match="Cross-frontend continuous structure mismatch"):
        scan_continuous_structure(
            config,
            repo_root=Path("."),
            config_path=config_path,
        )
