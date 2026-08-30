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
