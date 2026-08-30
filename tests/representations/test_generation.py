from __future__ import annotations

import csv
from pathlib import Path

from sktlm.representations.generate import (
    boundary_offsets,
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


def test_boundary_offsets_use_only_observed_spaces() -> None:
    assert boundary_offsets("deva\u015b  ca r\u0101ma\u1e25 ") == [5, 7]
    assert boundary_offsets("continuous") == []


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
    assert result.boundary_sidecars == 2
    assert (output_root / "iast/surface_word/1_veda/example.txt").read_bytes() == canonical_path.read_bytes()
    assert (
        output_root / "iast/continuous/1_veda/example.txt"
    ).read_bytes() == (
        output_root / "iast/lexical_boundary/1_veda/example.txt"
    ).read_bytes()
    assert "proxy, not inferred or gold" in report.read_text(encoding="utf-8")
