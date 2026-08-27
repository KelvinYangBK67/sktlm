"""Tests for the four existing vocabulary diagnostic categories."""

from sktlm.diagnostics.vocab import categories


def test_existing_vocab_categories_are_preserved() -> None:
    assert categories({"piece": "▁ा", "clean_piece": "ा"}) == ["starts_with_dependent_vowel"]
    assert categories({"piece": "▁रामः", "clean_piece": "रामः"}) == ["contains_special_A"]
    assert categories({"piece": "▁का", "clean_piece": "का"}) == ["simple_cv"]
    assert categories({"piece": "▁त्", "clean_piece": "त्"}) == ["ends_with_virama"]
