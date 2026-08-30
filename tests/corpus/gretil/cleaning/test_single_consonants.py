import csv
from pathlib import Path

import pytest

from sktlm.corpus.gretil.cleaning.single_consonants import (
    KeepEntry,
    VAIMP,
    _clean_one_file,
    _validate_no_confirmed_english,
    materialize_keep_whitelist,
)


def _write_tsv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def test_materialize_keep_whitelist_checks_exact_context_and_multiplicity(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    source = root / "x.txt"
    source.parent.mkdir(parents=True)
    context = "m a m k ā ṃ"
    source.write_text(context + "\n", encoding="utf-8", newline="")
    spec = tmp_path / "spec.tsv"
    audit = tmp_path / "audit.tsv"
    output = tmp_path / "materialized.tsv"
    _write_tsv(
        spec,
        ("file", "token", "line_no", "occurrence_count"),
        [{"file": "x.txt", "token": "m", "line_no": 1, "occurrence_count": 2}],
    )
    _write_tsv(
        audit,
        ("file", "line_no", "token", "context"),
        [
            {"file": "x.txt", "line_no": 1, "token": "m", "context": context},
            {"file": "x.txt", "line_no": 1, "token": "m", "context": context},
        ],
    )

    rows = materialize_keep_whitelist(
        source_root=root,
        audit_path=audit,
        spec_path=spec,
        output_path=output,
    )

    assert rows == (KeepEntry("x.txt", 1, "m", 2, context),)
    assert output.read_text(encoding="utf-8").splitlines()[1].split("\t")[3] == "2"


def test_materialize_keep_whitelist_stops_on_count_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "x.txt").write_text("m\n", encoding="utf-8")
    spec = tmp_path / "spec.tsv"
    audit = tmp_path / "audit.tsv"
    _write_tsv(
        spec,
        ("file", "token", "line_no", "occurrence_count"),
        [{"file": "x.txt", "token": "m", "line_no": 1, "occurrence_count": 2}],
    )
    _write_tsv(
        audit,
        ("file", "line_no", "token", "context"),
        [{"file": "x.txt", "line_no": 1, "token": "m", "context": "m"}],
    )

    with pytest.raises(RuntimeError, match="KEEP audit mismatch"):
        materialize_keep_whitelist(
            source_root=root,
            audit_path=audit,
            spec_path=spec,
            output_path=tmp_path / "out.tsv",
        )


def test_cleaning_keeps_exact_occurrences_vowels_and_signs() -> None:
    keep = KeepEntry("x.txt", 1, "m", 2, "m a m k ā ṃ")
    after, rows, expected, before_count, iterations = _clean_one_file(
        relative="x.txt",
        text="m a m k ā ṃ\n",
        keep_by_key={("x.txt", 1, "m"): keep},
    )

    assert after == "m a m ā ṃ\n"
    assert expected == {("x.txt", 1, "m"): 2}
    assert before_count == 3
    assert iterations >= 2
    assert [(row.token, row.occurrence_count) for row in rows] == [("k", 1)]


def test_cleaning_removes_confirmed_whole_line_and_only_mixed_marker() -> None:
    whole, rows, expected, before_count, _iterations = _clean_one_file(
        relative=VAIMP,
        text="check p |\n",
        keep_by_key={},
    )
    assert whole == ""
    assert expected == {}
    assert before_count == 1
    assert rows[0].category == "english_editorial"

    mixed, mixed_rows, _expected, _before, _iterations = _clean_one_file(
        relative="x.txt",
        text="sa add | vā\n",
        keep_by_key={},
    )
    assert mixed == "sa | vā\n"
    assert any(row.rule == "english_marker" for row in mixed_rows)


def test_confirmed_english_validator_includes_division(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "x.txt").write_text("sūtra division |\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="division"):
        _validate_no_confirmed_english(root)
