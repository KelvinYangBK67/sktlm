from __future__ import annotations

from sktlm.latent.candidates import build_candidate_graph
from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.inference import infer_segment
from sktlm.latent.phonology import PhonologicalForm


class _CountingScorer:
    def __init__(self) -> None:
        self.calls = 0

    def score(self, form: PhonologicalForm) -> float:
        self.calls += 1
        return -0.25 * len(form.symbols)


def test_segment_scores_each_distinct_form_once() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments('devo\'pi api ca'))
    graph = build_candidate_graph(segment, grammar)
    forms = {
        edge.word
        for factor in graph.factors
        if factor.lattice is not None
        for edge in factor.lattice.edges
    }
    forms.update(
        factor.merged_word
        for factor in graph.factors
        if factor.merged_word is not None
    )
    scorer = _CountingScorer()

    infer_segment(
        graph,
        scorer,
        whitespace_merge_penalty=8.0,
        top_k=8,
    )

    assert scorer.calls == len(forms)
