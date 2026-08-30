"""Regression tests for deterministic weighted corpus sampling."""

from sktlm.corpus.weighted import include_line, normalize_commas, split_on_danda


def test_weighted_sampling_is_deterministic() -> None:
    first = [include_line("fixed-seed", "corpus/work.txt", line, 0.35) for line in range(1, 101)]
    second = [include_line("fixed-seed", "corpus/work.txt", line, 0.35) for line in range(1, 101)]
    assert first == second
    assert 0 < sum(first) < len(first)


def test_weight_boundaries_are_preserved() -> None:
    assert include_line("seed", "path", 1, 1.0)
    assert not include_line("seed", "path", 1, 0.0)


def test_existing_comma_handling_is_preserved() -> None:
    assert normalize_commas(",राम, सीता ,गीता") == "राम। सीता गीता"


def test_existing_danda_splitting_is_preserved() -> None:
    assert split_on_danda("रामः। सीता॥ गीता") == ["रामः।", "सीता॥", "गीता"]
