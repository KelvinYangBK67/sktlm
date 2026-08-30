from __future__ import annotations

import csv
import inspect
from pathlib import Path

import sktlm.representations.generate as generation_module
from sktlm.representations.generate import (
    generate_representations,
    validate_representations,
)


def write_manifest(path: Path, canonical_path: Path) -> None:
    fields = ["canonical_path", "canonical_hash", "freeze_id", "freeze_input_path"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerow(
            {
                "canonical_path": canonical_path.as_posix(),
                "canonical_hash": "canonical-hash",
                "freeze_id": "freeze-123",
                "freeze_input_path": "1_veda/example.txt",
            }
        )


def test_generate_and_validate_six_conditions(tmp_path: Path) -> None:
    canonical_root = tmp_path / "canonical/gretil_iast"
    canonical_path = canonical_root / "1_veda/example.txt"
    canonical_path.parent.mkdir(parents=True)
    canonical_path.write_text(
        "deva\u015b ca |\nr\u0101ma\u1e25\n", encoding="utf-8", newline=""
    )
    canonical_manifest = tmp_path / "canonical.csv"
    write_manifest(canonical_manifest, canonical_path)
    output_root = tmp_path / "representations"
    manifest = tmp_path / "representations.csv"
    report = tmp_path / "report.txt"

    result = generate_representations(
        canonical_root=canonical_root,
        canonical_manifest=canonical_manifest,
        output_root=output_root,
        manifest_path=manifest,
        report_path=report,
    )
    validated = validate_representations(
        canonical_root=canonical_root,
        output_root=output_root,
        manifest_path=manifest,
    )

    assert validated == result
    assert result.representation_files == 6
    assert result.boundary_sidecars == 0
    assert (output_root / "iast/surface_word/1_veda/example.txt").read_bytes() == canonical_path.read_bytes()
    expected_layout = {
        f"{script}/{condition}/1_veda/example.txt"
        for script in ("iast", "devanagari")
        for condition in ("surface_word", "legacy_joined", "continuous")
    }
    assert {
        path.relative_to(output_root).as_posix()
        for path in output_root.rglob("*.txt")
    } == expected_layout
    assert not tuple(output_root.rglob("*.boundaries.jsonl"))

    with manifest.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["condition"] for row in rows} == {
        "surface_word",
        "legacy_joined",
        "continuous",
    }
    assert all(not row["boundary_path"] for row in rows)
    assert all(row["boundary_count"] == "0" for row in rows)
    assert "boundary_sidecars: 0" in report.read_text(encoding="utf-8")


def test_formal_generator_does_not_use_devanagari_post_normalization() -> None:
    assert "normalize_devanagari_text" not in inspect.getsource(
        generation_module.generate_representations
    )
