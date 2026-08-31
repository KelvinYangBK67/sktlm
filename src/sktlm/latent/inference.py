"""Forward/backward inference over compact lexical candidate graphs."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from sktlm.latent.candidates import (
    CandidateGraph,
    LexicalBoundary,
    LexicalEdge,
    SegmentFactor,
    TokenLattice,
)
from sktlm.latent.phonology import PhonologicalForm
from sktlm.latent.vocabulary import FrozenVocabulary, ProjectedFormScorer


def logaddexp(left: float, right: float) -> float:
    if left == -math.inf:
        return right
    if right == -math.inf:
        return left
    maximum = max(left, right)
    return maximum + math.log(math.exp(left - maximum) + math.exp(right - maximum))


class FormScorer(Protocol):
    def score(self, form: PhonologicalForm) -> float: ...


@dataclass(frozen=True, slots=True)
class NeutralFormScorer:
    """Assign equal lexical score to every legal candidate edge."""

    def score(self, form: PhonologicalForm) -> float:
        del form
        return 0.0


@dataclass(slots=True)
class _MemoizedFormScorer:
    scorer: FormScorer
    cache: dict[PhonologicalForm, float]

    def __init__(self, scorer: FormScorer) -> None:
        self.scorer = scorer
        self.cache = {}

    def score(self, form: PhonologicalForm) -> float:
        try:
            return self.cache[form]
        except KeyError:
            score = self.scorer.score(form)
            self.cache[form] = score
            return score


@dataclass(frozen=True, slots=True)
class TokenPath:
    score: float
    words: tuple[PhonologicalForm, ...]
    rule_ids: tuple[str, ...]
    boundaries: tuple[LexicalBoundary, ...]


@dataclass(frozen=True, slots=True)
class TokenEvaluation:
    log_partition: float
    edge_posteriors: tuple[tuple[LexicalEdge, float], ...]
    expected_score: float
    identity_log_score: float
    top_paths: tuple[TokenPath, ...]


@dataclass(frozen=True, slots=True)
class FactorEvaluation:
    factor: SegmentFactor
    log_score: float
    expected_score: float
    identity_log_score: float
    token: TokenEvaluation | None
    top_paths: tuple[TokenPath, ...]


@dataclass(frozen=True, slots=True)
class AnalysisPosterior:
    words: tuple[PhonologicalForm, ...]
    probability: float
    log_score: float
    rule_ids: tuple[str, ...]
    boundaries: tuple[LexicalBoundary, ...]


@dataclass(frozen=True, slots=True)
class BoundaryPosterior:
    boundary_id: str
    cue_kind: str
    source_start: int
    source_end: int
    probability: float


@dataclass(frozen=True, slots=True)
class SegmentInference:
    log_partition: float
    entropy: float
    identity_mass: float
    latent_mass: float
    expected_lexical_tokens: float
    expected_counts: dict[PhonologicalForm, float]
    rule_usage: dict[str, float]
    boundary_posteriors: tuple[BoundaryPosterior, ...]
    top_analyses: tuple[AnalysisPosterior, ...]
    top_analysis_mass: float


@dataclass(frozen=True, slots=True)
class TrainingSegmentInference:
    log_partition: float
    identity_mass: float
    latent_mass: float
    expected_lexical_tokens: float
    expected_counts: dict[PhonologicalForm, float]


def _trim_paths(paths: list[TokenPath], limit: int) -> list[TokenPath]:
    paths.sort(
        key=lambda path: (
            -path.score,
            tuple(word.key for word in path.words),
            path.rule_ids,
        )
    )
    return paths[:limit]


def _project_form(
    form: PhonologicalForm,
    vocabulary: FrozenVocabulary | None,
) -> tuple[PhonologicalForm, ...]:
    return (form,) if vocabulary is None else vocabulary.project(form)


def _add_expected_count(
    counts: dict[PhonologicalForm, float],
    form: PhonologicalForm,
    mass: float,
    vocabulary: FrozenVocabulary | None,
) -> None:
    for projected in _project_form(form, vocabulary):
        counts[projected] += mass


def evaluate_token_lattice(
    lattice: TokenLattice,
    scorer: FormScorer,
    *,
    top_k: int | None,
    vocabulary: FrozenVocabulary | None = None,
) -> TokenEvaluation:
    outgoing = lattice.outgoing_edges
    incoming = lattice.incoming_edges
    edge_scores = {
        id(edge): scorer.score(edge.word)
        for edge in lattice.edges
    }
    node_count = len(lattice.nodes)
    alpha = [-math.inf] * node_count
    alpha[0] = 0.0
    for node in range(node_count - 1):
        if alpha[node] == -math.inf:
            continue
        for edge in outgoing[node]:
            alpha[edge.end] = logaddexp(
                alpha[edge.end],
                alpha[node] + edge_scores[id(edge)],
            )
    log_z = alpha[-1]
    if log_z == -math.inf:
        raise ValueError("Token lattice has no complete lexical analysis.")

    beta = [-math.inf] * node_count
    beta[-1] = 0.0
    for node in range(node_count - 2, -1, -1):
        for edge in outgoing[node]:
            beta[node] = logaddexp(
                beta[node],
                edge_scores[id(edge)] + beta[edge.end],
            )

    posteriors: list[tuple[LexicalEdge, float]] = []
    expected_score = 0.0
    identity_log_score = -math.inf
    for edge in lattice.edges:
        score = edge_scores[id(edge)]
        probability = math.exp(alpha[edge.start] + score + beta[edge.end] - log_z)
        posteriors.append((edge, probability))
        expected_score += probability * score
        if edge.identity_edge and edge.start == 0 and edge.end == node_count - 1:
            identity_log_score = score

    if top_k is None:
        return TokenEvaluation(
            log_partition=log_z,
            edge_posteriors=tuple(posteriors),
            expected_score=expected_score,
            identity_log_score=identity_log_score,
            top_paths=(),
        )

    paths_by_node: list[list[TokenPath]] = [[] for _ in range(node_count)]
    paths_by_node[0] = [TokenPath(0.0, (), (), ())]
    for node in range(node_count - 1):
        if not paths_by_node[node]:
            continue
        for edge in outgoing[node]:
            candidates = paths_by_node[edge.end]
            for prefix in paths_by_node[node]:
                candidates.append(
                    TokenPath(
                        score=prefix.score + edge_scores[id(edge)],
                        words=prefix.words + _project_form(edge.word, vocabulary),
                        rule_ids=prefix.rule_ids + edge.rule_ids,
                        boundaries=(
                            prefix.boundaries
                            + ((edge.boundary,) if edge.boundary is not None else ())
                        ),
                    )
                )
            paths_by_node[edge.end] = _trim_paths(candidates, top_k)

    return TokenEvaluation(
        log_partition=log_z,
        edge_posteriors=tuple(posteriors),
        expected_score=expected_score,
        identity_log_score=identity_log_score,
        top_paths=tuple(paths_by_node[-1]),
    )


def _evaluate_factor(
    factor: SegmentFactor,
    scorer: FormScorer,
    *,
    whitespace_merge_penalty: float,
    top_k: int | None,
    vocabulary: FrozenVocabulary | None,
) -> FactorEvaluation:
    if factor.merged_word is not None:
        score = scorer.score(factor.merged_word) - (
            whitespace_merge_penalty * factor.ignored_whitespace
        )
        path = TokenPath(
            score,
            _project_form(factor.merged_word, vocabulary),
            (),
            (),
        )
        paths = () if top_k is None else (path,)
        return FactorEvaluation(factor, score, score, -math.inf, None, paths)
    assert factor.lattice is not None
    token = evaluate_token_lattice(
        factor.lattice,
        scorer,
        top_k=top_k,
        vocabulary=vocabulary,
    )
    return FactorEvaluation(
        factor=factor,
        log_score=token.log_partition,
        expected_score=token.expected_score,
        identity_log_score=(
            token.identity_log_score
            if not factor.incoming.transformed and not factor.outgoing.transformed
            else -math.inf
        ),
        token=token,
        top_paths=token.top_paths,
    )


def _outer_forward(
    graph: CandidateGraph,
    evaluations: tuple[FactorEvaluation, ...],
    *,
    identity_only: bool = False,
) -> tuple[dict[str, float], ...]:
    states: list[dict[str, float]] = [dict() for _ in range(len(graph.segment.tokens) + 1)]
    states[0]["START"] = 0.0
    by_start: dict[int, list[FactorEvaluation]] = defaultdict(list)
    for evaluation in evaluations:
        by_start[evaluation.factor.start_token].append(evaluation)
    for position in range(len(graph.segment.tokens)):
        for evaluation in by_start[position]:
            factor = evaluation.factor
            prefix = states[position].get(factor.incoming.key, -math.inf)
            score = (
                evaluation.identity_log_score
                if identity_only
                else evaluation.log_score
            )
            if prefix == -math.inf or score == -math.inf:
                continue
            previous = states[factor.end_token].get(factor.outgoing.key, -math.inf)
            states[factor.end_token][factor.outgoing.key] = logaddexp(
                previous,
                prefix + score,
            )
    return tuple(states)


def _outer_backward(
    graph: CandidateGraph,
    evaluations: tuple[FactorEvaluation, ...],
) -> tuple[dict[str, float], ...]:
    token_count = len(graph.segment.tokens)
    beta: list[dict[str, float]] = [dict() for _ in range(token_count + 1)]
    beta[token_count]["END"] = 0.0
    by_start: dict[int, list[FactorEvaluation]] = defaultdict(list)
    for evaluation in evaluations:
        by_start[evaluation.factor.start_token].append(evaluation)
    for position in range(token_count - 1, -1, -1):
        for evaluation in by_start[position]:
            factor = evaluation.factor
            suffix = beta[factor.end_token].get(factor.outgoing.key, -math.inf)
            if suffix == -math.inf:
                continue
            previous = beta[position].get(factor.incoming.key, -math.inf)
            beta[position][factor.incoming.key] = logaddexp(
                previous,
                evaluation.log_score + suffix,
            )
    return tuple(beta)


def _outer_top_paths(
    graph: CandidateGraph,
    evaluations: tuple[FactorEvaluation, ...],
    *,
    top_k: int,
) -> tuple[TokenPath, ...]:
    states: list[dict[str, list[TokenPath]]] = [
        {} for _ in range(len(graph.segment.tokens) + 1)
    ]
    states[0]["START"] = [TokenPath(0.0, (), (), ())]
    by_start: dict[int, list[FactorEvaluation]] = defaultdict(list)
    for evaluation in evaluations:
        by_start[evaluation.factor.start_token].append(evaluation)
    for position in range(len(graph.segment.tokens)):
        for evaluation in by_start[position]:
            factor = evaluation.factor
            prefixes = states[position].get(factor.incoming.key, ())
            if not prefixes:
                continue
            candidates = states[factor.end_token].setdefault(factor.outgoing.key, [])
            visible_boundary: tuple[LexicalBoundary, ...] = ()
            outer_rules: tuple[str, ...] = ()
            if factor.end_token < len(graph.segment.tokens):
                boundary_index = factor.end_token
                left = graph.segment.tokens[boundary_index - 1]
                right = graph.segment.tokens[boundary_index]
                visible_boundary = (
                    LexicalBoundary(
                        boundary_id=f"visible:{boundary_index}",
                        cue_kind="space",
                        source_start=left.source_end,
                        source_end=right.source_start,
                    ),
                )
                outer_rules = factor.outgoing.rule_ids
            for prefix in prefixes:
                for local in evaluation.top_paths:
                    candidates.append(
                        TokenPath(
                            score=prefix.score + local.score,
                            words=prefix.words + local.words,
                            rule_ids=prefix.rule_ids + local.rule_ids + outer_rules,
                            boundaries=prefix.boundaries + local.boundaries + visible_boundary,
                        )
                    )
            states[factor.end_token][factor.outgoing.key] = _trim_paths(
                candidates,
                top_k,
            )
    return tuple(states[-1].get("END", ()))


def infer_training_segment(
    graph: CandidateGraph,
    scorer: FormScorer,
    *,
    whitespace_merge_penalty: float,
    vocabulary: FrozenVocabulary | None = None,
) -> TrainingSegmentInference:
    '''Exact marginals needed by EM training, without inspection decoding.'''

    effective_scorer: FormScorer = (
        scorer
        if vocabulary is None
        else ProjectedFormScorer(scorer, vocabulary)
    )
    memoized_scorer = (
        effective_scorer
        if isinstance(effective_scorer, NeutralFormScorer)
        else _MemoizedFormScorer(effective_scorer)
    )
    evaluations = tuple(
        _evaluate_factor(
            factor,
            memoized_scorer,
            whitespace_merge_penalty=whitespace_merge_penalty,
            top_k=None,
            vocabulary=vocabulary,
        )
        for factor in graph.factors
    )
    forward = _outer_forward(graph, evaluations)
    log_z = forward[-1].get('END', -math.inf)
    if log_z == -math.inf:
        raise ValueError('Candidate graph has no complete analysis.')
    backward = _outer_backward(graph, evaluations)

    expected_counts: dict[PhonologicalForm, float] = defaultdict(float)
    for evaluation in evaluations:
        factor = evaluation.factor
        prefix = forward[factor.start_token].get(factor.incoming.key, -math.inf)
        suffix = backward[factor.end_token].get(factor.outgoing.key, -math.inf)
        if prefix == -math.inf or suffix == -math.inf:
            continue
        factor_mass = math.exp(prefix + evaluation.log_score + suffix - log_z)
        if factor.merged_word is not None:
            _add_expected_count(
                expected_counts,
                factor.merged_word,
                factor_mass,
                vocabulary,
            )
            continue
        assert evaluation.token is not None
        for edge, conditional_mass in evaluation.token.edge_posteriors:
            _add_expected_count(
                expected_counts,
                edge.word,
                factor_mass * conditional_mass,
                vocabulary,
            )

    identity_forward = _outer_forward(graph, evaluations, identity_only=True)
    identity_log_z = identity_forward[-1].get('END', -math.inf)
    identity_mass = (
        0.0
        if identity_log_z == -math.inf
        else min(1.0, math.exp(identity_log_z - log_z))
    )
    expected_tokens = sum(expected_counts.values())
    return TrainingSegmentInference(
        log_partition=log_z,
        identity_mass=identity_mass,
        latent_mass=1.0 - identity_mass,
        expected_lexical_tokens=expected_tokens,
        expected_counts=dict(expected_counts),
    )


def infer_segment(
    graph: CandidateGraph,
    scorer: FormScorer,
    *,
    whitespace_merge_penalty: float,
    top_k: int = 8,
    vocabulary: FrozenVocabulary | None = None,
) -> SegmentInference:
    """Exact marginalization; only the bounded top-k inspection list is decoded."""

    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    effective_scorer: FormScorer = (
        scorer
        if vocabulary is None
        else ProjectedFormScorer(scorer, vocabulary)
    )
    memoized_scorer = (
        effective_scorer
        if isinstance(effective_scorer, NeutralFormScorer)
        else _MemoizedFormScorer(effective_scorer)
    )
    evaluations = tuple(
        _evaluate_factor(
            factor,
            memoized_scorer,
            whitespace_merge_penalty=whitespace_merge_penalty,
            top_k=top_k,
            vocabulary=vocabulary,
        )
        for factor in graph.factors
    )
    forward = _outer_forward(graph, evaluations)
    log_z = forward[-1].get("END", -math.inf)
    if log_z == -math.inf:
        raise ValueError("Candidate graph has no complete analysis.")
    backward = _outer_backward(graph, evaluations)

    expected_counts: dict[PhonologicalForm, float] = defaultdict(float)
    rule_usage: dict[str, float] = defaultdict(float)
    boundary_mass: dict[str, float] = defaultdict(float)
    boundary_meta: dict[str, LexicalBoundary] = {}
    expected_score = 0.0

    for evaluation in evaluations:
        factor = evaluation.factor
        prefix = forward[factor.start_token].get(factor.incoming.key, -math.inf)
        suffix = backward[factor.end_token].get(factor.outgoing.key, -math.inf)
        if prefix == -math.inf or suffix == -math.inf:
            continue
        factor_mass = math.exp(prefix + evaluation.log_score + suffix - log_z)
        expected_score += factor_mass * evaluation.expected_score
        if factor.merged_word is not None:
            _add_expected_count(
                expected_counts,
                factor.merged_word,
                factor_mass,
                vocabulary,
            )
        else:
            assert evaluation.token is not None
            for edge, conditional_mass in evaluation.token.edge_posteriors:
                mass = factor_mass * conditional_mass
                _add_expected_count(
                    expected_counts,
                    edge.word,
                    mass,
                    vocabulary,
                )
                if edge.boundary is not None:
                    boundary_mass[edge.boundary.boundary_id] += mass
                    boundary_meta[edge.boundary.boundary_id] = edge.boundary
                for rule_id in edge.rule_ids:
                    rule_usage[rule_id] += mass / len(edge.rule_ids)
        if factor.end_token < len(graph.segment.tokens):
            boundary_index = factor.end_token
            boundary_id = f"visible:{boundary_index}"
            left = graph.segment.tokens[boundary_index - 1]
            right = graph.segment.tokens[boundary_index]
            boundary_mass[boundary_id] += factor_mass
            boundary_meta[boundary_id] = LexicalBoundary(
                boundary_id,
                "space",
                left.source_end,
                right.source_start,
            )
            for rule_id in factor.outgoing.rule_ids:
                rule_usage[rule_id] += factor_mass / len(factor.outgoing.rule_ids)

    identity_forward = _outer_forward(graph, evaluations, identity_only=True)
    identity_log_z = identity_forward[-1].get("END", -math.inf)
    identity_mass = (
        0.0
        if identity_log_z == -math.inf
        else min(1.0, math.exp(identity_log_z - log_z))
    )
    decoded = _outer_top_paths(graph, evaluations, top_k=top_k)
    analyses = tuple(
        AnalysisPosterior(
            words=path.words,
            probability=math.exp(path.score - log_z),
            log_score=path.score,
            rule_ids=path.rule_ids,
            boundaries=path.boundaries,
        )
        for path in decoded
    )
    boundaries = tuple(
        BoundaryPosterior(
            boundary_id=boundary_id,
            cue_kind=boundary_meta[boundary_id].cue_kind,
            source_start=boundary_meta[boundary_id].source_start,
            source_end=boundary_meta[boundary_id].source_end,
            probability=min(1.0, probability),
        )
        for boundary_id, probability in sorted(boundary_mass.items())
    )
    expected_tokens = sum(expected_counts.values())
    return SegmentInference(
        log_partition=log_z,
        entropy=max(0.0, log_z - expected_score),
        identity_mass=identity_mass,
        latent_mass=1.0 - identity_mass,
        expected_lexical_tokens=expected_tokens,
        expected_counts=dict(expected_counts),
        rule_usage=dict(rule_usage),
        boundary_posteriors=boundaries,
        top_analyses=analyses,
        top_analysis_mass=sum(item.probability for item in analyses),
    )
