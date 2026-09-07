"""Exact production composition of lazy lexical spans and reusable pieces.

This module is the S1M2-P1c inference kernel.  It preserves the P0 legal
piece support and scoring equations, but evaluates the position dynamic
program directly and shares fixed-pass results through explicitly bounded
caches.  It never constructs :class:`~sktlm.pieces.lattice.PieceLattice`
objects or persistent lexical-edge rows.
"""

from __future__ import annotations

import heapq
import math
import time
from array import array
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field

from sktlm.latent.candidates import LexicalBoundary
from sktlm.latent.inference import BoundaryPosterior, logaddexp
from sktlm.latent.lazy_candidates import (
    LazyCandidateGraph,
    LazyLexicalSpan,
    LazySegmentFactor,
    LazyTokenLattice,
)
from sktlm.latent.phonology import Phoneme, PhonologicalForm
from sktlm.pieces.inference import PieceSegmentation
from sktlm.pieces.model import PieceModelConfig
from sktlm.pieces.scorer import PieceScorer


@dataclass(frozen=True, slots=True)
class ComposedCacheConfig:
    """Engineering-only finite bounds for one fixed inference pass."""

    piece_score_entries: int = 65_536
    piece_score_bytes: int = 32 * 1024 * 1024
    form_entries: int = 8_192
    form_bytes: int = 256 * 1024 * 1024
    shared_token_marginals: bool = True
    shared_prefix_nodes: int = 262_144
    shared_top_k_piece_references: int = 4_194_304

    def __post_init__(self) -> None:
        for name, value in (
            ("piece_score_entries", self.piece_score_entries),
            ("piece_score_bytes", self.piece_score_bytes),
            ("form_entries", self.form_entries),
            ("form_bytes", self.form_bytes),
            ("shared_prefix_nodes", self.shared_prefix_nodes),
            (
                "shared_top_k_piece_references",
                self.shared_top_k_piece_references,
            ),
        ):
            if value < 1:
                raise ValueError(f"{name} must be >= 1")
        if not isinstance(self.shared_token_marginals, bool):
            raise TypeError("shared_token_marginals must be bool")


@dataclass(frozen=True, slots=True)
class FormPieceEvaluation:
    """Exact fixed-pass reusable-piece marginals conditional on one form."""

    form: PhonologicalForm
    prior_log_normalizer: float
    log_score: float
    expected_piece_counts: dict[PhonologicalForm, float]
    expected_log_weight: float
    segmentation_entropy: float
    expected_piece_tokens: float
    whole_form_mass: float
    singleton_path_mass: float
    multi_piece_mass: float
    top_segmentations: tuple[PieceSegmentation, ...]


@dataclass(frozen=True, slots=True)
class ComposedInferenceCounters:
    """Deterministic work counters plus current bounded-cache gauges."""

    lazy_span_traversals: int = 0
    candidate_span_hypotheses: int = 0
    merged_form_traversals: int = 0
    candidate_factors: int = 0
    candidate_nodes: int = 0
    composed_state_count: int = 0
    composed_transition_count: int = 0
    piece_score_calls: int = 0
    piece_score_cache_hits: int = 0
    piece_score_cache_misses: int = 0
    piece_score_cache_evictions: int = 0
    piece_score_cache_oversize: int = 0
    form_cache_hits: int = 0
    form_cache_misses: int = 0
    form_cache_evictions: int = 0
    form_cache_oversize: int = 0
    shared_prefix_nodes: int = 0
    shared_form_endpoints: int = 0
    shared_batch_fallbacks: int = 0
    shared_top_k_states: int = 0
    shared_top_k_paths: int = 0
    topology_compiles: int = 0
    topology_reuses: int = 0
    store_lookups: int = 0
    piece_score_cache_entries: int = 0
    piece_score_cache_estimated_bytes: int = 0
    form_cache_entries: int = 0
    form_cache_estimated_bytes: int = 0


@dataclass(frozen=True, slots=True)
class ComposedInferenceTimings:
    """Nested engineering-only phase timings for exact composed inference."""

    inner_piece_evaluation_seconds: float = 0.0
    inner_piece_transition_build_seconds: float = 0.0
    inner_piece_topology_compile_seconds: float = 0.0
    inner_piece_reweight_seconds: float = 0.0
    inner_piece_forward_seconds: float = 0.0
    inner_piece_backward_seconds: float = 0.0
    inner_piece_posterior_seconds: float = 0.0
    inner_piece_top_k_seconds: float = 0.0
    lazy_token_forward_seconds: float = 0.0
    lazy_token_backward_seconds: float = 0.0
    lazy_token_posterior_seconds: float = 0.0
    lazy_token_top_k_seconds: float = 0.0
    piece_composition_seconds: float = 0.0
    outer_forward_seconds: float = 0.0
    outer_backward_seconds: float = 0.0
    outer_posterior_seconds: float = 0.0
    outer_identity_seconds: float = 0.0
    outer_top_k_seconds: float = 0.0


_EVENT_COUNTERS = (
    "lazy_span_traversals",
    "candidate_span_hypotheses",
    "merged_form_traversals",
    "candidate_factors",
    "candidate_nodes",
    "composed_state_count",
    "composed_transition_count",
    "piece_score_calls",
    "piece_score_cache_hits",
    "piece_score_cache_misses",
    "piece_score_cache_evictions",
    "piece_score_cache_oversize",
    "form_cache_hits",
    "form_cache_misses",
    "form_cache_evictions",
    "form_cache_oversize",
    "shared_prefix_nodes",
    "shared_form_endpoints",
    "shared_batch_fallbacks",
    "shared_top_k_states",
    "shared_top_k_paths",
    "topology_compiles",
    "topology_reuses",
    "store_lookups",
)

_TIMING_COUNTERS = tuple(ComposedInferenceTimings.__dataclass_fields__)


@dataclass(frozen=True, slots=True)
class ComposedSegmentInference:
    """Exact outer and inner S1M2 posterior summaries for one segment."""

    log_partition: float
    entropy: float
    identity_mass: float
    latent_mass: float
    expected_lexical_tokens: float
    expected_piece_tokens: float
    piece_segmentation_entropy: float
    expected_whole_form_uses: float
    expected_singleton_path_uses: float
    expected_multi_piece_uses: float
    lexical_expected_counts: dict[PhonologicalForm, float]
    piece_expected_counts: dict[PhonologicalForm, float]
    rule_usage: dict[str, float]
    boundary_posteriors: tuple[BoundaryPosterior, ...]
    top_analyses: tuple[ComposedAnalysisPosterior, ...]
    top_analysis_mass: float
    piece_occurrence_support: dict[PhonologicalForm, int]
    total_posterior_mass: float
    counters: ComposedInferenceCounters
    timings: ComposedInferenceTimings


@dataclass(frozen=True, slots=True)
class ComposedAnalysisPosterior:
    """One bounded presentation path; never part of inference support."""

    words: tuple[PhonologicalForm, ...]
    piece_segmentations: tuple[tuple[PhonologicalForm, ...], ...]
    probability: float
    log_score: float
    rule_ids: tuple[str, ...]
    boundaries: tuple[LexicalBoundary, ...]


@dataclass(frozen=True, slots=True)
class _ComposedPath:
    score: float
    words: tuple[PhonologicalForm, ...]
    piece_segmentations: tuple[tuple[PhonologicalForm, ...], ...]
    rule_ids: tuple[str, ...]
    boundaries: tuple[LexicalBoundary, ...]
    tie_key: tuple[
        tuple[str, ...],
        tuple[tuple[str, ...], ...],
        tuple[str, ...],
    ]


@dataclass(frozen=True, slots=True)
class _TokenSummary:
    log_partition: float
    expected_log_weight: float
    identity_log_score: float
    expected_piece_tokens: float
    piece_segmentation_entropy: float
    expected_whole_form_uses: float
    expected_singleton_path_uses: float
    expected_multi_piece_uses: float
    lexical_counts: dict[PhonologicalForm, float]
    piece_counts: dict[PhonologicalForm, float]
    boundary_mass: dict[str, float]
    boundary_meta: dict[str, LexicalBoundary]
    rule_usage: dict[str, float]
    piece_occurrences: dict[PhonologicalForm, dict[str, float]]
    top_paths: tuple[_ComposedPath, ...]


