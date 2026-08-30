from __future__ import annotations

from sktlm.latent.candidates import build_candidate_graph
from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.inference import (
    NeutralFormScorer,
    infer_segment,
    infer_training_segment,
)
from sktlm.latent.phonology import PhonologicalForm


class _LengthScorer:
    @staticmethod
    def score(form: PhonologicalForm) -> float:
        return -0.25 * len(form.symbols)


def test_training_inference_matches_full_exact_marginals() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments('devo\'pi api ca'))
    graph = build_candidate_graph(segment, grammar)

    for scorer in (NeutralFormScorer(), _LengthScorer()):
        full = infer_segment(
            graph,
            scorer,
            whitespace_merge_penalty=8.0,
            top_k=8,
        )
        training = infer_training_segment(
            graph,
            scorer,
            whitespace_merge_penalty=8.0,
        )

        assert training.log_partition == full.log_partition
        assert training.identity_mass == full.identity_mass
        assert training.latent_mass == full.latent_mass
        assert training.expected_lexical_tokens == full.expected_lexical_tokens
        assert training.expected_counts == full.expected_counts
