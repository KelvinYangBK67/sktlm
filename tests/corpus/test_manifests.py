"""Tests for manifest metadata added without changing legacy row semantics."""

from pathlib import Path

from sktlm.corpus.manifests.build import FileInfo, add_row


def make_info(path: Path) -> FileInfo:
    return FileInfo(
        path=path,
        relative="2_epic/work.txt",
        source="gretil",
        layer="epic",
        chars=100,
        lines=5,
        compact_chars=80,
        compact_hash="hash",
        prefix_sample="sample",
    )


def test_manifest_document_metadata_ignores_absolute_root() -> None:
    first: list[dict[str, str]] = []
    second: list[dict[str, str]] = []
    add_row(first, make_info(Path("C:/corpus-a/2_epic/work.txt")), "primary", "", 1.0, 1.0, 1.0)
    add_row(second, make_info(Path("D:/corpus-b/2_epic/work.txt")), "primary", "", 1.0, 1.0, 1.0)
    assert first[0]["document_id"] == second[0]["document_id"]
    assert first[0]["split"] == second[0]["split"]


def test_manifest_preserves_legacy_values_and_appends_metadata() -> None:
    rows: list[dict[str, str]] = []
    add_row(rows, make_info(Path("data/work.txt")), "primary", "", 0.8, 1.0, 0.8)
    row = rows[0]
    assert list(row) == [
        "path",
        "source",
        "layer",
        "chars",
        "lines",
        "compact_chars",
        "duplicate_status",
        "duplicate_of",
        "layer_weight",
        "duplicate_weight",
        "final_weight",
        "effective_chars",
        "document_id",
        "split",
    ]
    assert row["layer_weight"] == "0.800"
    assert row["duplicate_weight"] == "1.000"
    assert row["final_weight"] == "0.800"
    assert row["effective_chars"] == "80.0"