@dataclass(frozen=True, slots=True)
class _FactorSummary:
    factor: LazySegmentFactor
    log_score: float
    expected_log_weight: float
    identity_log_score: float
    expected_piece_tokens: float
    piece_segmentation_entropy: float
    expected_whole_form_uses: float
    expected_singleton_path_uses: float
    expected_multi_piece_uses: float
    lexical_counts: dict[PhonologicalForm, float]
    piece_counts: dict[PhonologicalForm, float]
    boundary_mass: dict[str, float]
    boundary_meta: dict[str, LexicalBoundary]
    rule_usage: dict[str, float]
    piece_occurrences: dict[PhonologicalForm, dict[str, float]]
    top_paths: tuple[_ComposedPath, ...]


@dataclass(frozen=True, slots=True)
class _SharedInnerPath:
    score: float
    pieces: tuple[PhonologicalForm, ...]
    piece_keys: tuple[str, ...]


@dataclass(slots=True)
class _SharedPrefixNode:
    parent: int
    symbol: Phoneme | None
    depth: int
    children: dict[Phoneme, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CompiledSharedFormTopology:
    """Compact immutable support for one shared lexical-form prefix DAG."""

    max_piece_length: int
    parent: array
    depth: array
    transition_offsets: array
    transition_sources: array
    transition_piece_ids: array
    pieces: tuple[tuple[Phoneme, ...], ...]
    form_keys: tuple[str, ...]
    endpoint_nodes: array
    whole_piece_ids: array


@dataclass(frozen=True, slots=True)
class CompiledSegmentTopology:
    """Factor-aligned immutable topology for one observed segment."""

    factor_ids: tuple[str, ...]
    factors: tuple[CompiledSharedFormTopology | None, ...]
    reused: bool = False


@dataclass(frozen=True, slots=True)
class _SharedFormScore:
    form: PhonologicalForm
    node: int
    prior_log_normalizer: float
    raw_log_partition: float
    log_score: float
    whole_piece: PhonologicalForm
    whole_raw_score: float
    singleton_score: float


@dataclass(slots=True)
class _SharedFormBatch:
    topology: CompiledSharedFormTopology
    pieces: tuple[PhonologicalForm, ...]
    transition_raw_scores: array
    prior_alpha: list[float]
    alpha: list[float]
    singleton_scores: list[float]
    top_paths: list[tuple[_SharedInnerPath, ...]] | None
    forms: dict[str, _SharedFormScore]


def _estimated_form_bytes(form: PhonologicalForm) -> int:
    # This is a deliberately conservative logical-size bound, not an RSS claim.
    return 128 + 8 * len(form.symbols) + len(form.key.encode("utf-8"))


def _estimated_evaluation_bytes(evaluation: FormPieceEvaluation) -> int:
    return 192 + _estimated_form_bytes(evaluation.form) + sum(
        80 + _estimated_form_bytes(piece)
        for piece in evaluation.expected_piece_counts
    ) + sum(
        96 + sum(_estimated_form_bytes(piece) for piece in item.pieces)
        for item in evaluation.top_segmentations
    )


def _raw_prior_score(start: int, end: int, *, rho: float) -> float:
    return int(start > 0) * math.log(rho) + (end - start - 1) * math.log1p(
        -rho
    )


def _piece_ends(length: int, start: int, max_piece_length: int) -> tuple[int, ...]:
    ends = set(range(start + 1, min(length, start + max_piece_length) + 1))
    if start == 0:
        ends.add(length)
    return tuple(sorted(ends))


def _trim_composed_paths(
    paths: list[_ComposedPath],
    limit: int,
) -> list[_ComposedPath]:
    paths.sort(key=lambda path: (-path.score, *path.tie_key))
    return paths[:limit]


def _extend_token_path(
    prefix: _ComposedPath,
    span: LazyLexicalSpan,
    segmentation: PieceSegmentation,
    segmentation_key: tuple[str, ...],
) -> _ComposedPath:
    return _ComposedPath(
        score=prefix.score + segmentation.log_weight,
        words=prefix.words + (span.word,),
        piece_segmentations=(
            prefix.piece_segmentations + (segmentation.pieces,)
        ),
        rule_ids=prefix.rule_ids + span.rule_ids,
        boundaries=(
            prefix.boundaries
            + ((span.boundary,) if span.boundary is not None else ())
        ),
        tie_key=(
            prefix.tie_key[0] + (span.word.key,),
            prefix.tie_key[1] + (segmentation_key,),
            prefix.tie_key[2] + span.rule_ids,
        ),
    )


def _top_token_path_extensions(
    prefixes: list[_ComposedPath],
    span: LazyLexicalSpan,
    segmentations: tuple[
        tuple[PieceSegmentation, tuple[str, ...]], ...
    ],
    limit: int,
) -> list[_ComposedPath]:
    """Return the exact top-K Cartesian extensions without building K^2 rows.

    Each fixed-prefix row is already ordered by the same score/piece-key order
    as ``_trim_composed_paths``.  A heap merge therefore visits only row heads
    that can enter the global top-K.  Prefix/segmentation indices reproduce
    the former stable nested-loop order when complete keys tie.
    """

    if not prefixes or not segmentations:
        return []
    heap: list[
        tuple[
            tuple[object, ...],
            int,
            int,
            _ComposedPath,
        ]
    ] = []
    first_segmentation, first_key = segmentations[0]
    for prefix_index, prefix in enumerate(prefixes):
        path = _extend_token_path(
            prefix,
            span,
            first_segmentation,
            first_key,
        )
        heapq.heappush(
            heap,
            ((-path.score, *path.tie_key), prefix_index, 0, path),
        )

    result: list[_ComposedPath] = []
    while heap and len(result) < limit:
        _key, prefix_index, segmentation_index, path = heapq.heappop(heap)
        result.append(path)
        next_index = segmentation_index + 1
        if next_index >= len(segmentations):
            continue
        segmentation, segmentation_key = segmentations[next_index]
        next_path = _extend_token_path(
            prefixes[prefix_index],
            span,
            segmentation,
            segmentation_key,
        )
        heapq.heappush(
            heap,
            (
                (-next_path.score, *next_path.tie_key),
                prefix_index,
                next_index,
                next_path,
            ),
        )
    return result


class ComposedPieceInference:
    """One fixed-pass exact piece engine with bounded reusable state.

    The scorer and active piece parameters must remain immutable for the life
    of this object.  Create a fresh engine after every between-pass update.
    """

    def __init__(
        self,
        scorer: PieceScorer,
        *,
        model_config: PieceModelConfig = PieceModelConfig(),
        cache_config: ComposedCacheConfig = ComposedCacheConfig(),
        inspection_top_k: int | None = None,
    ) -> None:
        if inspection_top_k is not None and inspection_top_k < 1:
            raise ValueError("inspection_top_k must be >= 1 or None")
        self.scorer = scorer
        self.model_config = model_config
        self.cache_config = cache_config
        self.inspection_top_k = inspection_top_k
        self._piece_scores: OrderedDict[
            tuple[Phoneme, ...], tuple[PhonologicalForm, float, int]
        ] = OrderedDict()
        self._piece_score_bytes = 0
        self._forms: OrderedDict[
            str, tuple[FormPieceEvaluation, int]
        ] = OrderedDict()
        self._form_bytes = 0
        self._events: dict[str, int] = defaultdict(int)
        self._timings: dict[str, float] = defaultdict(float)
        self._initial_store_lookups = int(getattr(scorer, "store_lookups", 0))

    def _store_lookups(self) -> int:
        return max(
            0,
            int(getattr(self.scorer, "store_lookups", 0))
            - self._initial_store_lookups,
        )

    def counter_snapshot(self) -> ComposedInferenceCounters:
        payload = {name: self._events[name] for name in _EVENT_COUNTERS}
        payload["store_lookups"] = self._store_lookups()
        payload.update(
            {
                "piece_score_cache_entries": len(self._piece_scores),
                "piece_score_cache_estimated_bytes": self._piece_score_bytes,
                "form_cache_entries": len(self._forms),
                "form_cache_estimated_bytes": self._form_bytes,
            }
        )
        return ComposedInferenceCounters(**payload)

    def counter_delta(
        self,
        before: ComposedInferenceCounters,
    ) -> ComposedInferenceCounters:
        after = self.counter_snapshot()
        payload = {
            name: getattr(after, name) - getattr(before, name)
            for name in _EVENT_COUNTERS
        }
        payload.update(
            {
                "piece_score_cache_entries": after.piece_score_cache_entries,
                "piece_score_cache_estimated_bytes": (
                    after.piece_score_cache_estimated_bytes
                ),
                "form_cache_entries": after.form_cache_entries,
                "form_cache_estimated_bytes": after.form_cache_estimated_bytes,
            }
        )
        return ComposedInferenceCounters(**payload)

    def timing_snapshot(self) -> ComposedInferenceTimings:
        return ComposedInferenceTimings(
            **{name: self._timings[name] for name in _TIMING_COUNTERS}
        )

    def timing_delta(
        self,
        before: ComposedInferenceTimings,
    ) -> ComposedInferenceTimings:
        after = self.timing_snapshot()
        return ComposedInferenceTimings(
            **{
                name: getattr(after, name) - getattr(before, name)
                for name in _TIMING_COUNTERS
            }
        )

    def add_timing(self, name: str, started: float) -> None:
        if name not in _TIMING_COUNTERS:
            raise ValueError(f"unknown composed timing: {name}")
        self._timings[name] += time.perf_counter() - started

    def _piece_and_score(
        self,
        symbols: tuple[Phoneme, ...],
    ) -> tuple[PhonologicalForm, float]:
        self._events["piece_score_calls"] += 1
        cached = self._piece_scores.get(symbols)
        if cached is not None:
            self._events["piece_score_cache_hits"] += 1
            self._piece_scores.move_to_end(symbols)
            return cached[0], cached[1]
        self._events["piece_score_cache_misses"] += 1
        piece = PhonologicalForm(symbols)
        score = self.scorer.score(piece)
        size = 64 + _estimated_form_bytes(piece)
        if size > self.cache_config.piece_score_bytes:
            self._events["piece_score_cache_oversize"] += 1
            return piece, score
        while self._piece_scores and (
            len(self._piece_scores) >= self.cache_config.piece_score_entries
            or self._piece_score_bytes + size > self.cache_config.piece_score_bytes
        ):
            _old_symbols, (_old_piece, _old_score, old_size) = (
                self._piece_scores.popitem(last=False)
            )
            self._piece_score_bytes -= old_size
            self._events["piece_score_cache_evictions"] += 1
        self._piece_scores[symbols] = (piece, score, size)
        self._piece_score_bytes += size
        return piece, score

    def evaluate_form(self, form: PhonologicalForm) -> FormPieceEvaluation:
        """Evaluate the complete P0 support directly, with no P0 lattice."""

        form_key = form.key
        cached = self._forms.get(form_key)
        if cached is not None:
            self._events["form_cache_hits"] += 1
            self._forms.move_to_end(form_key)
            return cached[0]
        self._events["form_cache_misses"] += 1

        length = len(form.symbols)
        evaluation_started = time.perf_counter()
        self._events["composed_state_count"] += length + 1
        prior_alpha = [-math.inf] * (length + 1)
        alpha = [-math.inf] * (length + 1)
        prior_alpha[0] = 0.0
        alpha[0] = 0.0
        transition_count = 0
        transition_started = time.perf_counter()
        transitions_by_start: list[
            tuple[tuple[int, PhonologicalForm, float, float], ...]
        ] = []
        for start in range(length):
            transitions: list[tuple[int, PhonologicalForm, float, float]] = []
            for end in _piece_ends(
                length,
                start,
                self.model_config.max_piece_length,
            ):
                transition_count += 1
                prior = _raw_prior_score(start, end, rho=self.model_config.rho)
                piece, piece_score = self._piece_and_score(
                    form.symbols[start:end]
                )
                transitions.append((end, piece, prior, prior + piece_score))
            transitions_by_start.append(tuple(transitions))
        self.add_timing("inner_piece_transition_build_seconds", transition_started)

        started = time.perf_counter()
        for start in range(length):
            for end, _piece, prior, score in transitions_by_start[start]:
                prior_alpha[end] = logaddexp(
                    prior_alpha[end], prior_alpha[start] + prior
                )
                alpha[end] = logaddexp(alpha[end], alpha[start] + score)
        self.add_timing("inner_piece_forward_seconds", started)
        self._events["composed_transition_count"] += transition_count
        prior_log_z = prior_alpha[-1]
        raw_log_z = alpha[-1]
        if prior_log_z == -math.inf or raw_log_z == -math.inf:
            raise ValueError("Lexical form has no complete piece segmentation.")

        beta = [-math.inf] * (length + 1)
        beta[-1] = 0.0
        started = time.perf_counter()
        for start in range(length - 1, -1, -1):
            for end, _piece, _prior, score in transitions_by_start[start]:
                beta[start] = logaddexp(beta[start], score + beta[end])
        self.add_timing("inner_piece_backward_seconds", started)

        started = time.perf_counter()
        expected_counts: dict[PhonologicalForm, float] = defaultdict(float)
        expected_raw_score = 0.0
        whole_form_mass = 0.0
        for start in range(length):
            for end, piece, _prior, score in transitions_by_start[start]:
                posterior = math.exp(alpha[start] + score + beta[end] - raw_log_z)
                expected_counts[piece] += posterior
                expected_raw_score += posterior * score
                if start == 0 and end == length:
                    whole_form_mass = math.exp(score - raw_log_z)

        singleton_score = sum(
            transitions_by_start[start][0][3] for start in range(length)
        )
        singleton_path_mass = math.exp(singleton_score - raw_log_z)
        self.add_timing("inner_piece_posterior_seconds", started)
        top_segmentations: tuple[PieceSegmentation, ...] = ()
        if self.inspection_top_k is not None:
            started = time.perf_counter()
            paths: list[
                list[
                    tuple[
                        float,
                        tuple[PhonologicalForm, ...],
                        tuple[str, ...],
                    ]
                ]
            ] = [[] for _ in range(length + 1)]
            paths[0] = [(0.0, (), ())]
            for start in range(length):
                # Every transition moves right, so all paths into ``start``
                # are present before it is consumed.  Trim once here instead
                # of after every incoming edge; the unchanged key keeps the
                # same exact top-K.  Before trimming, a position has at most
                # (max_piece_length + 1) * K paths (including the whole-form
                # edge), independent of corpus size.
                prefixes = paths[start]
                prefixes.sort(key=lambda item: (-item[0], item[2]))
                del prefixes[self.inspection_top_k :]
                for end, piece, _prior, score in transitions_by_start[start]:
                    candidates = paths[end]
                    candidates.extend(
                        (
                            prefix_score + score,
                            prefix_pieces + (piece,),
                            prefix_keys + (piece.key,),
                        )
                        for prefix_score, prefix_pieces, prefix_keys in prefixes
                    )
            candidates = paths[-1]
            candidates.sort(key=lambda item: (-item[0], item[2]))
            del candidates[self.inspection_top_k :]
            top_segmentations = tuple(
                PieceSegmentation(
                    pieces=pieces,
                    log_weight=score - prior_log_z,
                    probability=math.exp(score - raw_log_z),
                )
                for score, pieces, _piece_keys in paths[-1]
            )
            self.add_timing("inner_piece_top_k_seconds", started)
        evaluation = FormPieceEvaluation(
            form=form,
            prior_log_normalizer=prior_log_z,
            log_score=raw_log_z - prior_log_z,
            expected_piece_counts=dict(expected_counts),
            expected_log_weight=expected_raw_score - prior_log_z,
            segmentation_entropy=max(0.0, raw_log_z - expected_raw_score),
            expected_piece_tokens=sum(expected_counts.values()),
            whole_form_mass=min(1.0, whole_form_mass),
            singleton_path_mass=min(1.0, singleton_path_mass),
            multi_piece_mass=max(0.0, 1.0 - whole_form_mass),
            top_segmentations=top_segmentations,
        )
        self.add_timing("inner_piece_evaluation_seconds", evaluation_started)

        size = _estimated_evaluation_bytes(evaluation)
        if size > self.cache_config.form_bytes:
            self._events["form_cache_oversize"] += 1
            return evaluation
        while self._forms and (
            len(self._forms) >= self.cache_config.form_entries
            or self._form_bytes + size > self.cache_config.form_bytes
        ):
            _old_form_key, (_old_evaluation, old_size) = self._forms.popitem(
                last=False
            )
            self._form_bytes -= old_size
            self._events["form_cache_evictions"] += 1
        self._forms[form_key] = (evaluation, size)
        self._form_bytes += size
        return evaluation

    def _compile_shared_form_topology(
        self,
        forms: tuple[PhonologicalForm, ...],
    ) -> CompiledSharedFormTopology | None:
        """Compile bounded score-free support for one token-local prefix DAG."""

        nodes = [
            _SharedPrefixNode(
                parent=-1,
                symbol=None,
                depth=0,
            )
        ]
        endpoints: list[int] = []
        for form in forms:
            current = 0
            for symbol in form.symbols:
                child = nodes[current].children.get(symbol)
                if child is None:
                    if len(nodes) >= self.cache_config.shared_prefix_nodes:
                        return None
                    child = len(nodes)
                    nodes[current].children[symbol] = child
                    nodes.append(
                        _SharedPrefixNode(
                            parent=current,
                            symbol=symbol,
                            depth=nodes[current].depth + 1,
                        )
                    )
                current = child
            endpoints.append(current)

        max_piece_length = self.model_config.max_piece_length
        piece_ids: dict[tuple[Phoneme, ...], int] = {}
        pieces: list[tuple[Phoneme, ...]] = []
        offsets = array("I", [0])
        sources = array("I")
        transition_piece_ids = array("I")
        for node_index in range(1, len(nodes)):
            node = nodes[node_index]
            cursor = node_index
            suffix_reversed: list[Phoneme] = []
            descending: list[tuple[int, int]] = []
            for _piece_length in range(
                1,
                min(node.depth, max_piece_length) + 1,
            ):
                symbol = nodes[cursor].symbol
                assert symbol is not None
                suffix_reversed.append(symbol)
                source = nodes[cursor].parent
                piece_symbols = tuple(reversed(suffix_reversed))
                piece_id = piece_ids.get(piece_symbols)
                if piece_id is None:
                    piece_id = len(pieces)
                    piece_ids[piece_symbols] = piece_id
                    pieces.append(piece_symbols)
                descending.append((source, piece_id))
                cursor = source
            # Existing per-form DP accumulates contributions by ascending
            # source position.  Preserve that deterministic order here.
            for source, piece_id in reversed(descending):
                sources.append(source)
                transition_piece_ids.append(piece_id)
            offsets.append(len(sources))

        whole_piece_ids = array("I")
        for form in forms:
            piece_id = piece_ids.get(form.symbols)
            if piece_id is None:
                piece_id = len(pieces)
                piece_ids[form.symbols] = piece_id
                pieces.append(form.symbols)
            whole_piece_ids.append(piece_id)
        return CompiledSharedFormTopology(
            max_piece_length=max_piece_length,
            parent=array("i", (node.parent for node in nodes)),
            depth=array("I", (node.depth for node in nodes)),
            transition_offsets=offsets,
            transition_sources=sources,
            transition_piece_ids=transition_piece_ids,
            pieces=tuple(pieces),
            form_keys=tuple(form.key for form in forms),
            endpoint_nodes=array("I", endpoints),
            whole_piece_ids=whole_piece_ids,
        )

    def _build_shared_form_batch(
        self,
        forms: tuple[PhonologicalForm, ...],
        *,
        topology: CompiledSharedFormTopology | None = None,
        topology_reused: bool = False,
    ) -> _SharedFormBatch | None:
        """Compile or exactly reweight one bounded shared prefix DAG."""

        evaluation_started = time.perf_counter()
        transition_started = time.perf_counter()
        if topology is None:
            compile_started = time.perf_counter()
            topology = self._compile_shared_form_topology(forms)
            self.add_timing(
                "inner_piece_topology_compile_seconds", compile_started
            )
            if topology is None:
                self._events["shared_batch_fallbacks"] += 1
                return None
            self._events["topology_compiles"] += 1
        elif topology_reused:
            self._events["topology_reuses"] += 1
        else:
            self._events["topology_compiles"] += 1
        if topology.max_piece_length != self.model_config.max_piece_length:
            raise ValueError("Compiled piece topology uses a different max length.")
        form_keys = tuple(form.key for form in forms)
        if topology.form_keys != form_keys:
            raise ValueError("Compiled piece topology does not match lexical forms.")
        if self.inspection_top_k is not None and (
            self.inspection_top_k * sum(topology.depth)
            > self.cache_config.shared_top_k_piece_references
        ):
            self._events["shared_batch_fallbacks"] += 1
            return None

        reweight_started = time.perf_counter()
        pieces_and_scores = tuple(
            self._piece_and_score(piece_symbols)
            for piece_symbols in topology.pieces
        )
        prior_by_shape = {
            (noninitial, length): (
                int(noninitial) * math.log(self.model_config.rho)
                + (length - 1) * math.log1p(-self.model_config.rho)
            )
            for noninitial in (False, True)
            for length in range(1, topology.max_piece_length + 1)
        }
        prior_alpha = [-math.inf] * len(topology.parent)
        alpha = [-math.inf] * len(topology.parent)
        singleton_scores = [-math.inf] * len(topology.parent)
        prior_alpha[0] = 0.0
        alpha[0] = 0.0
        singleton_scores[0] = 0.0
        transition_raw_scores = array("d")

        forward_started = time.perf_counter()
        for node_index in range(1, len(topology.parent)):
            node_prior_alpha = -math.inf
            node_alpha = -math.inf
            start = topology.transition_offsets[node_index - 1]
            end = topology.transition_offsets[node_index]
            for transition_index in range(start, end):
                source = topology.transition_sources[transition_index]
                prior = prior_by_shape[
                    (
                        source > 0,
                        topology.depth[node_index] - topology.depth[source],
                    )
                ]
                raw = (
                    prior
                    + pieces_and_scores[
                        topology.transition_piece_ids[transition_index]
                    ][1]
                )
                transition_raw_scores.append(raw)
                node_prior_alpha = logaddexp(
                    node_prior_alpha,
                    prior_alpha[source] + prior,
                )
                node_alpha = logaddexp(
                    node_alpha,
                    alpha[source] + raw,
                )
            prior_alpha[node_index] = node_prior_alpha
            alpha[node_index] = node_alpha
            singleton_index = end - 1
            assert (
                topology.transition_sources[singleton_index]
                == topology.parent[node_index]
            )
            singleton_scores[node_index] = (
                singleton_scores[topology.parent[node_index]]
                + transition_raw_scores[singleton_index]
            )
        self.add_timing("inner_piece_forward_seconds", forward_started)

        scores: dict[str, _SharedFormScore] = {}
        long_whole_count = 0
        for form_index, form in enumerate(forms):
            node_index = topology.endpoint_nodes[form_index]
            node_depth = topology.depth[node_index]
            whole_piece, piece_score = pieces_and_scores[
                topology.whole_piece_ids[form_index]
            ]
            whole_prior = _raw_prior_score(
                0,
                len(form.symbols),
                rho=self.model_config.rho,
            )
            if node_depth > topology.max_piece_length:
                whole_raw = whole_prior + piece_score
                prior_log_z = logaddexp(whole_prior, prior_alpha[node_index])
                raw_log_z = logaddexp(whole_raw, alpha[node_index])
                long_whole_count += 1
            else:
                whole_raw = whole_prior + piece_score
                prior_log_z = prior_alpha[node_index]
                raw_log_z = alpha[node_index]
            if prior_log_z == -math.inf or raw_log_z == -math.inf:
                raise ValueError("Lexical form has no complete piece segmentation.")
            scores[form.key] = _SharedFormScore(
                form=form,
                node=node_index,
                prior_log_normalizer=prior_log_z,
                raw_log_partition=raw_log_z,
                log_score=raw_log_z - prior_log_z,
                whole_piece=whole_piece,
                whole_raw_score=whole_raw,
                singleton_score=singleton_scores[node_index],
            )
        top_paths: list[tuple[_SharedInnerPath, ...]] | None = None
        if self.inspection_top_k is not None:
            top_k_started = time.perf_counter()
            top_paths = [() for _ in topology.parent]
            top_paths[0] = (_SharedInnerPath(0.0, (), ()),)
            for node_index in range(1, len(topology.parent)):
                candidates: list[_SharedInnerPath] = []
                for transition_index in range(
                    topology.transition_offsets[node_index - 1],
                    topology.transition_offsets[node_index],
                ):
                    source = topology.transition_sources[transition_index]
                    piece = pieces_and_scores[
                        topology.transition_piece_ids[transition_index]
                    ][0]
                    raw_score = transition_raw_scores[transition_index]
                    candidates.extend(
                        _SharedInnerPath(
                            score=prefix.score + raw_score,
                            pieces=prefix.pieces + (piece,),
                            piece_keys=prefix.piece_keys + (piece.key,),
                        )
                        for prefix in top_paths[source]
                    )
                candidates.sort(
                    key=lambda item: (-item.score, item.piece_keys)
                )
                top_paths[node_index] = tuple(
                    candidates[: self.inspection_top_k]
                )
            self._events["shared_top_k_states"] += len(topology.parent)
            self._events["shared_top_k_paths"] += sum(
                len(paths) for paths in top_paths
            )
            self.add_timing("inner_piece_top_k_seconds", top_k_started)
        self.add_timing("inner_piece_reweight_seconds", reweight_started)
        self.add_timing("inner_piece_transition_build_seconds", transition_started)
        self._events["composed_state_count"] += len(topology.parent)
        self._events["composed_transition_count"] += (
            len(topology.transition_sources) + long_whole_count
        )
        self._events["shared_prefix_nodes"] += len(topology.parent)
        self._events["shared_form_endpoints"] += len(scores)
        self.add_timing("inner_piece_evaluation_seconds", evaluation_started)
        return _SharedFormBatch(
            topology=topology,
            pieces=tuple(item[0] for item in pieces_and_scores),
            transition_raw_scores=transition_raw_scores,
            prior_alpha=prior_alpha,
            alpha=alpha,
            singleton_scores=singleton_scores,
            top_paths=top_paths,
            forms=scores,
        )

    def _aggregate_shared_piece_marginals(
        self,
        batch: _SharedFormBatch,
        endpoint_masses: dict[str, float],
    ) -> tuple[dict[PhonologicalForm, float], float]:
        """Reverse one shared DAG for posterior-weighted exact piece counts."""

        started = time.perf_counter()
        topology = batch.topology
        log_adjoint = [-math.inf] * len(topology.parent)
        piece_counts: dict[PhonologicalForm, float] = defaultdict(float)
        expected_raw_score = 0.0
        max_piece_length = self.model_config.max_piece_length
        for form_key, mass in endpoint_masses.items():
            if mass <= 0.0:
                continue
            score = batch.forms[form_key]
            seed = math.log(mass) - score.raw_log_partition
            log_adjoint[score.node] = logaddexp(
                log_adjoint[score.node],
                seed,
            )
            if len(score.form.symbols) > max_piece_length:
                contribution = math.exp(seed + score.whole_raw_score)
                piece_counts[score.whole_piece] += contribution
                expected_raw_score += contribution * score.whole_raw_score

        for node_index in range(len(topology.parent) - 1, 0, -1):
            adjoint = log_adjoint[node_index]
            if adjoint == -math.inf:
                continue
            for transition_index in range(
                topology.transition_offsets[node_index - 1],
                topology.transition_offsets[node_index],
            ):
                source = topology.transition_sources[transition_index]
                raw_score = batch.transition_raw_scores[transition_index]
                piece = batch.pieces[
                    topology.transition_piece_ids[transition_index]
                ]
                contribution = math.exp(
                    adjoint + batch.alpha[source] + raw_score
                )
                piece_counts[piece] += contribution
                expected_raw_score += contribution * raw_score
                log_adjoint[source] = logaddexp(
                    log_adjoint[source],
                    adjoint + raw_score,
                )
        self.add_timing("inner_piece_backward_seconds", started)
        self.add_timing("inner_piece_posterior_seconds", started)
        return dict(piece_counts), expected_raw_score

    def _shared_legal_pieces(
        self,
        batch: _SharedFormBatch,
        score: _SharedFormScore,
    ) -> tuple[PhonologicalForm, ...]:
        """Return deterministic positive-support pieces for one endpoint."""

        pieces: dict[str, PhonologicalForm] = {}
        topology = batch.topology
        cursor = score.node
        while cursor:
            for transition_index in range(
                topology.transition_offsets[cursor - 1],
                topology.transition_offsets[cursor],
            ):
                piece = batch.pieces[
                    topology.transition_piece_ids[transition_index]
                ]
                pieces.setdefault(piece.key, piece)
            cursor = topology.parent[cursor]
        pieces.setdefault(score.whole_piece.key, score.whole_piece)
        return tuple(pieces[key] for key in sorted(pieces))

    def _shared_top_segmentations(
        self,
        batch: _SharedFormBatch,
        score: _SharedFormScore,
    ) -> tuple[PieceSegmentation, ...]:
        """Derive the unchanged bounded top-K from shared transitions."""

        assert self.inspection_top_k is not None
        assert batch.top_paths is not None
        started = time.perf_counter()
        candidates = list(batch.top_paths[score.node])
        if len(score.form.symbols) > self.model_config.max_piece_length:
            candidates.append(
                _SharedInnerPath(
                    score=score.whole_raw_score,
                    pieces=(score.whole_piece,),
                    piece_keys=(score.whole_piece.key,),
                )
            )
        candidates.sort(key=lambda item: (-item.score, item.piece_keys))
        del candidates[self.inspection_top_k :]
        result = tuple(
            PieceSegmentation(
                pieces=path.pieces,
                log_weight=path.score - score.prior_log_normalizer,
                probability=math.exp(path.score - score.raw_log_partition),
            )
            for path in candidates
        )
        self.add_timing("inner_piece_top_k_seconds", started)
        return result

    def record_graph(self, graph: LazyCandidateGraph) -> None:
        self._events["candidate_factors"] += len(graph.factors)
        self._events["candidate_nodes"] += sum(
            len(factor.lattice.nodes)
            for factor in graph.factors
            if factor.lattice is not None
        )

    def record_lazy_span(self, *, hypothesis: bool) -> None:
        self._events["lazy_span_traversals"] += 1
        if hypothesis:
            self._events["candidate_span_hypotheses"] += 1

    def record_merged_form(self) -> None:
        self._events["merged_form_traversals"] += 1


def _evaluate_lazy_token_legacy(
    lattice: LazyTokenLattice,
    engine: ComposedPieceInference,
) -> _TokenSummary:
    node_count = len(lattice.nodes)
    alpha = [-math.inf] * node_count
    alpha[0] = 0.0
    started = time.perf_counter()
    for start in range(node_count - 1):
        if alpha[start] == -math.inf:
            continue
        for span in lattice.iter_spans_from(start):
            engine.record_lazy_span(hypothesis=True)
            evaluation = engine.evaluate_form(span.word)
            alpha[span.end] = logaddexp(
                alpha[span.end], alpha[start] + evaluation.log_score
            )
    engine.add_timing("lazy_token_forward_seconds", started)
    log_z = alpha[-1]
    if log_z == -math.inf:
        raise ValueError("Lazy token lattice has no complete lexical analysis.")

    beta = [-math.inf] * node_count
    beta[-1] = 0.0
    started = time.perf_counter()
    for start in range(node_count - 2, -1, -1):
        for span in lattice.iter_spans_from(start):
            engine.record_lazy_span(hypothesis=False)
            evaluation = engine.evaluate_form(span.word)
            beta[start] = logaddexp(
                beta[start], evaluation.log_score + beta[span.end]
            )
    engine.add_timing("lazy_token_backward_seconds", started)

    lexical_counts: dict[PhonologicalForm, float] = defaultdict(float)
    piece_counts: dict[PhonologicalForm, float] = defaultdict(float)
    boundary_mass: dict[str, float] = defaultdict(float)
    boundary_meta: dict[str, LexicalBoundary] = {}
    rule_usage: dict[str, float] = defaultdict(float)
    piece_occurrences: dict[
        PhonologicalForm, dict[str, float]
    ] = defaultdict(dict)
    expected_log_weight = 0.0
    expected_piece_tokens = 0.0
    piece_segmentation_entropy = 0.0
    expected_whole_form_uses = 0.0
    expected_singleton_path_uses = 0.0
    expected_multi_piece_uses = 0.0
    started = time.perf_counter()
    for start in range(node_count - 1):
        for span in lattice.iter_spans_from(start):
            engine.record_lazy_span(hypothesis=False)
            evaluation = engine.evaluate_form(span.word)
            mass = math.exp(
                alpha[span.start]
                + evaluation.log_score
                + beta[span.end]
                - log_z
            )
            lexical_counts[span.word] += mass
            expected_log_weight += mass * evaluation.expected_log_weight
            expected_piece_tokens += mass * evaluation.expected_piece_tokens
            piece_segmentation_entropy += mass * evaluation.segmentation_entropy
            expected_whole_form_uses += mass * evaluation.whole_form_mass
            expected_singleton_path_uses += mass * evaluation.singleton_path_mass
            expected_multi_piece_uses += mass * evaluation.multi_piece_mass
            if mass > 0.0:
                for piece, conditional_mass in evaluation.expected_piece_counts.items():
                    piece_counts[piece] += mass * conditional_mass
                    occurrence_id = (
                        f"{lattice.nodes[span.start].surface_end}:"
                        f"{lattice.nodes[span.end].surface_start}:{span.word.key}"
                    )
                    piece_occurrences[piece][occurrence_id] = max(
                        piece_occurrences[piece].get(occurrence_id, 0.0),
                        mass * conditional_mass,
                    )
            if span.boundary is not None:
                boundary_mass[span.boundary.boundary_id] += mass
                boundary_meta[span.boundary.boundary_id] = span.boundary
            for rule_id in span.rule_ids:
                rule_usage[rule_id] += mass / len(span.rule_ids)

    identity = lattice.span(0, node_count - 1)
    identity_log_score = -math.inf
    if identity is not None:
        engine.record_lazy_span(hypothesis=False)
        identity_log_score = engine.evaluate_form(identity.word).log_score
    engine.add_timing("lazy_token_posterior_seconds", started)

    top_paths: tuple[_ComposedPath, ...] = ()
    if engine.inspection_top_k is not None:
        started = time.perf_counter()
        paths: list[list[_ComposedPath]] = [[] for _ in range(node_count)]
        paths[0] = [_ComposedPath(0.0, (), (), (), (), ((), (), ()))]
        for start in range(node_count - 1):
            if not paths[start]:
                continue
            for span in lattice.iter_spans_from(start):
                engine.record_lazy_span(hypothesis=False)
                evaluation = engine.evaluate_form(span.word)
                candidates = paths[span.end]
                keyed_segmentations = tuple(
                    (
                        segmentation,
                        tuple(piece.key for piece in segmentation.pieces),
                    )
                    for segmentation in evaluation.top_segmentations
                )
                for prefix in paths[start]:
                    for segmentation, segmentation_key in keyed_segmentations:
                        candidates.append(
                            _ComposedPath(
                                score=prefix.score + segmentation.log_weight,
                                words=prefix.words + (span.word,),
                                piece_segmentations=(
                                    prefix.piece_segmentations
                                    + (segmentation.pieces,)
                                ),
                                rule_ids=prefix.rule_ids + span.rule_ids,
                                boundaries=(
                                    prefix.boundaries
                                    + (
                                        (span.boundary,)
                                        if span.boundary is not None
                                        else ()
                                    )
                                ),
                                tie_key=(
                                    prefix.tie_key[0] + (span.word.key,),
                                    prefix.tie_key[1] + (segmentation_key,),
                                    prefix.tie_key[2] + span.rule_ids,
                                ),
                            )
                        )
                paths[span.end] = _trim_composed_paths(
                    candidates,
                    engine.inspection_top_k,
                )
        top_paths = tuple(paths[-1])
        engine.add_timing("lazy_token_top_k_seconds", started)
    return _TokenSummary(
        log_partition=log_z,
        expected_log_weight=expected_log_weight,
        identity_log_score=identity_log_score,
        expected_piece_tokens=expected_piece_tokens,
        piece_segmentation_entropy=piece_segmentation_entropy,
        expected_whole_form_uses=expected_whole_form_uses,
        expected_singleton_path_uses=expected_singleton_path_uses,
        expected_multi_piece_uses=expected_multi_piece_uses,
        lexical_counts=dict(lexical_counts),
        piece_counts=dict(piece_counts),
        boundary_mass=dict(boundary_mass),
        boundary_meta=boundary_meta,
        rule_usage=dict(rule_usage),
        piece_occurrences={
            piece: dict(occurrences)
            for piece, occurrences in piece_occurrences.items()
        },
        top_paths=top_paths,
    )


def _evaluate_lazy_token_shared(
    lattice: LazyTokenLattice,
    engine: ComposedPieceInference,
    topology: CompiledSharedFormTopology | None = None,
    topology_reused: bool = False,
) -> _TokenSummary | None:
    """Exact training marginals through a bounded token-local prefix DAG."""

    node_count = len(lattice.nodes)
    spans_by_start: list[tuple[LazyLexicalSpan, ...]] = []
    unique_forms: dict[str, PhonologicalForm] = {}
    for start in range(node_count - 1):
        spans = tuple(lattice.iter_spans_from(start))
        spans_by_start.append(spans)
        for span in spans:
            unique_forms.setdefault(span.word.key, span.word)
    batch = engine._build_shared_form_batch(
        tuple(unique_forms.values()),
        topology=topology,
        topology_reused=topology_reused,
    )
    if batch is None:
        return None
    for spans in spans_by_start:
        for _span in spans:
            engine.record_lazy_span(hypothesis=True)

    alpha = [-math.inf] * node_count
    alpha[0] = 0.0
    started = time.perf_counter()
    for start, spans in enumerate(spans_by_start):
        if alpha[start] == -math.inf:
            continue
        for span in spans:
            score = batch.forms[span.word.key].log_score
            alpha[span.end] = logaddexp(
                alpha[span.end],
                alpha[start] + score,
            )
    engine.add_timing("lazy_token_forward_seconds", started)
    log_z = alpha[-1]
    if log_z == -math.inf:
        raise ValueError("Lazy token lattice has no complete lexical analysis.")

    beta = [-math.inf] * node_count
    beta[-1] = 0.0
    started = time.perf_counter()
    for start in range(node_count - 2, -1, -1):
        for span in spans_by_start[start]:
            score = batch.forms[span.word.key].log_score
            beta[start] = logaddexp(
                beta[start],
                score + beta[span.end],
            )
    engine.add_timing("lazy_token_backward_seconds", started)

    lexical_counts: dict[PhonologicalForm, float] = defaultdict(float)
    boundary_mass: dict[str, float] = defaultdict(float)
    boundary_meta: dict[str, LexicalBoundary] = {}
    rule_usage: dict[str, float] = defaultdict(float)
    endpoint_masses: dict[str, float] = defaultdict(float)
    form_occurrences: dict[str, set[str]] = defaultdict(set)
    expected_prior_log_z = 0.0
    mass_weighted_raw_log_z = 0.0
    expected_whole_form_uses = 0.0
    expected_singleton_path_uses = 0.0
    expected_multi_piece_uses = 0.0
    started = time.perf_counter()
    for start, spans in enumerate(spans_by_start):
        for span in spans:
            score = batch.forms[span.word.key]
            mass = math.exp(
                alpha[span.start]
                + score.log_score
                + beta[span.end]
                - log_z
            )
            lexical_counts[span.word] += mass
            endpoint_masses[span.word.key] += mass
            expected_prior_log_z += mass * score.prior_log_normalizer
            mass_weighted_raw_log_z += mass * score.raw_log_partition
            whole_mass = math.exp(
                score.whole_raw_score - score.raw_log_partition
            )
            singleton_mass = math.exp(
                score.singleton_score - score.raw_log_partition
            )
            expected_whole_form_uses += mass * whole_mass
            expected_singleton_path_uses += mass * singleton_mass
            expected_multi_piece_uses += mass * (1.0 - whole_mass)
            if mass > 0.0:
                form_occurrences[span.word.key].add(
                    f"{lattice.nodes[span.start].surface_end}:"
                    f"{lattice.nodes[span.end].surface_start}:{span.word.key}"
                )
            if span.boundary is not None:
                boundary_mass[span.boundary.boundary_id] += mass
                boundary_meta[span.boundary.boundary_id] = span.boundary
            for rule_id in span.rule_ids:
                rule_usage[rule_id] += mass / len(span.rule_ids)

    piece_counts, expected_raw_score = (
        engine._aggregate_shared_piece_marginals(batch, endpoint_masses)
    )
    piece_occurrences: dict[
        PhonologicalForm, dict[str, float]
    ] = defaultdict(dict)
    # The shared route is used only for support_epsilon == 0. Every legal
    # transition has finite weight, so structural membership is exactly the
    # positive-posterior support event; the numeric sentinel is never used as
    # an expected count.
    for form_key, occurrences in form_occurrences.items():
        for piece in engine._shared_legal_pieces(batch, batch.forms[form_key]):
            for occurrence_id in occurrences:
                piece_occurrences[piece][occurrence_id] = 1.0

    identity = lattice.span(0, node_count - 1)
    identity_log_score = -math.inf
    if identity is not None:
        identity_log_score = batch.forms[identity.word.key].log_score
    engine.add_timing("lazy_token_posterior_seconds", started)

    top_paths: tuple[_ComposedPath, ...] = ()
    if engine.inspection_top_k is not None:
        started = time.perf_counter()
        top_segmentations: dict[
            str,
            tuple[tuple[PieceSegmentation, tuple[str, ...]], ...],
        ] = {}
        paths: list[list[_ComposedPath]] = [[] for _ in range(node_count)]
        paths[0] = [_ComposedPath(0.0, (), (), (), (), ((), (), ()))]
        for start, spans in enumerate(spans_by_start):
            if not paths[start]:
                continue
            for span in spans:
                keyed_segmentations = top_segmentations.get(span.word.key)
                if keyed_segmentations is None:
                    segmentations = engine._shared_top_segmentations(
                        batch,
                        batch.forms[span.word.key],
                    )
                    keyed_segmentations = tuple(
                        (
                            segmentation,
                            tuple(
                                piece.key for piece in segmentation.pieces
                            ),
                        )
                        for segmentation in segmentations
                    )
                    top_segmentations[span.word.key] = keyed_segmentations
                candidates = paths[span.end]
                candidates.extend(
                    _top_token_path_extensions(
                        paths[start],
                        span,
                        keyed_segmentations,
                        engine.inspection_top_k,
                    )
                )
                paths[span.end] = _trim_composed_paths(
                    candidates,
                    engine.inspection_top_k,
                )
        top_paths = tuple(paths[-1])
        engine.add_timing("lazy_token_top_k_seconds", started)
    return _TokenSummary(
        log_partition=log_z,
        expected_log_weight=expected_raw_score - expected_prior_log_z,
        identity_log_score=identity_log_score,
        expected_piece_tokens=sum(piece_counts.values()),
        piece_segmentation_entropy=max(
            0.0,
            mass_weighted_raw_log_z - expected_raw_score,
        ),
        expected_whole_form_uses=expected_whole_form_uses,
        expected_singleton_path_uses=expected_singleton_path_uses,
        expected_multi_piece_uses=expected_multi_piece_uses,
        lexical_counts=dict(lexical_counts),
        piece_counts=piece_counts,
        boundary_mass=dict(boundary_mass),
        boundary_meta=boundary_meta,
        rule_usage=dict(rule_usage),
        piece_occurrences={
            piece: dict(occurrences)
            for piece, occurrences in piece_occurrences.items()
        },
        top_paths=top_paths,
    )


def _evaluate_lazy_token(
    lattice: LazyTokenLattice,
    engine: ComposedPieceInference,
    *,
    support_epsilon: float,
    topology: CompiledSharedFormTopology | None = None,
    topology_available: bool = False,
    topology_reused: bool = False,
) -> _TokenSummary:
    if (
        engine.cache_config.shared_token_marginals
        and support_epsilon == 0.0
    ):
        if topology_available and topology is None:
            engine._events["shared_batch_fallbacks"] += 1
            return _evaluate_lazy_token_legacy(lattice, engine)
        shared = _evaluate_lazy_token_shared(
            lattice,
            engine,
            topology,
            topology_reused,
        )
        if shared is not None:
            return shared
    return _evaluate_lazy_token_legacy(lattice, engine)


def _evaluate_factor(
    factor: LazySegmentFactor,
    engine: ComposedPieceInference,
    *,
    whitespace_merge_penalty: float,
    support_epsilon: float,
    topology: CompiledSharedFormTopology | None = None,
    topology_available: bool = False,
    topology_reused: bool = False,
) -> _FactorSummary:
    if factor.merged_word is not None:
        engine.record_merged_form()
        evaluation = engine.evaluate_form(factor.merged_word)
        penalty = whitespace_merge_penalty * factor.ignored_whitespace
        top_paths = tuple(
            _ComposedPath(
                score=segmentation.log_weight - penalty,
                words=(factor.merged_word,),
                piece_segmentations=(segmentation.pieces,),
                rule_ids=(),
                boundaries=(),
                tie_key=(
                    (factor.merged_word.key,),
                    (tuple(piece.key for piece in segmentation.pieces),),
                    (),
                ),
            )
            for segmentation in evaluation.top_segmentations
        )
        return _FactorSummary(
            factor=factor,
            log_score=evaluation.log_score - penalty,
            expected_log_weight=evaluation.expected_log_weight - penalty,
            identity_log_score=-math.inf,
            expected_piece_tokens=evaluation.expected_piece_tokens,
            piece_segmentation_entropy=evaluation.segmentation_entropy,
            expected_whole_form_uses=evaluation.whole_form_mass,
            expected_singleton_path_uses=evaluation.singleton_path_mass,
            expected_multi_piece_uses=evaluation.multi_piece_mass,
            lexical_counts={factor.merged_word: 1.0},
            piece_counts=evaluation.expected_piece_counts,
            boundary_mass={},
            boundary_meta={},
            rule_usage={},
            piece_occurrences={
                piece: {
                    f"merge:{factor.start_token}:{factor.end_token}:"
                    f"{factor.merged_word.key}": conditional_mass
                }
                for piece, conditional_mass in evaluation.expected_piece_counts.items()
                if conditional_mass > 0.0
            },
            top_paths=top_paths,
        )
    assert factor.lattice is not None
    token = _evaluate_lazy_token(
        factor.lattice,
        engine,
        support_epsilon=support_epsilon,
        topology=topology,
        topology_available=topology_available,
        topology_reused=topology_reused,
    )
    return _FactorSummary(
        factor=factor,
        log_score=token.log_partition,
        expected_log_weight=token.expected_log_weight,
        identity_log_score=(
            token.identity_log_score
            if not factor.incoming.transformed and not factor.outgoing.transformed
            else -math.inf
        ),
        expected_piece_tokens=token.expected_piece_tokens,
        piece_segmentation_entropy=token.piece_segmentation_entropy,
        expected_whole_form_uses=token.expected_whole_form_uses,
        expected_singleton_path_uses=token.expected_singleton_path_uses,
        expected_multi_piece_uses=token.expected_multi_piece_uses,
        lexical_counts=token.lexical_counts,
        piece_counts=token.piece_counts,
        boundary_mass=token.boundary_mass,
        boundary_meta=token.boundary_meta,
        rule_usage=token.rule_usage,
        piece_occurrences=token.piece_occurrences,
        top_paths=token.top_paths,
    )


def _outer_forward(
    graph: LazyCandidateGraph,
    evaluations: tuple[_FactorSummary, ...],
    *,
    identity_only: bool = False,
) -> tuple[dict[str, float], ...]:
    states: list[dict[str, float]] = [
        {} for _ in range(len(graph.segment.tokens) + 1)
    ]
    states[0]["START"] = 0.0
    by_start: dict[int, list[_FactorSummary]] = defaultdict(list)
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
                previous, prefix + score
            )
    return tuple(states)


