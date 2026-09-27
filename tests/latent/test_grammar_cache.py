from __future__ import annotations

from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar


def test_internal_match_cache_uses_script_neutral_surface_keys() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments('api api'))
    first, second = segment.tokens

    first_matches = tuple(grammar.iter_internal_matches(first.units))
    after_first = grammar.cache_statistics()['internal_matches']
    second_matches = tuple(grammar.iter_internal_matches(second.units))
    after_second = grammar.cache_statistics()['internal_matches']

    assert first_matches == second_matches
    assert after_first['misses'] == 1
    assert after_second['misses'] == 1
    assert after_second['hits'] == 1
    assert after_second['maxsize'] == 100_000


def test_internal_match_cache_bypasses_long_tokens_without_changing_matches() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    token = next(iter_observed_segments("a" * 257)).tokens[0]

    first = tuple(grammar.iter_internal_matches(token.units))
    second = tuple(grammar.iter_internal_matches(token.units))
    statistics = grammar.cache_statistics()["internal_matches"]

    assert first == second
    assert statistics["hits"] == 0
    assert statistics["misses"] == 2
    assert statistics["long_token_bypasses"] == 2
    assert statistics["currsize"] == 0
    assert statistics["cached_token_units"] == 0
    assert statistics["cached_match_count"] == 0
