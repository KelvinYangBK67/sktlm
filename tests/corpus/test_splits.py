"""Tests for stable manifest document IDs and splits."""

import pytest

from sktlm.corpus.splits import assign_split, make_document_id


def test_document_id_normalizes_path_separators() -> None:
    relative = "2_epic/ramayana/ram_01_u.txt"
    from_posix_spelling = make_document_id("gretil", relative)
    from_windows_spelling = make_document_id("gretil", relative.replace("/", "\\"))
    assert from_posix_spelling == from_windows_spelling
    assert from_posix_spelling.startswith("doc_")


def test_document_id_distinguishes_source_and_relative_path() -> None:
    assert make_document_id("gretil", "work.txt") != make_document_id("ambuda", "work.txt")
    assert make_document_id("gretil", "a/work.txt") != make_document_id("gretil", "b/work.txt")


def test_split_assignment_is_deterministic() -> None:
    ids = [make_document_id("gretil", f"work-{index}.txt") for index in range(100)]
    first = [assign_split(document_id) for document_id in ids]
    second = [assign_split(document_id) for document_id in ids]
    assert first == second
    assert set(first) == {"train", "dev", "test"}


def test_split_seed_is_explicit_and_effective() -> None:
    ids = [make_document_id("gretil", f"work-{index}.txt") for index in range(100)]
    assert [assign_split(item, seed="a") for item in ids] != [assign_split(item, seed="b") for item in ids]


@pytest.mark.parametrize(
    "ratios",
    [{}, {"train": 0.0}, {"train": -0.1, "test": 1.1}],
)
def test_invalid_split_ratios_are_rejected(ratios: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        assign_split("doc_example", ratios=ratios)