def _outer_backward(
    graph: LazyCandidateGraph,
    evaluations: tuple[_FactorSummary, ...],
) -> tuple[dict[str, float], ...]:
    token_count = len(graph.segment.tokens)
    states: list[dict[str, float]] = [{} for _ in range(token_count + 1)]
    states[-1]["END"] = 0.0
    by_start: dict[int, list[_FactorSummary]] = defaultdict(list)
    for evaluation in evaluations:
        by_start[evaluation.factor.start_token].append(evaluation)
    for position in range(token_count - 1, -1, -1):
        for evaluation in by_start[position]:
            factor = evaluation.factor
            suffix = states[factor.end_token].get(factor.outgoing.key, -math.inf)
            if suffix == -math.inf:
                continue
            previous = states[position].get(factor.incoming.key, -math.inf)
            states[position][factor.incoming.key] = logaddexp(
                previous, evaluation.log_score + suffix
            )
    return tuple(states)


def _outer_top_paths(
    graph: LazyCandidateGraph,
    evaluations: tuple[_FactorSummary, ...],
    *,
    top_k: int,
) -> tuple[_ComposedPath, ...]:
    states: list[dict[str, list[_ComposedPath]]] = [
        {} for _ in range(len(graph.segment.tokens) + 1)
    ]
    states[0]["START"] = [_ComposedPath(0.0, (), (), (), (), ((), (), ()))]
    by_start: dict[int, list[_FactorSummary]] = defaultdict(list)
    for evaluation in evaluations:
        by_start[evaluation.factor.start_token].append(evaluation)
    for position in range(len(graph.segment.tokens)):
        for evaluation in by_start[position]:
            factor = evaluation.factor
            prefixes = states[position].get(factor.incoming.key, ())
            if not prefixes:
                continue
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
            candidates = states[factor.end_token].setdefault(
                factor.outgoing.key, []
            )
            for prefix in prefixes:
                for local in evaluation.top_paths:
                    candidates.append(
                        _ComposedPath(
                            score=prefix.score + local.score,
                            words=prefix.words + local.words,
                            piece_segmentations=(
                                prefix.piece_segmentations
                                + local.piece_segmentations
                            ),
                            rule_ids=(
                                prefix.rule_ids + local.rule_ids + outer_rules
                            ),
                            boundaries=(
                                prefix.boundaries
                                + local.boundaries
                                + visible_boundary
                            ),
                            tie_key=(
                                prefix.tie_key[0] + local.tie_key[0],
                                prefix.tie_key[1] + local.tie_key[1],
                                (
                                    prefix.tie_key[2]
                                    + local.tie_key[2]
                                    + outer_rules
                                ),
                            ),
                        )
                    )
            states[factor.end_token][factor.outgoing.key] = _trim_composed_paths(
                candidates,
                top_k,
            )
    return tuple(states[-1].get("END", ()))


