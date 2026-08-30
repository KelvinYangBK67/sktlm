from __future__ import annotations

import csv
from pathlib import Path

from sktlm.corpus.gretil.cleaning.semantic import (
    _raw_boundary_evidence,
    adjudicate_adjacent_vowels,
    apply_boundary_repairs,
    find_adjacent_vowels,
    normalize_laterals,
    scan_non_sanskrit_candidates,
)


def test_normalizes_only_vowel_adjacent_laterals() -> None:
    result = normalize_laterals(
        "īḷe iḷā puroḷāśa aḷha kḷha kḷpta ḷ ḷh"
    )
    assert result.text == (
        "īḍe iḍā puroḍāśa aḍha kḍha kḷpta ḷ ḷh"
    )
    assert result.l_to_d == 3
    assert result.lh_to_dh == 2


def test_adjacent_vowels_exclude_exact_ai_and_au() -> None:
    rows = find_adjacent_vowels(
        "pūutinā bhuñjīita vipluaṃ ai au", relative="example.txt"
    )
    assert [row.matched_sequence for row in rows] == ["ūu", "īi", "ua"]


def test_raw_boundary_index_distinguishes_space_joined_and_hyphen() -> None:
    targets = {
        ("ataeva", 2),
        ("aevam", 0),
        ("guṇaāptī", 3),
    }
    evidence = _raw_boundary_evidence(
        "ata eva aevam guṇa-āptī", targets
    )
    assert evidence[("ataeva", 2)] == [" "]
    assert evidence[("aevam", 0)] == [""]
    assert ("guṇaāptī", 3) not in evidence


def test_non_sanskrit_scan_never_flags_ambiguous_short_words_alone(
    tmp_path: Path,
) -> None:
    root = tmp_path / "canonical"
    root.mkdir()
    (root / "example.txt").write_text(
        "a in as is | edition notes | bskal pa med gsum\n",
        encoding="utf-8",
        newline="",
    )
    output = tmp_path / "candidates.tsv"
    rows = scan_non_sanskrit_candidates(root=root, output_path=output)
    spans = {row["matched_span"] for row in rows}
    categories = {row["category"] for row in rows}
    assert not any(span in {"a", "in", "as", "is"} for span in spans)
    assert "edition notes" in spans
    assert "tibetan_transliteration" in categories


def test_non_sanskrit_scan_recognizes_standalone_division(
    tmp_path: Path,
) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "sample.txt").write_text(
        "division\n", encoding="utf-8"
    )
    rows = scan_non_sanskrit_candidates(
        root=root, output_path=tmp_path / "candidates.tsv"
    )
    assert len(rows) == 1
    assert rows[0]["matched_span"] == "division"


def test_provenance_repairs_only_raw_ascii_space(
    tmp_path: Path,
) -> None:
    relative = "layer/example.txt"
    original = "ataeva aevam guṇaāptī īḷe\n"
    lateral = normalize_laterals(original).text
    strict_root = tmp_path / "strict"
    document_root = tmp_path / "document"
    for root in (strict_root, document_root):
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_text(original, encoding="utf-8", newline="")
    raw = tmp_path / "raw.htm"
    raw.write_text(
        "ata eva aevam guṇa-āptī īḷe", encoding="utf-8", newline=""
    )
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "freeze_input_path",
                "source_path",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "freeze_input_path": relative,
                "source_path": str(raw),
            }
        )

    rows = adjudicate_adjacent_vowels(
        original_texts={relative: original},
        lateral_texts={relative: lateral},
        strict_root=strict_root,
        document_root=document_root,
        manifest_path=manifest,
    )
    by_form = {row.form_before: row for row in rows}
    assert by_form["ataeva"].status == "PIPELINE_BOUNDARY_LOSS_FIXED"
    assert by_form["ataeva"].raw_form == "ata eva"
    assert by_form["aevam"].status == "SOURCE_PRESENT"
    assert by_form["guṇaāptī"].status == "UNRESOLVED"

    repaired = apply_boundary_repairs({relative: lateral}, rows)
    assert repaired[relative] == "ata eva aevam guṇaāptī īḍe\n"
