"""Bounded audit of compile-once S1M2 piece-prefix topology.

This script reads a fixed leading slice of the frozen Devanagari benchmark
documents.  It does not train a model or write an artifact run.  The measured
prototype keeps immutable prefix/transition indices in compact arrays and
recomputes all scores and dynamic-programming state for every phase.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.lazy_candidates import build_lazy_candidate_graph
from sktlm.latent.phonology import Phoneme, PhonologicalForm
from sktlm.latent.training import TrainingConfig, _iter_document_segments, load_documents
from sktlm.pieces.composed import (
    CompiledSegmentTopology,
    ComposedPieceInference,
)
from sktlm.pieces.model import PieceModelConfig
from sktlm.pieces.topology_archive import (
    TopologyArchiveReader,
    TopologyArchiveWriter,
    archive_header,
)


BENCHMARK_DOCUMENTS = Path(
    "configs/benchmarks/s1m2_continuous_representative_documents.txt"
)
DEVANAGARI_MANIFEST = Path("data/manifests/representations.csv")
PHASE_COUNT = 4


class _MeasuredScorer:
    """Cheap deterministic stand-in for changed fixed-pass parameters."""

    def __init__(self, phase: int) -> None:
        self.phase = phase
        self.score_calls = 0
        self._ordinals = {
            symbol: index + 1 for index, symbol in enumerate(Phoneme)
        }

    def score(self, piece: PhonologicalForm) -> float:
        self.score_calls += 1
        ordinal_sum = sum(self._ordinals[symbol] for symbol in piece.symbols)
        return (
            -0.071 * len(piece.symbols)
            - 0.0003 * ordinal_sum
            + 0.013 * self.phase * int(len(piece.symbols) == 2)
        )


@dataclass(slots=True)
class _LegacyNode:
    parent: int
    symbol: Phoneme | None
    depth: int
    children: dict[Phoneme, int]
    transitions: tuple[tuple[int, PhonologicalForm, float, float], ...] = ()
    prior_alpha: float = -math.inf
    alpha: float = -math.inf


def _legacy_rebuild(
    forms: tuple[PhonologicalForm, ...],
    engine: ComposedPieceInference,
) -> dict[str, tuple[float, float]]:
    """Reproduce the pre-Opt16 object topology build and score traversal."""

    nodes = [_LegacyNode(-1, None, 0, {}, prior_alpha=0.0, alpha=0.0)]
    endpoints: dict[str, int] = {}
    for form in forms:
        current = 0
        for symbol in form.symbols:
            child = nodes[current].children.get(symbol)
            if child is None:
                child = len(nodes)
                nodes[current].children[symbol] = child
                nodes.append(_LegacyNode(current, symbol, nodes[current].depth + 1, {}))
            current = child
        endpoints[form.key] = current
    for node_index in range(1, len(nodes)):
        node = nodes[node_index]
        cursor = node_index
        suffix_reversed: list[Phoneme] = []
        descending: list[tuple[int, PhonologicalForm, float, float]] = []
        for _ in range(min(node.depth, engine.model_config.max_piece_length)):
            symbol = nodes[cursor].symbol
            assert symbol is not None
            suffix_reversed.append(symbol)
            source = nodes[cursor].parent
            piece, piece_score = engine._piece_and_score(
                tuple(reversed(suffix_reversed))
            )
            prior = (
                int(nodes[source].depth > 0) * math.log(engine.model_config.rho)
                + (node.depth - nodes[source].depth - 1)
                * math.log1p(-engine.model_config.rho)
            )
            descending.append((source, piece, prior, prior + piece_score))
            cursor = source
        node.transitions = tuple(reversed(descending))
    for node_index in range(1, len(nodes)):
        node = nodes[node_index]
        for source, _piece, prior, raw in node.transitions:
            node.prior_alpha = _logaddexp(
                node.prior_alpha, nodes[source].prior_alpha + prior
            )
            node.alpha = _logaddexp(node.alpha, nodes[source].alpha + raw)
    scores: dict[str, tuple[float, float]] = {}
    for form in forms:
        node = nodes[endpoints[form.key]]
        prior_log_z = node.prior_alpha
        raw_log_z = node.alpha
        if node.depth > engine.model_config.max_piece_length:
            _piece, piece_score = engine._piece_and_score(form.symbols)
            whole_prior = (node.depth - 1) * math.log1p(-engine.model_config.rho)
            prior_log_z = _logaddexp(whole_prior, prior_log_z)
            raw_log_z = _logaddexp(whole_prior + piece_score, raw_log_z)
        scores[form.key] = (prior_log_z, raw_log_z)
    return scores


def _logaddexp(left: float, right: float) -> float:
    if left == -math.inf:
        return right
    if right == -math.inf:
        return left
    largest = max(left, right)
    return largest + math.log(math.exp(left - largest) + math.exp(right - largest))


def _forms_by_lattice(
    repo_root: Path,
    *,
    max_lines_per_document: int,
) -> tuple[tuple[PhonologicalForm, ...], ...]:
    config = TrainingConfig(
        manifest=DEVANAGARI_MANIFEST,
        document_list=BENCHMARK_DOCUMENTS,
        model="reusable_pieces_v1",
        script="devanagari",
        condition="continuous",
        max_lines_per_document=max_lines_per_document,
    )
    documents = load_documents(
        repo_root / config.manifest,
        repo_root=repo_root,
        max_documents=None,
        document_list=repo_root / config.document_list,
        script=config.script,
        condition=config.condition,
    )
    grammar = StructuredSandhiGrammar.from_default_inventory()
    batches: list[tuple[PhonologicalForm, ...]] = []
    for document in documents:
        for _line_number, _segment_index, segment in _iter_document_segments(
            document, config
        ):
            graph = build_lazy_candidate_graph(
                segment,
                grammar,
                config.candidate_config,
            )
            for factor in graph.factors:
                if factor.lattice is None:
                    continue
                unique: dict[str, PhonologicalForm] = {}
                for span in factor.lattice.iter_spans():
                    unique.setdefault(span.word.key, span.word)
                batches.append(tuple(unique.values()))
    return tuple(batches)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-lines-per-document", type=int, default=16)
    args = parser.parse_args(argv)
    if args.max_lines_per_document < 1:
        raise ValueError("--max-lines-per-document must be >= 1")
    repo_root = Path(".").resolve()
    batches = _forms_by_lattice(
        repo_root,
        max_lines_per_document=args.max_lines_per_document,
    )
    config = PieceModelConfig()

    baseline_started = time.perf_counter()
    baseline_scores: list[list[dict[str, tuple[float, float]]]] = []
    baseline_piece_score_calls = 0
    baseline_piece_score_misses = 0
    for phase in range(PHASE_COUNT):
        engine = ComposedPieceInference(_MeasuredScorer(phase), model_config=config)
        phase_scores: list[dict[str, tuple[float, float]]] = []
        for forms in batches:
            phase_scores.append(_legacy_rebuild(forms, engine))
        baseline_scores.append(phase_scores)
        counters = engine.counter_snapshot()
        baseline_piece_score_calls += counters.piece_score_calls
        baseline_piece_score_misses += counters.piece_score_cache_misses
    baseline_seconds = time.perf_counter() - baseline_started

    compile_started = time.perf_counter()
    compile_engine = ComposedPieceInference(_MeasuredScorer(0), model_config=config)
    compiled = tuple(
        compile_engine._compile_shared_form_topology(forms) for forms in batches
    )
    assert all(item is not None for item in compiled)
    compile_seconds = time.perf_counter() - compile_started
    typed_compiled = tuple(item for item in compiled if item is not None)
    header = archive_header(
        config_signature="bounded-topology-audit",
        document_index=0,
        relative_path="bounded-devanagari-slice",
        freeze_id="frozen-m0",
    )
    with tempfile.TemporaryDirectory(prefix="sktlm-topology-audit-") as directory:
        archive_path = Path(directory) / "topology.bin"
        archive_started = time.perf_counter()
        with TopologyArchiveWriter(archive_path, header) as writer:
            for index, topology in enumerate(typed_compiled):
                writer.write(
                    index,
                    0,
                    CompiledSegmentTopology(
                        factor_ids=(f"factor:{index}",),
                        factors=(topology,),
                    ),
                )
        archive_write_seconds = time.perf_counter() - archive_started
        archive_bytes = archive_path.stat().st_size
        archive_uncompressed_bytes = writer.uncompressed_bytes
        decode_started = time.perf_counter()
        for _phase in range(PHASE_COUNT - 1):
            with TopologyArchiveReader(archive_path, header) as reader:
                for index in range(len(typed_compiled)):
                    reader.read(index, 0)
        three_phase_decode_seconds = time.perf_counter() - decode_started
    raw_array_bytes = sum(
        sum(
            len(item) * item.itemsize
            for item in (
                topology.parent,
                topology.depth,
                topology.transition_offsets,
                topology.transition_sources,
                topology.transition_piece_ids,
                topology.endpoint_nodes,
                topology.whole_piece_ids,
            )
        )
        + sum(len(piece) for piece in topology.pieces)
        + sum(len(key.encode("utf-8")) for key in topology.form_keys)
        for topology in typed_compiled
    )

    reweight_started = time.perf_counter()
    candidate_scores: list[list[dict[str, tuple[float, float]]]] = []
    candidate_piece_score_calls = 0
    candidate_piece_score_misses = 0
    for phase in range(PHASE_COUNT):
        engine = ComposedPieceInference(_MeasuredScorer(phase), model_config=config)
        phase_scores = []
        for forms, topology in zip(batches, typed_compiled):
            batch = engine._build_shared_form_batch(
                forms,
                topology=topology,
                topology_reused=phase > 0,
            )
            assert batch is not None
            phase_scores.append(
                {
                    key: (score.prior_log_normalizer, score.raw_log_partition)
                    for key, score in batch.forms.items()
                }
            )
        candidate_scores.append(phase_scores)
        counters = engine.counter_snapshot()
        candidate_piece_score_calls += counters.piece_score_calls
        candidate_piece_score_misses += counters.piece_score_cache_misses
    reweight_seconds = time.perf_counter() - reweight_started

    max_abs = 0.0
    compared = 0
    for baseline_phase, candidate_phase in zip(baseline_scores, candidate_scores):
        for baseline_batch, candidate_batch in zip(baseline_phase, candidate_phase):
            if baseline_batch.keys() != candidate_batch.keys():
                raise AssertionError("compiled form support changed")
            for key in baseline_batch:
                for baseline_value, candidate_value in zip(
                    baseline_batch[key], candidate_batch[key]
                ):
                    compared += 1
                    max_abs = max(max_abs, abs(baseline_value - candidate_value))
                    if not math.isclose(
                        baseline_value,
                        candidate_value,
                        rel_tol=1e-10,
                        abs_tol=1e-12,
                    ):
                        raise AssertionError(
                            f"compiled reweight mismatch for {key}: "
                            f"{baseline_value} != {candidate_value}"
                        )

    nodes = sum(len(item.parent) for item in typed_compiled)
    transitions = sum(len(item.transition_sources) for item in typed_compiled)
    forms = sum(len(item.form_keys) for item in typed_compiled)
    candidate_total = (
        compile_seconds
        + archive_write_seconds
        + three_phase_decode_seconds
        + reweight_seconds
    )
    reusable_phase_seconds = baseline_seconds / PHASE_COUNT
    projected_saved = baseline_seconds - candidate_total
    representative_transitions = 39_051_167
    full_corpus_multiplier = 101.23887973280279
    projected_compiled_bytes = int(
        archive_bytes
        / max(1, transitions)
        * representative_transitions
        * full_corpus_multiplier
    )
    opt15_transient_projection_bytes = int(229.8638374457302 * 1024**3)
    result = {
        "schema_version": "sktlm-s1m2-topology-audit/v1",
        "classification": "BOUNDED_TARGETED_MEASUREMENT_NOT_REPRESENTATIVE",
        "frontend": "devanagari",
        "documents": 3,
        "max_lines_per_document": args.max_lines_per_document,
        "phase_count": PHASE_COUNT,
        "lattice_batches": len(batches),
        "forms": forms,
        "prefix_nodes": nodes,
        "transitions": transitions,
        "baseline_rebuild_seconds": baseline_seconds,
        "baseline_mean_phase_seconds": reusable_phase_seconds,
        "baseline_piece_score_calls": baseline_piece_score_calls,
        "baseline_piece_score_cache_misses": baseline_piece_score_misses,
        "compile_once_seconds": compile_seconds,
        "archive_write_seconds": archive_write_seconds,
        "three_phase_decode_seconds": three_phase_decode_seconds,
        "four_reweights_seconds": reweight_seconds,
        "candidate_piece_score_calls": candidate_piece_score_calls,
        "candidate_piece_score_cache_misses": candidate_piece_score_misses,
        "compile_plus_four_reweights_seconds": candidate_total,
        "modeled_four_phase_reduction_percent": (
            100.0 * projected_saved / baseline_seconds
        ),
        "archive_uncompressed_bytes": archive_uncompressed_bytes,
        "compressed_archive_bytes": archive_bytes,
        "raw_array_and_piece_symbol_bytes": raw_array_bytes,
        "compressed_bytes_per_transition": archive_bytes / max(1, transitions),
        "projected_full_corpus_compiled_bytes": projected_compiled_bytes,
        "projected_full_corpus_compiled_gib": projected_compiled_bytes / 1024**3,
        "opt15_transient_projection_gib": 229.8638374457302,
        "opt15_plus_compiled_projection_gib": (
            opt15_transient_projection_bytes + projected_compiled_bytes
        )
        / 1024**3,
        "numeric_values_compared": compared,
        "max_absolute_difference": max_abs,
        "rtol": 1e-10,
        "atol": 1e-12,
        "exact_support": True,
        "mutable_scores_recomputed_each_phase": True,
        "prototype_archive_record_prefix_bytes": struct.calcsize("<I"),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