def _add_scaled(
    target: dict[object, float],
    source: dict[object, float],
    scale: float,
) -> None:
    for key, value in source.items():
        target[key] += scale * value


def compile_composed_segment_topology(
    graph: LazyCandidateGraph,
    engine: ComposedPieceInference,
) -> CompiledSegmentTopology:
    """Compile only immutable factor-aligned piece support for one segment."""

    compiled: list[CompiledSharedFormTopology | None] = []
    for factor in graph.factors:
        if factor.lattice is None:
            compiled.append(None)
            continue
        unique_forms: dict[str, PhonologicalForm] = {}
        for span in factor.lattice.iter_spans():
            unique_forms.setdefault(span.word.key, span.word)
        compiled.append(
            engine._compile_shared_form_topology(tuple(unique_forms.values()))
        )
    return CompiledSegmentTopology(
        factor_ids=tuple(factor.factor_id for factor in graph.factors),
        factors=tuple(compiled),
    )


def infer_composed_segment(
    graph: LazyCandidateGraph,
    engine: ComposedPieceInference,
    *,
    whitespace_merge_penalty: float,
    support_epsilon: float = 0.0,
    topology: CompiledSegmentTopology | None = None,
) -> ComposedSegmentInference:
    """Marginalize lazy outer analyses and all inner piece paths exactly."""

    if whitespace_merge_penalty < 0.0:
        raise ValueError("whitespace_merge_penalty must be >= 0")
    if support_epsilon < 0.0:
        raise ValueError("support_epsilon must be >= 0")
    before = engine.counter_snapshot()
    timing_before = engine.timing_snapshot()
    engine.record_graph(graph)
    if topology is not None and topology.factor_ids != tuple(
        factor.factor_id for factor in graph.factors
    ):
        raise ValueError("Compiled segment topology does not match candidate factors.")
    factor_topologies = (
        topology.factors
        if topology is not None
        else (None,) * len(graph.factors)
    )
    started = time.perf_counter()
    evaluations = tuple(
        _evaluate_factor(
            factor,
            engine,
            whitespace_merge_penalty=whitespace_merge_penalty,
            support_epsilon=support_epsilon,
            topology=factor_topology,
            topology_available=topology is not None,
            topology_reused=topology.reused if topology is not None else False,
        )
        for factor, factor_topology in zip(graph.factors, factor_topologies)
    )
    engine.add_timing("piece_composition_seconds", started)
    started = time.perf_counter()
    forward = _outer_forward(graph, evaluations)
    engine.add_timing("outer_forward_seconds", started)
    log_z = forward[-1].get("END", -math.inf)
    if log_z == -math.inf:
        raise ValueError("Lazy candidate graph has no complete analysis.")
    started = time.perf_counter()
    backward = _outer_backward(graph, evaluations)
    engine.add_timing("outer_backward_seconds", started)

    lexical_counts: dict[PhonologicalForm, float] = defaultdict(float)
    piece_counts: dict[PhonologicalForm, float] = defaultdict(float)
    rule_usage: dict[str, float] = defaultdict(float)
    boundary_mass: dict[str, float] = defaultdict(float)
    boundary_meta: dict[str, LexicalBoundary] = {}
    piece_occurrences: dict[PhonologicalForm, set[str]] = defaultdict(set)
    expected_log_weight = 0.0
    expected_piece_tokens = 0.0
    piece_segmentation_entropy = 0.0
    expected_whole_form_uses = 0.0
    expected_singleton_path_uses = 0.0
    expected_multi_piece_uses = 0.0
    started = time.perf_counter()
    for evaluation in evaluations:
        factor = evaluation.factor
        prefix = forward[factor.start_token].get(factor.incoming.key, -math.inf)
        suffix = backward[factor.end_token].get(factor.outgoing.key, -math.inf)
        if prefix == -math.inf or suffix == -math.inf:
            continue
        factor_mass = math.exp(prefix + evaluation.log_score + suffix - log_z)
        expected_log_weight += factor_mass * evaluation.expected_log_weight
        expected_piece_tokens += factor_mass * evaluation.expected_piece_tokens
        piece_segmentation_entropy += (
            factor_mass * evaluation.piece_segmentation_entropy
        )
        expected_whole_form_uses += (
            factor_mass * evaluation.expected_whole_form_uses
        )
        expected_singleton_path_uses += (
            factor_mass * evaluation.expected_singleton_path_uses
        )
        expected_multi_piece_uses += (
            factor_mass * evaluation.expected_multi_piece_uses
        )
        _add_scaled(lexical_counts, evaluation.lexical_counts, factor_mass)
        _add_scaled(piece_counts, evaluation.piece_counts, factor_mass)
        _add_scaled(rule_usage, evaluation.rule_usage, factor_mass)
        _add_scaled(boundary_mass, evaluation.boundary_mass, factor_mass)
        boundary_meta.update(evaluation.boundary_meta)
        for piece, occurrences in evaluation.piece_occurrences.items():
            for occurrence_id, conditional_mass in occurrences.items():
                if factor_mass * conditional_mass > support_epsilon:
                    piece_occurrences[piece].add(
                        f"{factor.start_token}:{factor.end_token}:{occurrence_id}"
                    )

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
    engine.add_timing("outer_posterior_seconds", started)

    started = time.perf_counter()
    identity_forward = _outer_forward(graph, evaluations, identity_only=True)
    identity_log_z = identity_forward[-1].get("END", -math.inf)
    identity_mass = (
        0.0
        if identity_log_z == -math.inf
        else min(1.0, math.exp(identity_log_z - log_z))
    )
    posterior_mass = math.exp(
        forward[0]["START"] + backward[0]["START"] - log_z
    )
    engine.add_timing("outer_identity_seconds", started)
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
    top_k_started = (
        time.perf_counter() if engine.inspection_top_k is not None else 0.0
    )
    decoded = (
        ()
        if engine.inspection_top_k is None
        else _outer_top_paths(
            graph,
            evaluations,
            top_k=engine.inspection_top_k,
        )
    )
    if engine.inspection_top_k is not None:
        engine.add_timing("outer_top_k_seconds", top_k_started)
    analyses = tuple(
        ComposedAnalysisPosterior(
            words=path.words,
            piece_segmentations=path.piece_segmentations,
            probability=math.exp(path.score - log_z),
            log_score=path.score,
            rule_ids=path.rule_ids,
            boundaries=path.boundaries,
        )
        for path in decoded
    )
    return ComposedSegmentInference(
        log_partition=log_z,
        entropy=max(0.0, log_z - expected_log_weight),
        identity_mass=identity_mass,
        latent_mass=1.0 - identity_mass,
        expected_lexical_tokens=sum(lexical_counts.values()),
        expected_piece_tokens=expected_piece_tokens,
        piece_segmentation_entropy=piece_segmentation_entropy,
        expected_whole_form_uses=expected_whole_form_uses,
        expected_singleton_path_uses=expected_singleton_path_uses,
        expected_multi_piece_uses=expected_multi_piece_uses,
        lexical_expected_counts=dict(lexical_counts),
        piece_expected_counts=dict(piece_counts),
        rule_usage=dict(rule_usage),
        boundary_posteriors=boundaries,
        top_analyses=analyses,
        top_analysis_mass=sum(item.probability for item in analyses),
        piece_occurrence_support={
            piece: len(occurrences)
            for piece, occurrences in piece_occurrences.items()
        },
        total_posterior_mass=posterior_mass,
        counters=engine.counter_delta(before),
        timings=engine.timing_delta(timing_before),
    )
