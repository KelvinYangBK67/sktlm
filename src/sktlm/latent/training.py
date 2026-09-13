"""Streaming corpus training and research artifacts for latent lexicon v1."""

from __future__ import annotations

import csv
import hashlib
import heapq
import io
import json
import multiprocessing
import os
import shutil
import sqlite3
import subprocess
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from sktlm.latent.candidates import (
    CandidateBuildProfile,
    CandidateConfig,
    build_candidate_graph,
    candidate_graph_fingerprint,
    candidate_graph_statistics,
)
from sktlm.latent.frontend import ObservedSegment, iter_observed_segments
from sktlm.latent.execution_bundles import (
    ExecutionBundle,
    ExecutionBundlePlan,
    load_execution_bundle_plan,
)
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.inference import (
    AnalysisPosterior,
    BoundaryPosterior,
    NeutralFormScorer,
    SegmentInference,
    TrainingSegmentInference,
    infer_segment,
    infer_training_segment,
)
from sktlm.latent.phonology import PhonologicalForm
from sktlm.latent.store import LexiconScorer, LexiconStore, PieceStoreScorer
from sktlm.latent.telemetry import RuntimeTelemetry
from sktlm.latent.vocabulary import (
    BASE_UNIT_COUNT,
    RANKING_RULE,
    SELECTION_PASS,
    FrozenVocabulary,
)
from sktlm.latent.lazy_candidates import (
    build_lazy_candidate_graph,
    lazy_candidate_graph_statistics,
)
from sktlm.pieces.composed import (
    ComposedAnalysisPosterior,
    ComposedCacheConfig,
    ComposedInferenceCounters,
    ComposedInferenceTimings,
    ComposedPieceInference,
    ComposedSegmentInference,
    CompiledSegmentTopology,
    INSPECTION_RETENTION_FORMULA,
    compile_composed_segment_topology,
    infer_composed_segment,
)
from sktlm.pieces.model import PieceModelConfig
from sktlm.pieces.scorer import NeutralPieceScorer
from sktlm.pieces.topology_archive import (
    ReconstructibleTopologyArchiveReader,
    TopologyArchiveReader,
    TopologyArchiveWriter,
    archive_header,
)


EXPECTED_FREEZE_ID = "9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40"
IMPLEMENTATION = "latent-lexicon-v1"
S1M1_MODEL = "latent_lexicon_v1"
S1M2_MODEL = "reusable_pieces_v1"
COMPACT_EXACT_S1M2 = True
FORMAL_M0_SCRIPTS = frozenset({"iast", "devanagari"})
SUPPORTED_OBSERVATION_SCRIPTS = FORMAL_M0_SCRIPTS | {"iast_m0_prime"}
FORMAL_CONDITIONS = frozenset({"surface_word", "legacy_joined", "continuous"})

_WORKER_GRAMMAR: StructuredSandhiGrammar | None = None
_WORKER_SCORER: NeutralFormScorer | LexiconScorer | None = None
_WORKER_CONNECTION: sqlite3.Connection | None = None
_WORKER_VOCABULARY: FrozenVocabulary | None = None
_WORKER_PIECE_ENGINE: ComposedPieceInference | None = None


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    manifest: Path = Path("data/manifests/representations.csv")
    document_list: Path | None = None
    output_root: Path = Path("artifacts/latent_lexicon")
    run_id: str | None = None
    model: str = S1M1_MODEL
    script: str = "iast"
    condition: str = "surface_word"
    passes: int = 3
    vocab_budget: int | None = None
    workers: int = 1
    lexical_alpha: float = 0.1
    complexity_weight: float = 0.5
    complexity_tau: float = 1.0
    whitespace_merge_penalty: float = 8.0
    allow_whitespace_merge: bool = True
    max_internal_matches: int = 512
    max_segment_tokens: int = 128
    lexicon_cache_size: int = 100_000
    flush_types: int = 50_000
    analysis_top_k: int = 8
    usage_posterior_threshold: float = 0.01
    high_confidence_threshold: float = 0.8
    low_count_threshold: float = 1.0
    max_documents: int | None = None
    max_lines_per_document: int | None = None
    seed: int = 0
    equivalence_diagnostics: bool = False
    piece_max_length: int = 8
    piece_boundary_probability: float = 0.5
    piece_alpha: float = 0.1
    piece_complexity_weight: float = 0.5
    piece_complexity_kappa: float = 1.0
    piece_complexity_beta: float = 0.25
    piece_complexity_tau: float = 1.0
    piece_base_stop_probability: float = 0.5
    piece_min_reuse_occurrences: int = 2
    piece_support_epsilon: float = 0.0
    piece_score_cache_entries: int = 65_536
    piece_score_cache_bytes: int = 32 * 1024 * 1024
    piece_form_cache_entries: int = 8_192
    piece_form_cache_bytes: int = 256 * 1024 * 1024
    piece_shared_token_marginals: bool = True
    piece_shared_prefix_nodes: int = 262_144
    piece_shared_top_k_piece_references: int = 4_194_304
    inspection_retained_factor_bytes: int = 320 * 1024 * 1024
    execution_bundle_plan: Path | None = None
    resume: bool = False

    def __post_init__(self) -> None:
        if self.model not in {S1M1_MODEL, S1M2_MODEL}:
            raise ValueError(f"unsupported model: {self.model}")
        if self.script not in SUPPORTED_OBSERVATION_SCRIPTS:
            raise ValueError(f"unsupported formal script: {self.script}")
        if self.condition not in FORMAL_CONDITIONS:
            raise ValueError(f"unsupported formal condition: {self.condition}")
        if self.script == "iast_m0_prime" and self.condition != "continuous":
            raise ValueError("iast_m0_prime is defined only for continuous spacing")
        if self.passes < 1:
            raise ValueError("passes must be >= 1")
        if self.vocab_budget is not None and self.vocab_budget < BASE_UNIT_COUNT:
            raise ValueError(
                f"vocab_budget must be >= {BASE_UNIT_COUNT}; got {self.vocab_budget}"
            )
        if self.model == S1M2_MODEL and self.vocab_budget is not None:
            raise ValueError("vocab_budget is an S1M1-only comparison condition")
        if self.workers < 1:
            raise ValueError('workers must be >= 1')
        if self.execution_bundle_plan is not None and self.model != S1M2_MODEL:
            raise ValueError("execution_bundle_plan is supported only for S1M2")
        if self.execution_bundle_plan is not None and self.workers < 2:
            raise ValueError("execution_bundle_plan requires at least two workers")
        if self.lexical_alpha <= 0.0:
            raise ValueError("lexical_alpha must be > 0")
        if self.complexity_weight < 0.0:
            raise ValueError("complexity_weight must be >= 0")
        if self.complexity_tau <= 0.0:
            raise ValueError("complexity_tau must be > 0")
        if self.max_segment_tokens < 1:
            raise ValueError("max_segment_tokens must be >= 1")
        if self.lexicon_cache_size < 1 or self.flush_types < 1:
            raise ValueError("cache and flush bounds must be >= 1")
        if self.analysis_top_k < 1:
            raise ValueError("analysis_top_k must be >= 1")
        if not 0.0 <= self.high_confidence_threshold <= 1.0:
            raise ValueError("high_confidence_threshold must be in [0, 1]")
        PieceModelConfig(
            max_piece_length=self.piece_max_length,
            rho=self.piece_boundary_probability,
            alpha=self.piece_alpha,
            lambda_=self.piece_complexity_weight,
            kappa=self.piece_complexity_kappa,
            beta=self.piece_complexity_beta,
            tau=self.piece_complexity_tau,
            top_k=self.analysis_top_k,
        )
        if not 0.0 < self.piece_base_stop_probability < 1.0:
            raise ValueError(
                "piece_base_stop_probability must be strictly between 0 and 1"
            )
        if self.piece_min_reuse_occurrences < 2:
            raise ValueError("piece_min_reuse_occurrences must be >= 2")
        if self.piece_support_epsilon < 0.0:
            raise ValueError("piece_support_epsilon must be >= 0")
        ComposedCacheConfig(
            piece_score_entries=self.piece_score_cache_entries,
            piece_score_bytes=self.piece_score_cache_bytes,
            form_entries=self.piece_form_cache_entries,
            form_bytes=self.piece_form_cache_bytes,
            shared_token_marginals=self.piece_shared_token_marginals,
            shared_prefix_nodes=self.piece_shared_prefix_nodes,
            shared_top_k_piece_references=(
                self.piece_shared_top_k_piece_references
            ),
            inspection_retained_factor_bytes=(
                self.inspection_retained_factor_bytes
            ),
        )

    def payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["manifest"] = self.manifest.as_posix()
        payload["document_list"] = (
            None if self.document_list is None else self.document_list.as_posix()
        )
        payload["output_root"] = self.output_root.as_posix()
        payload.pop("resume")
        # Inspection admission is execution-only.  Changing its memory/runtime
        # tradeoff must not invalidate or rename an existing learned state.
        payload.pop("inspection_retained_factor_bytes")
        payload.pop("execution_bundle_plan")
        if self.vocab_budget is None:
            payload.pop("vocab_budget")
        if self.model == S1M1_MODEL:
            # Preserve the frozen S1M1 configuration identity.  S1M2-only
            # fields must not invalidate an existing S1M1 checkpoint merely
            # because this trainer learned how to run another model.
            payload.pop("model")
            for name in (
                "piece_max_length",
                "piece_boundary_probability",
                "piece_alpha",
                "piece_complexity_weight",
                "piece_complexity_kappa",
                "piece_complexity_beta",
                "piece_complexity_tau",
                "piece_base_stop_probability",
                "piece_min_reuse_occurrences",
                "piece_support_epsilon",
                "piece_score_cache_entries",
                "piece_score_cache_bytes",
                "piece_form_cache_entries",
                "piece_form_cache_bytes",
                "piece_shared_token_marginals",
                "piece_shared_prefix_nodes",
                "piece_shared_top_k_piece_references",
            ):
                payload.pop(name)
        return payload

    @property
    def candidate_config(self) -> CandidateConfig:
        return CandidateConfig(
            max_internal_matches=self.max_internal_matches,
            allow_whitespace_merge=self.allow_whitespace_merge,
            whitespace_merge_penalty=self.whitespace_merge_penalty,
        )

    @property
    def piece_model_config(self) -> PieceModelConfig:
        return PieceModelConfig(
            max_piece_length=self.piece_max_length,
            rho=self.piece_boundary_probability,
            alpha=self.piece_alpha,
            lambda_=self.piece_complexity_weight,
            kappa=self.piece_complexity_kappa,
            beta=self.piece_complexity_beta,
            tau=self.piece_complexity_tau,
            top_k=self.analysis_top_k,
        )

    @property
    def piece_cache_config(self) -> ComposedCacheConfig:
        return ComposedCacheConfig(
            piece_score_entries=self.piece_score_cache_entries,
            piece_score_bytes=self.piece_score_cache_bytes,
            form_entries=self.piece_form_cache_entries,
            form_bytes=self.piece_form_cache_bytes,
            shared_token_marginals=self.piece_shared_token_marginals,
            shared_prefix_nodes=self.piece_shared_prefix_nodes,
            shared_top_k_piece_references=(
                self.piece_shared_top_k_piece_references
            ),
            inspection_retained_factor_bytes=(
                self.inspection_retained_factor_bytes
            ),
        )


@dataclass(frozen=True, slots=True)
class CorpusDocument:
    relative_path: str
    path: Path
    document_id: str
    freeze_id: str


@dataclass(slots=True)
class PassMetrics:
    documents: int = 0
    lines: int = 0
    segments: int = 0
    characters: int = 0
    log_partition: float = 0.0
    identity_mass_sum: float = 0.0
    latent_mass_sum: float = 0.0
    expected_lexical_tokens: float = 0.0
    expected_piece_tokens: float = 0.0
    piece_segmentation_entropy: float = 0.0
    expected_whole_form_uses: float = 0.0
    expected_singleton_path_uses: float = 0.0
    expected_multi_piece_uses: float = 0.0
    overflowed_tokens: int = 0
    candidate_factors: int = 0
    candidate_nodes: int = 0
    candidate_edges: int = 0
    lazy_span_traversals: int = 0
    composed_states: int = 0
    composed_transitions: int = 0
    piece_score_calls: int = 0
    piece_score_cache_hits: int = 0
    piece_score_cache_misses: int = 0
    form_cache_hits: int = 0
    form_cache_misses: int = 0
    piece_store_lookups: int = 0

    def update(
        self,
        segment: ObservedSegment,
        inference: SegmentInference | TrainingSegmentInference | ComposedSegmentInference,
        *,
        overflowed_tokens: int,
        candidate_factors: int,
        candidate_nodes: int,
        candidate_edges: int,
    ) -> None:
        self.segments += 1
        self.characters += len(segment.written)
        self.log_partition += inference.log_partition
        self.identity_mass_sum += inference.identity_mass
        self.latent_mass_sum += inference.latent_mass
        self.expected_lexical_tokens += inference.expected_lexical_tokens
        counters = getattr(inference, "counters", None)
        if isinstance(inference, ComposedSegmentInference):
            self.expected_piece_tokens += inference.expected_piece_tokens
            self.piece_segmentation_entropy += (
                inference.piece_segmentation_entropy
            )
            self.expected_whole_form_uses += inference.expected_whole_form_uses
            self.expected_singleton_path_uses += (
                inference.expected_singleton_path_uses
            )
            self.expected_multi_piece_uses += inference.expected_multi_piece_uses
        if counters is not None:
            self.lazy_span_traversals += counters.lazy_span_traversals
            self.composed_states += counters.composed_state_count
            self.composed_transitions += counters.composed_transition_count
            self.piece_score_calls += counters.piece_score_calls
            self.piece_score_cache_hits += counters.piece_score_cache_hits
            self.piece_score_cache_misses += counters.piece_score_cache_misses
            self.form_cache_hits += counters.form_cache_hits
            self.form_cache_misses += counters.form_cache_misses
            self.piece_store_lookups += counters.store_lookups
        self.overflowed_tokens += overflowed_tokens
        self.candidate_factors += candidate_factors
        self.candidate_nodes += candidate_nodes
        self.candidate_edges += candidate_edges

    def summary(self, pass_index: int) -> dict[str, Any]:
        denominator = max(1, self.segments)
        return {
            "pass": pass_index,
            "documents": self.documents,
            "lines": self.lines,
            "segments": self.segments,
            "characters": self.characters,
            "log_partition": self.log_partition,
            "mean_identity_mass": self.identity_mass_sum / denominator,
            "mean_latent_mass": self.latent_mass_sum / denominator,
            "expected_lexical_tokens": self.expected_lexical_tokens,
            "expected_piece_tokens": self.expected_piece_tokens,
            "piece_segmentation_entropy": self.piece_segmentation_entropy,
            "expected_whole_form_uses": self.expected_whole_form_uses,
            "expected_singleton_path_uses": self.expected_singleton_path_uses,
            "expected_multi_piece_uses": self.expected_multi_piece_uses,
            "overflowed_tokens": self.overflowed_tokens,
            "candidate_factors": self.candidate_factors,
            "candidate_nodes": self.candidate_nodes,
            "candidate_edges": self.candidate_edges,
            "lazy_span_traversals": self.lazy_span_traversals,
        }

    def merged(self, other: PassMetrics) -> PassMetrics:
        return PassMetrics(
            documents=self.documents + other.documents,
            lines=self.lines + other.lines,
            segments=self.segments + other.segments,
            characters=self.characters + other.characters,
            log_partition=self.log_partition + other.log_partition,
            identity_mass_sum=self.identity_mass_sum + other.identity_mass_sum,
            latent_mass_sum=self.latent_mass_sum + other.latent_mass_sum,
            expected_lexical_tokens=(
                self.expected_lexical_tokens + other.expected_lexical_tokens
            ),
            expected_piece_tokens=(
                self.expected_piece_tokens + other.expected_piece_tokens
            ),
            piece_segmentation_entropy=(
                self.piece_segmentation_entropy
                + other.piece_segmentation_entropy
            ),
            expected_whole_form_uses=(
                self.expected_whole_form_uses + other.expected_whole_form_uses
            ),
            expected_singleton_path_uses=(
                self.expected_singleton_path_uses
                + other.expected_singleton_path_uses
            ),
            expected_multi_piece_uses=(
                self.expected_multi_piece_uses + other.expected_multi_piece_uses
            ),
            overflowed_tokens=self.overflowed_tokens + other.overflowed_tokens,
            candidate_factors=self.candidate_factors + other.candidate_factors,
            candidate_nodes=self.candidate_nodes + other.candidate_nodes,
            candidate_edges=self.candidate_edges + other.candidate_edges,
            lazy_span_traversals=(
                self.lazy_span_traversals + other.lazy_span_traversals
            ),
            composed_states=self.composed_states + other.composed_states,
            composed_transitions=(
                self.composed_transitions + other.composed_transitions
            ),
            piece_score_calls=self.piece_score_calls + other.piece_score_calls,
            piece_score_cache_hits=(
                self.piece_score_cache_hits + other.piece_score_cache_hits
            ),
            piece_score_cache_misses=(
                self.piece_score_cache_misses + other.piece_score_cache_misses
            ),
            form_cache_hits=self.form_cache_hits + other.form_cache_hits,
            form_cache_misses=self.form_cache_misses + other.form_cache_misses,
            piece_store_lookups=(
                self.piece_store_lookups + other.piece_store_lookups
            ),
        )


def _record_composed_telemetry(
    telemetry: RuntimeTelemetry,
    counters: ComposedInferenceCounters,
    *,
    phase: str,
    timings: ComposedInferenceTimings | None = None,
) -> None:
    gauges = {
        "piece_score_cache_entries",
        "piece_score_cache_estimated_bytes",
        "form_cache_entries",
        "form_cache_estimated_bytes",
        "retained_budget_peak_bytes",
    }
    for name, value in asdict(counters).items():
        label = f"{phase}_{name}"
        if name in gauges:
            telemetry.maximum(label, int(value))
        else:
            telemetry.increment(label, int(value))
    if timings is not None:
        _record_composed_timings(telemetry, timings, phase=phase)


def _record_composed_timings(
    telemetry: RuntimeTelemetry,
    timings: ComposedInferenceTimings,
    *,
    phase: str,
) -> None:
    for name, value in asdict(timings).items():
        telemetry.add_seconds(f"{phase}_{name}", float(value))


def _existing_path_bytes(paths: Iterable[Path]) -> int:
    return sum(path.stat().st_size for path in paths if path.is_file())


def _record_store_storage(
    telemetry: RuntimeTelemetry,
    database_path: Path,
) -> None:
    paths = {
        "sqlite_database_bytes": database_path,
        "sqlite_wal_bytes": Path(f"{database_path}-wal"),
        "sqlite_shm_bytes": Path(f"{database_path}-shm"),
    }
    total = 0
    for label, path in paths.items():
        size = path.stat().st_size if path.is_file() else 0
        telemetry.maximum(label, size)
        total += size
    telemetry.maximum("sqlite_total_bytes", total)


def _record_run_storage(
    telemetry: RuntimeTelemetry,
    run_dir: Path,
) -> None:
    telemetry.maximum(
        "artifact_transient_bytes",
        _existing_path_bytes(run_dir.rglob("*")),
    )


def _observe_segment_telemetry(
    telemetry: RuntimeTelemetry,
    segment: ObservedSegment,
    config: TrainingConfig,
    *,
    phase: str,
) -> None:
    phonemes = sum(len(token.phonemes) for token in segment.tokens)
    telemetry.observe(f"{phase}_segment_written_characters", len(segment.written))
    telemetry.observe(f"{phase}_segment_phonemes", phonemes)
    telemetry.observe(f"{phase}_observed_tokens", len(segment.tokens))
    if config.condition == "continuous":
        telemetry.observe(f"{phase}_continuous_span_phonemes", phonemes)
    for token in segment.tokens:
        telemetry.observe(f"{phase}_token_written_characters", len(token.written))
        telemetry.observe(f"{phase}_token_phonemes", len(token.phonemes))


def _record_candidate_telemetry(
    telemetry: RuntimeTelemetry,
    profile: CandidateBuildProfile,
    statistics: dict[str, int],
    *,
    phase: str,
) -> None:
    for name in (
        "visible_boundary_seconds",
        "grammar_match_seconds",
        "window_filter_seconds",
        "node_construction_seconds",
        "lattice_validation_seconds",
        "factor_construction_seconds",
    ):
        telemetry.add_seconds(f"{phase}_{name}", float(getattr(profile, name)))
    for name in (
        "internal_match_calls",
        "unfiltered_internal_matches",
        "factor_combinations_attempted",
    ):
        telemetry.increment(f"{phase}_{name}", int(getattr(profile, name)))
    for name in (
        "boundary_options",
        "factors",
        "merged_factors",
        "token_lattices",
        "raw_internal_matches",
        "retained_internal_matches",
        "lattice_nodes",
        "lexical_span_hypotheses",
        "overflowed_tokens",
    ):
        telemetry.observe(f"{phase}_{name}_per_segment", int(statistics[name]))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _config_signature(config: TrainingConfig) -> str:
    return _sha256_bytes(_canonical_json(config.payload()).encode("utf-8"))


def _run_id(config: TrainingConfig) -> str:
    return (
        config.run_id
        or f"m0_{config.script}_{config.condition}_{_config_signature(config)[:12]}"
    )


def _replace_file(source: Path, target: Path) -> None:
    delays = (0.02, 0.04, 0.08, 0.16, 0.32)
    for attempt, delay in enumerate(delays):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt + 1 == len(delays):
                raise
            time.sleep(delay)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    _replace_file(temporary, path)


def _pending_vocabulary_payload(budget: int) -> dict[str, object]:
    return {
        "status": "pending_pass_1_selection",
        "total_budget": budget,
        "base_unit_count": BASE_UNIT_COUNT,
        "learned_lexical_capacity": budget - BASE_UNIT_COUNT,
        "selection_pass": SELECTION_PASS,
        "ranking_rule": RANKING_RULE,
        "identity_semantics": "one distinct latent form_key is one vocabulary item",
        "surface_realizations_consume_slots": False,
        "oov_projection": "constituent phonological base-unit tokens",
    }


def _vocabulary_tsv(vocabulary: FrozenVocabulary) -> str:
    handle = io.StringIO(newline="")
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(
        (
            "rank",
            "kind",
            "form_key",
            "latent_form",
            "phoneme_ids",
            "pass1_expected_count",
        )
    )
    for entry in vocabulary.entries:
        writer.writerow(
            (
                entry.rank,
                entry.kind,
                entry.form.key,
                entry.form.iast,
                " ".join(entry.form.phoneme_ids),
                repr(entry.pass1_expected_count),
            )
        )
    return handle.getvalue()


def _write_or_verify_text(path: Path, content: str) -> None:
    if path.is_file():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Frozen vocabulary artifact changed: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="")
    _replace_file(temporary, path)


def _materialize_vocabulary_artifacts(
    run_dir: Path,
    vocabulary: FrozenVocabulary,
) -> None:
    budget_path = run_dir / "vocabulary_budget.json"
    expected_budget = vocabulary.artifact_payload()
    if budget_path.is_file():
        if json.loads(budget_path.read_text(encoding="utf-8")) != expected_budget:
            raise RuntimeError(
                f"Frozen vocabulary metadata changed: {budget_path}"
            )
    else:
        _write_json(budget_path, expected_budget)
    _write_or_verify_text(run_dir / "vocabulary.tsv", _vocabulary_tsv(vocabulary))

    provenance_path = run_dir / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["vocabulary_budget"] = vocabulary.checkpoint_payload()
    _write_json(provenance_path, provenance)


def _git_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def load_documents(
    manifest: Path,
    *,
    repo_root: Path,
    max_documents: int | None,
    document_list: Path | None = None,
    script: str = "iast",
    condition: str = "surface_word",
) -> tuple[CorpusDocument, ...]:
    if script not in SUPPORTED_OBSERVATION_SCRIPTS:
        raise ValueError(f"unsupported formal script: {script}")
    if condition not in FORMAL_CONDITIONS:
        raise ValueError(f"unsupported formal condition: {condition}")
    if script == "iast_m0_prime" and condition != "continuous":
        raise ValueError("iast_m0_prime is defined only for continuous spacing")
    with manifest.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("script") == script
            and row.get("condition") == condition
        ]
    if not rows:
        raise ValueError(f"Manifest has no {script} + {condition} rows.")
    freeze_ids = {row["freeze_id"] for row in rows}
    if freeze_ids != {EXPECTED_FREEZE_ID}:
        raise ValueError(f"Unexpected or mixed M0 freeze IDs: {sorted(freeze_ids)}")
    rows.sort(key=lambda row: row["relative_path"])
    if document_list is not None:
        requested = [
            line.strip()
            for line in document_list.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if len(requested) != len(set(requested)):
            raise ValueError(f"Document list contains duplicates: {document_list}")
        by_path = {row["relative_path"]: row for row in rows}
        missing = [relative_path for relative_path in requested if relative_path not in by_path]
        if missing:
            raise ValueError(
                f"Document list contains paths absent from the condition: {missing}"
            )
        rows = [by_path[relative_path] for relative_path in requested]
    if max_documents is not None:
        rows = rows[:max_documents]
    documents: list[CorpusDocument] = []
    for row in rows:
        path = Path(row["representation_path"])
        if not path.is_absolute():
            path = repo_root / path
        if not path.is_file():
            raise FileNotFoundError(path)
        documents.append(
            CorpusDocument(
                relative_path=row["relative_path"],
                path=path,
                document_id=row["relative_path"].replace("/", ":"),
                freeze_id=row["freeze_id"],
            )
        )
    return tuple(documents)


def _iter_document_segments(
    document: CorpusDocument,
    config: TrainingConfig,
) -> Iterator[tuple[int, int, ObservedSegment]]:
    with document.path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if (
                config.max_lines_per_document is not None
                and line_number > config.max_lines_per_document
            ):
                break
            if not line.strip():
                continue
            for segment_index, segment in enumerate(
                iter_observed_segments(
                    line.rstrip("\r\n"),
                    max_tokens=config.max_segment_tokens,
                    script=config.script,
                )
            ):
                yield line_number, segment_index, segment


def _profiled_document_segments(
    document: CorpusDocument,
    config: TrainingConfig,
    telemetry: RuntimeTelemetry,
    *,
    phase: str,
) -> Iterator[tuple[int, int, ObservedSegment]]:
    iterator = _iter_document_segments(document, config)
    while True:
        started = telemetry.now()
        try:
            item = next(iterator)
        except StopIteration:
            telemetry.elapsed(f'{phase}_frontend_io', started)
            return
        telemetry.elapsed(f'{phase}_frontend_io', started)
        _observe_segment_telemetry(
            telemetry,
            item[2],
            config,
            phase=phase,
        )
        yield item


def _flush_counts(
    store: LexiconStore,
    counts: Counter[PhonologicalForm],
    *,
    table: str = "counts_next",
    document_transaction: bool = False,
) -> None:
    if counts:
        if document_transaction:
            if table != "counts_next":
                raise ValueError("Document-atomic writes are only valid for counts_next.")
            store.add_document_counts(counts.items())
        else:
            store.add_counts(counts.items(), table=table)
        counts.clear()


def _checkpoint_path(run_dir: Path) -> Path:
    return run_dir / "checkpoint.json"


def _load_checkpoint(run_dir: Path) -> dict[str, Any]:
    path = _checkpoint_path(run_dir)
    if not path.is_file():
        return {
            "completed_passes": 0,
            "active_pass": None,
            "next_document_index": 0,
            "history": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _save_checkpoint(run_dir: Path, checkpoint: dict[str, Any]) -> None:
    _write_json(_checkpoint_path(run_dir), checkpoint)


def _timed_checkpoint(
    run_dir: Path,
    checkpoint: dict[str, Any],
    telemetry: RuntimeTelemetry,
) -> None:
    started = telemetry.now()
    _save_checkpoint(run_dir, checkpoint)
    telemetry.elapsed('checkpoint_json', started)


def _metrics_from_mapping(payload: dict[str, Any] | None) -> PassMetrics:
    if payload is None:
        return PassMetrics()
    return PassMetrics(
        documents=int(payload.get("documents", 0)),
        lines=int(payload.get("lines", 0)),
        segments=int(payload.get("segments", 0)),
        characters=int(payload.get("characters", 0)),
        log_partition=float(payload.get("log_partition", 0.0)),
        identity_mass_sum=float(payload.get("identity_mass_sum", 0.0)),
        latent_mass_sum=float(payload.get("latent_mass_sum", 0.0)),
        expected_lexical_tokens=float(payload.get("expected_lexical_tokens", 0.0)),
        expected_piece_tokens=float(payload.get("expected_piece_tokens", 0.0)),
        piece_segmentation_entropy=float(
            payload.get("piece_segmentation_entropy", 0.0)
        ),
        expected_whole_form_uses=float(
            payload.get("expected_whole_form_uses", 0.0)
        ),
        expected_singleton_path_uses=float(
            payload.get("expected_singleton_path_uses", 0.0)
        ),
        expected_multi_piece_uses=float(
            payload.get("expected_multi_piece_uses", 0.0)
        ),
        overflowed_tokens=int(payload.get("overflowed_tokens", 0)),
        candidate_factors=int(payload.get("candidate_factors", 0)),
        candidate_nodes=int(payload.get("candidate_nodes", 0)),
        candidate_edges=int(payload.get("candidate_edges", 0)),
        lazy_span_traversals=int(payload.get("lazy_span_traversals", 0)),
        composed_states=int(payload.get("composed_states", 0)),
        composed_transitions=int(payload.get("composed_transitions", 0)),
        piece_score_calls=int(payload.get("piece_score_calls", 0)),
        piece_score_cache_hits=int(payload.get("piece_score_cache_hits", 0)),
        piece_score_cache_misses=int(payload.get("piece_score_cache_misses", 0)),
        form_cache_hits=int(payload.get("form_cache_hits", 0)),
        form_cache_misses=int(payload.get("form_cache_misses", 0)),
        piece_store_lookups=int(payload.get("piece_store_lookups", 0)),
    )


def _training_shard_paths(
    run_dir: Path,
    pass_index: int,
    document_index: int,
) -> tuple[Path, Path]:
    root = run_dir / 'shards' / f'pass_{pass_index:04d}'
    stem = f'document_{document_index:08d}'
    return root / f'{stem}.counts.tsv', root / f'{stem}.complete.json'


def _training_bundle_paths(
    run_dir: Path,
    pass_index: int,
    bundle: ExecutionBundle,
) -> dict[str, Path]:
    root = run_dir / "shards" / f"pass_{pass_index:04d}" / "bundles"
    stem = (
        f"document_{bundle.document_index:08d}."
        f"bundle_{bundle.bundle_index:06d}"
    )
    return {
        "segments": root / f"{stem}.segments.jsonl",
        "marker": root / f"{stem}.complete.json",
        "topology": root / f"{stem}.topology.bin",
    }


def _iter_execution_bundle_segments(
    document: CorpusDocument,
    config: TrainingConfig,
    bundle: ExecutionBundle,
) -> Iterator[tuple[int, int, ObservedSegment]]:
    """Yield exactly one canonical contiguous range of atomic segments."""

    first_identity = (bundle.first_line_number, bundle.first_segment_index)
    last_identity = (bundle.last_line_number, bundle.last_segment_index)
    seen = 0
    first_seen: tuple[int, int] | None = None
    last_seen: tuple[int, int] | None = None
    phonemes = 0
    pressure = 0
    with document.path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if (
                config.max_lines_per_document is not None
                and line_number > config.max_lines_per_document
            ):
                break
            if line_number < bundle.first_line_number:
                continue
            if line_number > bundle.last_line_number:
                break
            if not line.strip():
                continue
            for segment_index, segment in enumerate(
                iter_observed_segments(
                    line.rstrip("\r\n"),
                    max_tokens=config.max_segment_tokens,
                    script=config.script,
                )
            ):
                identity = (line_number, segment_index)
                if identity < first_identity:
                    continue
                if identity > last_identity:
                    break
                segment_phonemes = sum(
                    len(token.phonemes) for token in segment.tokens
                )
                if first_seen is None:
                    first_seen = identity
                last_seen = identity
                seen += 1
                phonemes += segment_phonemes
                pressure += segment_phonemes * segment_phonemes
                yield line_number, segment_index, segment
    if (
        first_seen != first_identity
        or last_seen != last_identity
        or seen != bundle.segment_count
        or phonemes != bundle.phonemes
        or pressure != bundle.pressure
    ):
        raise RuntimeError(
            "Execution bundle no longer matches canonical ObservedSegments: "
            f"{document.relative_path} bundle {bundle.bundle_index}."
        )


def _exact_metrics_payload(metrics: PassMetrics) -> dict[str, int | str]:
    return {
        name: value.hex() if isinstance(value, float) else int(value)
        for name, value in asdict(metrics).items()
    }


def _metrics_from_exact_payload(payload: dict[str, Any]) -> PassMetrics:
    decoded = {
        name: float.fromhex(value) if isinstance(value, str) else int(value)
        for name, value in payload.items()
    }
    return PassMetrics(**decoded)


def _topology_archive_path(run_dir: Path, document_index: int) -> Path:
    return run_dir / "topology" / f"document_{document_index:08d}.bin"


def _topology_archive_header(
    config_signature: str,
    document_index: int,
    document: CorpusDocument,
) -> dict[str, Any]:
    return archive_header(
        config_signature=config_signature,
        document_index=document_index,
        relative_path=document.relative_path,
        freeze_id=document.freeze_id,
    )


def _rebuild_topology_archive(
    *,
    document: CorpusDocument,
    document_index: int,
    config: TrainingConfig,
    run_dir: Path,
    config_signature: str,
    grammar: StructuredSandhiGrammar,
    piece_engine: ComposedPieceInference,
    telemetry: RuntimeTelemetry,
    error: BaseException,
) -> None:
    """Reconstruct one score-free archive without touching scientific state."""

    path = _topology_archive_path(run_dir, document_index)
    temporary = path.with_suffix(path.suffix + ".rebuild.tmp")
    if isinstance(error, FileNotFoundError):
        telemetry.increment("topology_archive_cache_misses", 1)
    else:
        telemetry.increment("topology_archive_cache_invalid", 1)
    if temporary.exists():
        temporary.unlink()
    writer: TopologyArchiveWriter | None = None
    try:
        writer = TopologyArchiveWriter(
            temporary,
            _topology_archive_header(
                config_signature, document_index, document
            ),
        )
        for line_number, segment_index, segment in _iter_document_segments(
            document, config
        ):
            graph = build_lazy_candidate_graph(
                segment,
                grammar,
                config.candidate_config,
                exact_internal_matches=False,
            )
            writer.write(
                line_number,
                segment_index,
                compile_composed_segment_topology(graph, piece_engine),
            )
        writer.close()
        _replace_file(temporary, path)
    except BaseException:
        if writer is not None:
            writer.close()
        if temporary.exists():
            temporary.unlink()
        raise
    telemetry.increment("topology_archives_regenerated", 1)
    telemetry.increment("topology_records_regenerated", writer.records)
    telemetry.increment(
        "topology_regenerated_uncompressed_bytes", writer.uncompressed_bytes
    )
    telemetry.maximum("topology_archive_bytes", path.stat().st_size)


def _open_reconstructible_topology_archive(
    *,
    document: CorpusDocument,
    document_index: int,
    config: TrainingConfig,
    run_dir: Path,
    config_signature: str,
    grammar: StructuredSandhiGrammar,
    piece_engine: ComposedPieceInference,
    telemetry: RuntimeTelemetry,
) -> ReconstructibleTopologyArchiveReader:
    header = _topology_archive_header(
        config_signature, document_index, document
    )

    def rebuild(error: BaseException) -> None:
        _rebuild_topology_archive(
            document=document,
            document_index=document_index,
            config=config,
            run_dir=run_dir,
            config_signature=config_signature,
            grammar=grammar,
            piece_engine=piece_engine,
            telemetry=telemetry,
            error=error,
        )

    return ReconstructibleTopologyArchiveReader(
        _topology_archive_path(run_dir, document_index),
        header,
        rebuild,
    )


def _validate_bundle_topology_archive(
    *,
    document: CorpusDocument,
    document_index: int,
    config: TrainingConfig,
    run_dir: Path,
    config_signature: str,
    grammar: StructuredSandhiGrammar,
    piece_engine: ComposedPieceInference,
    telemetry: RuntimeTelemetry,
) -> None:
    """Validate or reconstruct once before concurrent range readers start."""

    reader = _open_reconstructible_topology_archive(
        document=document,
        document_index=document_index,
        config=config,
        run_dir=run_dir,
        config_signature=config_signature,
        grammar=grammar,
        piece_engine=piece_engine,
        telemetry=telemetry,
    )
    try:
        for line_number, segment_index, _segment in _iter_document_segments(
            document, config
        ):
            reader.read(line_number, segment_index)
        reader.close()
    finally:
        reader.close(require_eof=False)
    telemetry.increment("training_bundle_topology_archives_validated", 1)


def _profiled_document_segments_with_topology(
    document: CorpusDocument,
    document_index: int,
    config: TrainingConfig,
    run_dir: Path,
    telemetry: RuntimeTelemetry,
    *,
    phase: str,
    config_signature: str,
    grammar: StructuredSandhiGrammar,
    piece_engine: ComposedPieceInference | None,
) -> Iterator[tuple[int, int, ObservedSegment, CompiledSegmentTopology | None]]:
    reader = None
    if config.model == S1M2_MODEL and not COMPACT_EXACT_S1M2:
        assert piece_engine is not None
        reader = _open_reconstructible_topology_archive(
            document=document,
            document_index=document_index,
            config=config,
            run_dir=run_dir,
            config_signature=config_signature,
            grammar=grammar,
            piece_engine=piece_engine,
            telemetry=telemetry,
        )
    try:
        for line_number, segment_index, segment in _profiled_document_segments(
            document,
            config,
            telemetry,
            phase=phase,
        ):
            topology = (
                None
                if reader is None
                else reader.read(line_number, segment_index)
            )
            yield line_number, segment_index, segment, topology
        if reader is not None:
            reader.close()
            telemetry.increment("topology_archives_reused", 1)
            telemetry.increment("topology_records_reused", reader.records)
    finally:
        if reader is not None:
            reader.close(require_eof=False)


def _initialize_training_worker(
    pass_index: int,
    database_path: Path,
    config: TrainingConfig,
    vocabulary: FrozenVocabulary | None,
) -> None:
    global _WORKER_CONNECTION, _WORKER_GRAMMAR, _WORKER_PIECE_ENGINE
    global _WORKER_SCORER, _WORKER_VOCABULARY
    _WORKER_GRAMMAR = StructuredSandhiGrammar.from_default_inventory()
    _WORKER_VOCABULARY = vocabulary
    _WORKER_PIECE_ENGINE = None
    if config.model == S1M2_MODEL:
        if pass_index == 1:
            piece_scorer = NeutralPieceScorer()
            _WORKER_CONNECTION = None
        else:
            uri = database_path.resolve().as_uri() + '?mode=ro'
            connection = sqlite3.connect(uri, uri=True)
            connection.execute('PRAGMA query_only=ON')
            _WORKER_CONNECTION = connection
            piece_scorer = PieceStoreScorer(
                connection,
                alpha=config.piece_alpha,
                complexity_weight=config.piece_complexity_weight,
                complexity_kappa=config.piece_complexity_kappa,
                complexity_beta=config.piece_complexity_beta,
                complexity_tau=config.piece_complexity_tau,
                base_stop_probability=config.piece_base_stop_probability,
                cache_size=config.lexicon_cache_size,
                telemetry=RuntimeTelemetry(),
            )
        _WORKER_PIECE_ENGINE = ComposedPieceInference(
            piece_scorer,
            model_config=config.piece_model_config,
            cache_config=config.piece_cache_config,
        )
        _WORKER_SCORER = None
        return
    if pass_index == 1:
        _WORKER_SCORER = NeutralFormScorer()
        _WORKER_CONNECTION = None
        return
    uri = database_path.resolve().as_uri() + '?mode=ro'
    connection = sqlite3.connect(uri, uri=True)
    connection.execute('PRAGMA query_only=ON')
    telemetry = RuntimeTelemetry()
    _WORKER_CONNECTION = connection
    _WORKER_SCORER = LexiconScorer(
        connection,
        alpha=config.lexical_alpha,
        complexity_weight=config.complexity_weight,
        complexity_tau=config.complexity_tau,
        cache_size=config.lexicon_cache_size,
        telemetry=telemetry,
    )


def _write_training_shard(
    document_index: int,
    document: CorpusDocument,
    config: TrainingConfig,
    pass_index: int,
    run_dir: Path,
    config_signature: str,
) -> dict[str, Any]:
    if _WORKER_GRAMMAR is None or (
        config.model == S1M1_MODEL and _WORKER_SCORER is None
    ) or (
        config.model == S1M2_MODEL and _WORKER_PIECE_ENGINE is None
    ):
        raise RuntimeError('Training worker was not initialized.')
    shard_path, marker_path = _training_shard_paths(
        run_dir,
        pass_index,
        document_index,
    )
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = shard_path.with_suffix(shard_path.suffix + '.tmp')
    counts: Counter[PhonologicalForm] = Counter()
    piece_counts: Counter[PhonologicalForm] = Counter()
    piece_support: Counter[PhonologicalForm] = Counter()
    metrics = PassMetrics()
    seen_lines: set[int] = set()
    row_count = 0
    candidate_seconds = 0.0
    inference_seconds = 0.0
    aggregation_seconds = 0.0
    frontend_seconds = 0.0
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    active_scorer = (
        _WORKER_SCORER
        if config.model == S1M1_MODEL
        else _WORKER_PIECE_ENGINE.scorer
    )
    scorer_calls_before = int(getattr(active_scorer, 'score_calls', 0))
    sqlite_selects_before = int(getattr(active_scorer, 'sqlite_selects', 0))
    sqlite_seconds_before = float(getattr(active_scorer, 'sqlite_seconds', 0.0))
    piece_counters_before = (
        _WORKER_PIECE_ENGINE.counter_snapshot()
        if config.model == S1M2_MODEL
        else None
    )
    engineering = RuntimeTelemetry()

    def flush(handle: Any) -> None:
        nonlocal row_count
        if not counts and not piece_counts:
            return
        if config.model == S1M1_MODEL:
            for form, value in sorted(counts.items(), key=lambda item: item[0].key):
                handle.write(f'{form.key}\t{float(value).hex()}\n')
                row_count += 1
        else:
            for form, value in sorted(counts.items(), key=lambda item: item[0].key):
                handle.write(f'L\t{form.key}\t{float(value).hex()}\n')
                row_count += 1
            for piece, value in sorted(
                piece_counts.items(), key=lambda item: item[0].key
            ):
                handle.write(
                    f'P\t{piece.key}\t{float(value).hex()}\t'
                    f'{piece_support[piece]}\n'
                )
                row_count += 1
        counts.clear()
        piece_counts.clear()
        piece_support.clear()

    topology_path = _topology_archive_path(run_dir, document_index)
    topology_temporary = topology_path.with_suffix(topology_path.suffix + ".tmp")
    topology_writer: TopologyArchiveWriter | None = None
    topology_reader: ReconstructibleTopologyArchiveReader | None = None
    with ExitStack() as resources:
        handle = resources.enter_context(
            temporary.open('w', encoding='utf-8', newline='')
        )
        if config.model == S1M2_MODEL and not COMPACT_EXACT_S1M2:
            header = _topology_archive_header(
                config_signature, document_index, document
            )
            if pass_index == 1 and not COMPACT_EXACT_S1M2:
                if topology_temporary.exists():
                    topology_temporary.unlink()
                topology_writer = resources.enter_context(
                    TopologyArchiveWriter(topology_temporary, header)
                )
            else:
                assert _WORKER_GRAMMAR is not None
                assert _WORKER_PIECE_ENGINE is not None
                topology_reader = resources.enter_context(
                    _open_reconstructible_topology_archive(
                        document=document,
                        document_index=document_index,
                        config=config,
                        run_dir=run_dir,
                        config_signature=config_signature,
                        grammar=_WORKER_GRAMMAR,
                        piece_engine=_WORKER_PIECE_ENGINE,
                        telemetry=engineering,
                    )
                )
        iterator = _iter_document_segments(document, config)
        while True:
            started = time.perf_counter()
            try:
                line_number, segment_index, segment = next(iterator)
            except StopIteration:
                frontend_seconds += time.perf_counter() - started
                break
            frontend_seconds += time.perf_counter() - started
            seen_lines.add(line_number)
            _observe_segment_telemetry(
                engineering,
                segment,
                config,
                phase="training",
            )
            started = time.perf_counter()
            candidate_profile = (
                CandidateBuildProfile() if config.model == S1M2_MODEL else None
            )
            if config.model == S1M1_MODEL:
                graph = build_candidate_graph(
                    segment,
                    _WORKER_GRAMMAR,
                    config.candidate_config,
                )
            else:
                graph = build_lazy_candidate_graph(
                    segment,
                    _WORKER_GRAMMAR,
                    config.candidate_config,
                    profile=candidate_profile,
                )
            candidate_seconds += time.perf_counter() - started
            candidate_counts = (
                candidate_graph_statistics(graph)
                if config.model == S1M1_MODEL
                else lazy_candidate_graph_statistics(graph)
            )
            if candidate_profile is not None:
                _record_candidate_telemetry(
                    engineering,
                    candidate_profile,
                    candidate_counts,
                    phase="training",
                )
            segment_topology = None
            if config.model == S1M2_MODEL and not COMPACT_EXACT_S1M2:
                assert _WORKER_PIECE_ENGINE is not None
                if topology_writer is not None:
                    segment_topology = compile_composed_segment_topology(
                        graph, _WORKER_PIECE_ENGINE
                    )
                    topology_writer.write(
                        line_number, segment_index, segment_topology
                    )
                else:
                    assert topology_reader is not None
                    segment_topology = topology_reader.read(
                        line_number, segment_index
                    )
            started = time.perf_counter()
            if config.model == S1M1_MODEL:
                inference = infer_training_segment(
                    graph,
                    _WORKER_SCORER,
                    whitespace_merge_penalty=config.whitespace_merge_penalty,
                    vocabulary=_WORKER_VOCABULARY,
                )
            else:
                inference = infer_composed_segment(
                    graph,
                    _WORKER_PIECE_ENGINE,
                    whitespace_merge_penalty=config.whitespace_merge_penalty,
                    support_epsilon=config.piece_support_epsilon,
                    topology=segment_topology,
                )
                _record_composed_timings(
                    engineering,
                    inference.timings,
                    phase="training",
                )
            inference_seconds += time.perf_counter() - started
            started = time.perf_counter()
            counts.update(
                inference.expected_counts
                if config.model == S1M1_MODEL
                else inference.lexical_expected_counts
            )
            if config.model == S1M2_MODEL:
                piece_counts.update(inference.piece_expected_counts)
                piece_support.update(inference.piece_occurrence_support)
            aggregation_seconds += time.perf_counter() - started
            metrics.update(
                segment,
                inference,
                overflowed_tokens=graph.overflowed_tokens,
                candidate_factors=candidate_counts['factors'],
                candidate_nodes=candidate_counts['lattice_nodes'],
                candidate_edges=(
                    candidate_counts['lexical_edges']
                    if config.model == S1M1_MODEL
                    else candidate_counts['lexical_span_hypotheses']
                ),
            )
            if len(counts) + len(piece_counts) >= config.flush_types:
                flush(handle)
        flush(handle)
        handle.flush()
        os.fsync(handle.fileno())
    _replace_file(temporary, shard_path)
    if topology_writer is not None:
        _replace_file(topology_temporary, topology_path)
        engineering.increment("topology_archives_compiled", 1)
        engineering.increment("topology_records_compiled", topology_writer.records)
        engineering.increment(
            "topology_uncompressed_bytes", topology_writer.uncompressed_bytes
        )
        engineering.maximum(
            "topology_archive_bytes", topology_path.stat().st_size
        )
    elif topology_reader is not None:
        engineering.increment("topology_archives_reused", 1)
        engineering.increment("topology_records_reused", topology_reader.records)
    metrics.documents = 1
    metrics.lines = len(seen_lines)
    payload = {
        'schema_version': 1 if config.model == S1M1_MODEL else 2,
        'config_signature': config_signature,
        'pass_index': pass_index,
        'document_index': document_index,
        'relative_path': document.relative_path,
        'count_shard': shard_path.name,
        'count_shard_sha256': _file_sha256(shard_path),
        'count_rows': row_count,
        'metrics': asdict(metrics),
        'runtime': {
            'training_candidate_generation': candidate_seconds,
            'training_inference': inference_seconds,
            'training_count_aggregation': aggregation_seconds,
            'training_frontend_io': frontend_seconds,
            'training_worker_document_total': time.perf_counter() - wall_started,
            'training_worker_cpu': time.process_time() - cpu_started,
            'lexical_score_calls': (
                int(getattr(active_scorer, 'score_calls', 0))
                - scorer_calls_before
            ),
            'sqlite_selects': (
                int(getattr(active_scorer, 'sqlite_selects', 0))
                - sqlite_selects_before
            ),
            'sqlite_seconds': (
                float(getattr(active_scorer, 'sqlite_seconds', 0.0))
                - sqlite_seconds_before
            ),
            'composed_counters': (
                asdict(
                    _WORKER_PIECE_ENGINE.counter_delta(piece_counters_before)
                )
                if piece_counters_before is not None
                else {}
            ),
            "engineering_telemetry": engineering.payload(),
        },
    }
    _write_json(marker_path, payload)
    return payload


def _write_training_bundle_shard(
    bundle: ExecutionBundle,
    document: CorpusDocument,
    config: TrainingConfig,
    pass_index: int,
    run_dir: Path,
    config_signature: str,
    plan_sha256: str,
) -> dict[str, Any]:
    """Compute bundle segments without changing their canonical reduction order."""

    if _WORKER_GRAMMAR is None or _WORKER_PIECE_ENGINE is None:
        raise RuntimeError("S1M2 bundle worker was not initialized.")
    paths = _training_bundle_paths(run_dir, pass_index, bundle)
    paths["segments"].parent.mkdir(parents=True, exist_ok=True)
    segment_temporary = paths["segments"].with_suffix(".jsonl.tmp")
    topology_temporary = paths["topology"].with_suffix(".bin.tmp")
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    candidate_seconds = 0.0
    inference_seconds = 0.0
    aggregation_seconds = 0.0
    frontend_seconds = 0.0
    active_scorer = _WORKER_PIECE_ENGINE.scorer
    scorer_calls_before = int(getattr(active_scorer, "score_calls", 0))
    sqlite_selects_before = int(getattr(active_scorer, "sqlite_selects", 0))
    sqlite_seconds_before = float(getattr(active_scorer, "sqlite_seconds", 0.0))
    piece_counters_before = _WORKER_PIECE_ENGINE.counter_snapshot()
    engineering = RuntimeTelemetry()
    records = 0

    try:
        with ExitStack() as resources:
            handle = resources.enter_context(
                segment_temporary.open("w", encoding="utf-8", newline="")
            )
            topology_writer: TopologyArchiveWriter | None = None
            topology_reader: TopologyArchiveReader | None = None
            if not COMPACT_EXACT_S1M2:
                header = _topology_archive_header(
                    config_signature, bundle.document_index, document
                )
                if pass_index == 1 and not COMPACT_EXACT_S1M2:
                    topology_writer = resources.enter_context(
                        TopologyArchiveWriter(topology_temporary, header)
                    )
                else:
                    topology_reader = TopologyArchiveReader(
                        _topology_archive_path(run_dir, bundle.document_index),
                        header,
                    )
                    topology_reader.skip_records(bundle.first_segment_ordinal)
                    resources.callback(topology_reader.close, require_eof=False)

            iterator = _iter_execution_bundle_segments(document, config, bundle)
            while True:
                started = time.perf_counter()
                try:
                    line_number, segment_index, segment = next(iterator)
                except StopIteration:
                    frontend_seconds += time.perf_counter() - started
                    break
                frontend_seconds += time.perf_counter() - started
                _observe_segment_telemetry(
                    engineering, segment, config, phase="training"
                )
                started = time.perf_counter()
                candidate_profile = CandidateBuildProfile()
                graph = build_lazy_candidate_graph(
                    segment,
                    _WORKER_GRAMMAR,
                    config.candidate_config,
                    profile=candidate_profile,
                )
                candidate_seconds += time.perf_counter() - started
                candidate_counts = lazy_candidate_graph_statistics(graph)
                _record_candidate_telemetry(
                    engineering,
                    candidate_profile,
                    candidate_counts,
                    phase="training",
                )
                topology = None
                if topology_writer is not None:
                    topology = compile_composed_segment_topology(
                        graph, _WORKER_PIECE_ENGINE
                    )
                    topology_writer.write(line_number, segment_index, topology)
                elif topology_reader is not None:
                    topology = topology_reader.read(line_number, segment_index)

                started = time.perf_counter()
                inference = infer_composed_segment(
                    graph,
                    _WORKER_PIECE_ENGINE,
                    whitespace_merge_penalty=config.whitespace_merge_penalty,
                    support_epsilon=config.piece_support_epsilon,
                    topology=topology,
                )
                _record_composed_timings(
                    engineering, inference.timings, phase="training"
                )
                inference_seconds += time.perf_counter() - started
                started = time.perf_counter()
                segment_metrics = PassMetrics()
                segment_metrics.update(
                    segment,
                    inference,
                    overflowed_tokens=graph.overflowed_tokens,
                    candidate_factors=candidate_counts["factors"],
                    candidate_nodes=candidate_counts["lattice_nodes"],
                    candidate_edges=candidate_counts["lexical_span_hypotheses"],
                )
                record = {
                    "schema_version": "sktlm-s1m2-training-segment-result/v1",
                    "line_number": line_number,
                    "segment_index": segment_index,
                    "lexical_counts": [
                        (form.key, float(value).hex())
                        for form, value in sorted(
                            inference.lexical_expected_counts.items(),
                            key=lambda item: item[0].key,
                        )
                    ],
                    "piece_counts": [
                        (
                            piece.key,
                            float(value).hex(),
                            int(inference.piece_occurrence_support[piece]),
                        )
                        for piece, value in sorted(
                            inference.piece_expected_counts.items(),
                            key=lambda item: item[0].key,
                        )
                    ],
                    "metrics": _exact_metrics_payload(segment_metrics),
                }
                aggregation_seconds += time.perf_counter() - started
                handle.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                records += 1
            handle.flush()
            os.fsync(handle.fileno())
        _replace_file(segment_temporary, paths["segments"])
        topology_name = None
        topology_sha = None
        if topology_writer is not None:
            _replace_file(topology_temporary, paths["topology"])
            topology_name = paths["topology"].name
            topology_sha = _file_sha256(paths["topology"])
        payload = {
            "schema_version": "sktlm-s1m2-training-bundle-shard/v1",
            "config_signature": config_signature,
            "plan_sha256": plan_sha256,
            "pass_index": pass_index,
            "document_index": bundle.document_index,
            "relative_path": document.relative_path,
            "bundle_index": bundle.bundle_index,
            "first_segment_ordinal": bundle.first_segment_ordinal,
            "last_segment_ordinal_exclusive": (
                bundle.last_segment_ordinal_exclusive
            ),
            "segment_count": records,
            "segment_shard": paths["segments"].name,
            "segment_shard_sha256": _file_sha256(paths["segments"]),
            "topology_shard": topology_name,
            "topology_shard_sha256": topology_sha,
            "runtime": {
                "training_candidate_generation": candidate_seconds,
                "training_inference": inference_seconds,
                "training_count_aggregation": aggregation_seconds,
                "training_frontend_io": frontend_seconds,
                "training_worker_document_total": (
                    time.perf_counter() - wall_started
                ),
                "training_worker_cpu": time.process_time() - cpu_started,
                "lexical_score_calls": (
                    int(getattr(active_scorer, "score_calls", 0))
                    - scorer_calls_before
                ),
                "sqlite_selects": (
                    int(getattr(active_scorer, "sqlite_selects", 0))
                    - sqlite_selects_before
                ),
                "sqlite_seconds": (
                    float(getattr(active_scorer, "sqlite_seconds", 0.0))
                    - sqlite_seconds_before
                ),
                "composed_counters": asdict(
                    _WORKER_PIECE_ENGINE.counter_delta(piece_counters_before)
                ),
                "engineering_telemetry": engineering.payload(),
            },
        }
        _write_json(paths["marker"], payload)
        return payload
    except BaseException:
        for temporary in (segment_temporary, topology_temporary):
            if temporary.exists():
                temporary.unlink()
        raise


def _load_training_bundle_shard(
    *,
    run_dir: Path,
    pass_index: int,
    bundle: ExecutionBundle,
    document: CorpusDocument,
    config_signature: str,
    plan_sha256: str,
) -> dict[str, Any] | None:
    paths = _training_bundle_paths(run_dir, pass_index, bundle)
    if not paths["segments"].is_file() or not paths["marker"].is_file():
        return None
    payload = json.loads(paths["marker"].read_text(encoding="utf-8"))
    expected = (
        payload.get("schema_version")
        == "sktlm-s1m2-training-bundle-shard/v1"
        and payload.get("config_signature") == config_signature
        and payload.get("plan_sha256") == plan_sha256
        and int(payload.get("pass_index", -1)) == pass_index
        and int(payload.get("document_index", -1)) == bundle.document_index
        and payload.get("relative_path") == document.relative_path
        and int(payload.get("bundle_index", -1)) == bundle.bundle_index
        and int(payload.get("first_segment_ordinal", -1))
        == bundle.first_segment_ordinal
        and int(payload.get("last_segment_ordinal_exclusive", -1))
        == bundle.last_segment_ordinal_exclusive
        and int(payload.get("segment_count", -1)) == bundle.segment_count
    )
    if not expected:
        raise RuntimeError(f"Stale or mismatched bundle shard: {paths['marker']}")
    if payload.get("segment_shard_sha256") != _file_sha256(paths["segments"]):
        raise RuntimeError(f"Bundle shard checksum mismatch: {paths['segments']}")
    if pass_index == 1 and not COMPACT_EXACT_S1M2:
        if not paths["topology"].is_file() or (
            payload.get("topology_shard_sha256")
            != _file_sha256(paths["topology"])
        ):
            raise RuntimeError(
                f"Bundle topology checksum mismatch: {paths['topology']}"
            )
    return payload


def _coalesce_training_bundle_shards(
    *,
    bundles: tuple[ExecutionBundle, ...],
    payloads: dict[tuple[int, int], dict[str, Any]],
    document: CorpusDocument,
    config: TrainingConfig,
    pass_index: int,
    run_dir: Path,
    config_signature: str,
) -> dict[str, Any]:
    """Recreate the legacy document shard with its original left-fold order."""

    document_index = bundles[0].document_index
    shard_path, marker_path = _training_shard_paths(
        run_dir, pass_index, document_index
    )
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = shard_path.with_suffix(shard_path.suffix + ".tmp")
    topology_path = _topology_archive_path(run_dir, document_index)
    topology_temporary = topology_path.with_suffix(topology_path.suffix + ".tmp")
    counts: Counter[PhonologicalForm] = Counter()
    piece_counts: Counter[PhonologicalForm] = Counter()
    piece_support: Counter[PhonologicalForm] = Counter()
    metrics = PassMetrics()
    seen_lines: set[int] = set()
    row_count = 0
    runtime_totals: Counter[str] = Counter()
    composed_totals: Counter[str] = Counter()
    engineering = RuntimeTelemetry()

    def flush(handle: Any) -> None:
        nonlocal row_count
        if not counts and not piece_counts:
            return
        for form, value in sorted(counts.items(), key=lambda item: item[0].key):
            handle.write(f"L\t{form.key}\t{float(value).hex()}\n")
            row_count += 1
        for piece, value in sorted(
            piece_counts.items(), key=lambda item: item[0].key
        ):
            handle.write(
                f"P\t{piece.key}\t{float(value).hex()}\t"
                f"{piece_support[piece]}\n"
            )
            row_count += 1
        counts.clear()
        piece_counts.clear()
        piece_support.clear()

    topology_writer: TopologyArchiveWriter | None = None
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            if pass_index == 1 and not COMPACT_EXACT_S1M2:
                topology_writer = TopologyArchiveWriter(
                    topology_temporary,
                    _topology_archive_header(
                        config_signature, document_index, document
                    ),
                )
            for bundle in bundles:
                payload = payloads[bundle.key]
                paths = _training_bundle_paths(run_dir, pass_index, bundle)
                topology_reader = None
                if pass_index == 1 and not COMPACT_EXACT_S1M2:
                    topology_reader = TopologyArchiveReader(
                        paths["topology"],
                        _topology_archive_header(
                            config_signature, document_index, document
                        ),
                    )
                record_count = 0
                first_identity: tuple[int, int] | None = None
                last_identity: tuple[int, int] | None = None
                try:
                    with paths["segments"].open(encoding="utf-8") as source:
                        for line in source:
                            record = json.loads(line)
                            if (
                                record.get("schema_version")
                                != "sktlm-s1m2-training-segment-result/v1"
                            ):
                                raise RuntimeError(
                                    f"Invalid bundle segment record: {paths['segments']}"
                                )
                            identity = (
                                int(record["line_number"]),
                                int(record["segment_index"]),
                            )
                            if first_identity is None:
                                first_identity = identity
                            last_identity = identity
                            seen_lines.add(identity[0])
                            for key, value in record["lexical_counts"]:
                                counts[PhonologicalForm.from_key(key)] += (
                                    float.fromhex(value)
                                )
                            for key, value, support in record["piece_counts"]:
                                piece = PhonologicalForm.from_key(key)
                                piece_counts[piece] += float.fromhex(value)
                                piece_support[piece] += int(support)
                            metrics = metrics.merged(
                                _metrics_from_exact_payload(record["metrics"])
                            )
                            if topology_reader is not None:
                                assert topology_writer is not None
                                topology_writer.write(
                                    identity[0],
                                    identity[1],
                                    topology_reader.read(*identity),
                                )
                            record_count += 1
                            if len(counts) + len(piece_counts) >= config.flush_types:
                                flush(handle)
                finally:
                    if topology_reader is not None:
                        topology_reader.close()
                if (
                    record_count != bundle.segment_count
                    or first_identity
                    != (bundle.first_line_number, bundle.first_segment_index)
                    or last_identity
                    != (bundle.last_line_number, bundle.last_segment_index)
                ):
                    raise RuntimeError(
                        f"Bundle segment order mismatch: {paths['segments']}"
                    )
                runtime = payload["runtime"]
                for label in (
                    "training_candidate_generation",
                    "training_inference",
                    "training_count_aggregation",
                    "training_frontend_io",
                    "training_worker_document_total",
                    "training_worker_cpu",
                    "lexical_score_calls",
                    "sqlite_selects",
                    "sqlite_seconds",
                ):
                    runtime_totals[label] += runtime[label]
                composed_totals.update(runtime.get("composed_counters", {}))
                if runtime.get("engineering_telemetry"):
                    engineering.merge_payload(runtime["engineering_telemetry"])
            flush(handle)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_file(temporary, shard_path)
        if topology_writer is not None:
            topology_writer.close()
            _replace_file(topology_temporary, topology_path)
            engineering.increment("topology_archives_compiled", 1)
            engineering.increment(
                "topology_records_compiled", topology_writer.records
            )
            engineering.increment(
                "topology_uncompressed_bytes", topology_writer.uncompressed_bytes
            )
            engineering.maximum("topology_archive_bytes", topology_path.stat().st_size)
        metrics.documents = 1
        metrics.lines = len(seen_lines)
        payload = {
            "schema_version": 2,
            "config_signature": config_signature,
            "pass_index": pass_index,
            "document_index": document_index,
            "relative_path": document.relative_path,
            "count_shard": shard_path.name,
            "count_shard_sha256": _file_sha256(shard_path),
            "count_rows": row_count,
            "metrics": asdict(metrics),
            "runtime": {
                **{
                    label: float(runtime_totals[label])
                    for label in (
                        "training_candidate_generation",
                        "training_inference",
                        "training_count_aggregation",
                        "training_frontend_io",
                        "training_worker_document_total",
                        "training_worker_cpu",
                        "sqlite_seconds",
                    )
                },
                "lexical_score_calls": int(
                    runtime_totals["lexical_score_calls"]
                ),
                "sqlite_selects": int(runtime_totals["sqlite_selects"]),
                "composed_counters": dict(composed_totals),
                "engineering_telemetry": engineering.payload(),
            },
        }
        _write_json(marker_path, payload)
        return payload
    except BaseException:
        if topology_writer is not None:
            topology_writer.close()
        for path in (temporary, topology_temporary):
            if path.exists():
                path.unlink()
        raise


def _retire_training_bundle_shards(
    run_dir: Path,
    pass_index: int,
    bundles: tuple[ExecutionBundle, ...],
) -> None:
    for bundle in bundles:
        for path in _training_bundle_paths(run_dir, pass_index, bundle).values():
            if path.is_file():
                path.unlink()


def _apply_compact_training_bundle_shards(
    *,
    bundles: tuple[ExecutionBundle, ...],
    payloads: dict[tuple[int, int], dict[str, Any]],
    store: LexiconStore,
    config: TrainingConfig,
    checkpoint: dict[str, Any],
    metrics: PassMetrics,
    run_dir: Path,
    pass_index: int,
    telemetry: RuntimeTelemetry,
) -> PassMetrics:
    """Fold canonical compact bundle records directly into one document transaction."""

    document_index = bundles[0].document_index
    lexical_counts: Counter[PhonologicalForm] = Counter()
    piece_counts: Counter[PhonologicalForm] = Counter()
    piece_support: Counter[PhonologicalForm] = Counter()
    document_metrics = PassMetrics()
    seen_lines: set[int] = set()
    runtime_totals: Counter[str] = Counter()
    composed_totals: Counter[str] = Counter()
    engineering = RuntimeTelemetry()

    def flush() -> None:
        if lexical_counts:
            store.add_document_lexical_diagnostics(
                sorted(lexical_counts.items(), key=lambda item: item[0].key)
            )
            lexical_counts.clear()
        if piece_counts:
            store.add_document_piece_counts(
                (
                    (piece, value, piece_support[piece])
                    for piece, value in sorted(
                        piece_counts.items(), key=lambda item: item[0].key
                    )
                )
            )
            piece_counts.clear()
            piece_support.clear()

    store.begin_document_counts()
    try:
        for bundle in bundles:
            payload = payloads[bundle.key]
            paths = _training_bundle_paths(run_dir, pass_index, bundle)
            record_count = 0
            first_identity: tuple[int, int] | None = None
            last_identity: tuple[int, int] | None = None
            with paths["segments"].open(encoding="utf-8") as source:
                for line in source:
                    record = json.loads(line)
                    if (
                        record.get("schema_version")
                        != "sktlm-s1m2-training-segment-result/v1"
                    ):
                        raise RuntimeError(
                            f"Invalid bundle segment record: {paths['segments']}"
                        )
                    identity = (
                        int(record["line_number"]),
                        int(record["segment_index"]),
                    )
                    if first_identity is None:
                        first_identity = identity
                    last_identity = identity
                    seen_lines.add(identity[0])
                    for key, value in record["lexical_counts"]:
                        lexical_counts[PhonologicalForm.from_key(key)] += (
                            float.fromhex(value)
                        )
                    for key, value, support in record["piece_counts"]:
                        piece = PhonologicalForm.from_key(key)
                        piece_counts[piece] += float.fromhex(value)
                        piece_support[piece] += int(support)
                    document_metrics = document_metrics.merged(
                        _metrics_from_exact_payload(record["metrics"])
                    )
                    record_count += 1
                    if len(lexical_counts) + len(piece_counts) >= config.flush_types:
                        flush()
            if (
                record_count != bundle.segment_count
                or first_identity
                != (bundle.first_line_number, bundle.first_segment_index)
                or last_identity
                != (bundle.last_line_number, bundle.last_segment_index)
            ):
                raise RuntimeError(
                    f"Bundle segment order mismatch: {paths['segments']}"
                )
            runtime = payload["runtime"]
            for label in (
                "training_candidate_generation",
                "training_inference",
                "training_count_aggregation",
                "training_frontend_io",
                "training_worker_document_total",
                "training_worker_cpu",
                "lexical_score_calls",
                "sqlite_selects",
                "sqlite_seconds",
            ):
                runtime_totals[label] += runtime[label]
            composed_totals.update(runtime.get("composed_counters", {}))
            if runtime.get("engineering_telemetry"):
                engineering.merge_payload(runtime["engineering_telemetry"])
        flush()
        document_metrics.documents = 1
        document_metrics.lines = len(seen_lines)
        next_metrics = metrics.merged(document_metrics)
        next_checkpoint = {
            **checkpoint,
            "active_pass": pass_index,
            "next_document_index": document_index + 1,
            "active_metrics": asdict(next_metrics),
        }
        store.commit_document(next_checkpoint)
        _record_store_storage(telemetry, store.path)
    except BaseException:
        store.rollback_document()
        raise

    checkpoint.update(next_checkpoint)
    for label in (
        "training_candidate_generation",
        "training_inference",
        "training_count_aggregation",
        "training_frontend_io",
        "training_worker_document_total",
        "training_worker_cpu",
    ):
        telemetry.add_seconds(label, float(runtime_totals[label]))
    telemetry.increment(
        "training_worker_lexical_score_calls",
        int(runtime_totals["lexical_score_calls"]),
    )
    telemetry.increment(
        "training_worker_sqlite_selects", int(runtime_totals["sqlite_selects"])
    )
    telemetry.add_seconds(
        "training_worker_sqlite", float(runtime_totals["sqlite_seconds"])
    )
    if composed_totals:
        _record_composed_telemetry(
            telemetry,
            ComposedInferenceCounters(**composed_totals),
            phase="training",
        )
    telemetry.merge_payload(engineering.payload())
    _timed_checkpoint(run_dir, checkpoint, telemetry)
    return next_metrics


def _flush_piece_training_counts(
    store: LexiconStore,
    lexical_counts: Counter[PhonologicalForm],
    piece_counts: Counter[PhonologicalForm],
    piece_support: Counter[PhonologicalForm],
) -> None:
    if lexical_counts:
        store.add_document_lexical_diagnostics(lexical_counts.items())
        lexical_counts.clear()
    if piece_counts:
        store.add_document_piece_counts(
            (
                (piece, count, piece_support[piece])
                for piece, count in piece_counts.items()
            )
        )
        piece_counts.clear()
        piece_support.clear()


def _load_training_shard(
    run_dir: Path,
    pass_index: int,
    document_index: int,
    document: CorpusDocument,
    config_signature: str,
) -> dict[str, Any] | None:
    shard_path, marker_path = _training_shard_paths(
        run_dir,
        pass_index,
        document_index,
    )
    if not shard_path.is_file() or not marker_path.is_file():
        return None
    payload = json.loads(marker_path.read_text(encoding='utf-8'))
    expected = (
        payload.get('config_signature') == config_signature
        and int(payload.get('pass_index', -1)) == pass_index
        and int(payload.get('document_index', -1)) == document_index
        and payload.get('relative_path') == document.relative_path
    )
    if not expected:
        raise RuntimeError(f'Stale or mismatched training shard: {marker_path}')
    if payload.get('count_shard_sha256') != _file_sha256(shard_path):
        raise RuntimeError(f'Training shard checksum mismatch: {shard_path}')
    return payload


def _apply_training_shard(
    *,
    payload: dict[str, Any],
    store: LexiconStore,
    config: TrainingConfig,
    checkpoint: dict[str, Any],
    metrics: PassMetrics,
    run_dir: Path,
    telemetry: RuntimeTelemetry,
) -> PassMetrics:
    document_index = int(payload['document_index'])
    pass_index = int(payload['pass_index'])
    shard_path, marker_path = _training_shard_paths(
        run_dir,
        pass_index,
        document_index,
    )
    next_metrics = metrics.merged(_metrics_from_mapping(payload['metrics']))
    next_checkpoint = {
        **checkpoint,
        'active_pass': pass_index,
        'next_document_index': document_index + 1,
        'active_metrics': asdict(next_metrics),
    }
    store.begin_document_counts()
    try:
        buffered: list[tuple[PhonologicalForm, float]] = []
        buffered_pieces: list[tuple[PhonologicalForm, float, int]] = []
        with shard_path.open(encoding='utf-8') as handle:
            for line in handle:
                fields = line.rstrip('\n').split('\t')
                if config.model == S1M1_MODEL:
                    key, value = fields
                    buffered.append(
                        (PhonologicalForm.from_key(key), float.fromhex(value))
                    )
                    if len(buffered) >= config.flush_types:
                        store.add_document_counts(buffered)
                        buffered.clear()
                elif fields[0] == 'L':
                    _kind, key, value = fields
                    buffered.append(
                        (PhonologicalForm.from_key(key), float.fromhex(value))
                    )
                    if len(buffered) >= config.flush_types:
                        store.add_document_lexical_diagnostics(buffered)
                        buffered.clear()
                elif fields[0] == 'P':
                    _kind, key, value, support = fields
                    buffered_pieces.append(
                        (
                            PhonologicalForm.from_key(key),
                            float.fromhex(value),
                            int(support),
                        )
                    )
                    if len(buffered_pieces) >= config.flush_types:
                        store.add_document_piece_counts(buffered_pieces)
                        buffered_pieces.clear()
                else:
                    raise RuntimeError(f'Unknown S1M2 shard row: {fields[0]!r}')
        if buffered:
            if config.model == S1M1_MODEL:
                store.add_document_counts(buffered)
            else:
                store.add_document_lexical_diagnostics(buffered)
        if buffered_pieces:
            store.add_document_piece_counts(buffered_pieces)
        store.commit_document(next_checkpoint)
        _record_store_storage(telemetry, store.path)
    except BaseException:
        store.rollback_document()
        raise
    checkpoint.update(next_checkpoint)
    runtime = payload['runtime']
    for label in (
        'training_candidate_generation',
        'training_inference',
        'training_count_aggregation',
        'training_frontend_io',
        'training_worker_document_total',
        'training_worker_cpu',
    ):
        telemetry.add_seconds(label, float(runtime[label]))
    telemetry.increment(
        'training_worker_lexical_score_calls',
        int(runtime['lexical_score_calls']),
    )
    telemetry.increment(
        'training_worker_sqlite_selects',
        int(runtime['sqlite_selects']),
    )
    telemetry.add_seconds('training_worker_sqlite', float(runtime['sqlite_seconds']))
    if runtime.get('composed_counters'):
        _record_composed_telemetry(
            telemetry,
            ComposedInferenceCounters(**runtime['composed_counters']),
            phase='training',
        )
    if runtime.get("engineering_telemetry"):
        telemetry.merge_payload(runtime["engineering_telemetry"])
    _timed_checkpoint(run_dir, checkpoint, telemetry)
    shard_path.unlink()
    marker_path.unlink()
    return next_metrics


def _parallel_training_documents(
    *,
    pass_index: int,
    documents: tuple[CorpusDocument, ...],
    store: LexiconStore,
    config: TrainingConfig,
    run_dir: Path,
    checkpoint: dict[str, Any],
    telemetry: RuntimeTelemetry,
    start_document: int,
    metrics: PassMetrics,
    vocabulary: FrozenVocabulary | None,
) -> PassMetrics:
    signature = _config_signature(config)
    parallel_started = telemetry.now()
    context = multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(
        max_workers=config.workers,
        mp_context=context,
        initializer=_initialize_training_worker,
        initargs=(pass_index, store.path, config, vocabulary),
    ) as executor:
        max_pending = config.workers * 2
        telemetry.maximum("training_pending_shard_limit", max_pending)
        pending: dict[int, Future[dict[str, Any]] | dict[str, Any]] = {}
        next_submit = start_document

        def fill_pending() -> None:
            nonlocal next_submit
            while next_submit < len(documents) and len(pending) < max_pending:
                document_index = next_submit
                document = documents[document_index]
                existing = _load_training_shard(
                    run_dir,
                    pass_index,
                    document_index,
                    document,
                    signature,
                )
                if existing is not None:
                    pending[document_index] = existing
                else:
                    pending[document_index] = executor.submit(
                        _write_training_shard,
                        document_index,
                        document,
                        config,
                        pass_index,
                        run_dir,
                        signature,
                    )
                next_submit += 1
            telemetry.maximum("training_pending_shards", len(pending))

        fill_pending()
        for document_index in range(start_document, len(documents)):
            telemetry.observe("training_pending_shards_per_reduction", len(pending))
            item = pending.pop(document_index)
            if isinstance(item, Future):
                ready = item.done()
                wait_started = telemetry.now()
                payload = item.result()
                telemetry.add_seconds(
                    "training_reducer_stall",
                    0.0 if ready else time.perf_counter() - wait_started,
                )
            else:
                payload = item
                telemetry.add_seconds("training_reducer_stall", 0.0)
            completed_but_blocked = sum(
                1
                for pending_item in pending.values()
                if not isinstance(pending_item, Future) or pending_item.done()
            )
            telemetry.observe(
                "training_completed_but_blocked_shards_per_reduction",
                completed_but_blocked,
            )
            telemetry.maximum(
                "training_completed_but_blocked_shards",
                completed_but_blocked,
            )
            pending_paths: list[Path] = []
            for pending_index in (document_index, *pending):
                pending_paths.extend(
                    _training_shard_paths(run_dir, pass_index, pending_index)
                )
            telemetry.maximum(
                "training_pending_shard_bytes",
                _existing_path_bytes(pending_paths),
            )
            metrics = _apply_training_shard(
                payload=payload,
                store=store,
                config=config,
                checkpoint=checkpoint,
                metrics=metrics,
                run_dir=run_dir,
                telemetry=telemetry,
            )
            fill_pending()
    parallel_seconds = time.perf_counter() - parallel_started
    telemetry.add_seconds('training_parallel_wall', parallel_seconds)
    telemetry.add_seconds('training_document_total', parallel_seconds)
    return metrics


def _parallel_training_bundles(
    *,
    pass_index: int,
    documents: tuple[CorpusDocument, ...],
    grammar: StructuredSandhiGrammar,
    store: LexiconStore,
    config: TrainingConfig,
    run_dir: Path,
    checkpoint: dict[str, Any],
    telemetry: RuntimeTelemetry,
    start_document: int,
    metrics: PassMetrics,
    vocabulary: FrozenVocabulary | None,
    plan: ExecutionBundlePlan,
) -> PassMetrics:
    """Run true inflight bundles while reducing documents canonically."""

    signature = _config_signature(config)
    parallel_started = telemetry.now()
    for document_index in range(start_document):
        _retire_training_bundle_shards(
            run_dir, pass_index, plan.by_document[document_index]
        )
        for path in _training_shard_paths(run_dir, pass_index, document_index):
            if path.is_file():
                path.unlink()

    existing_documents: dict[int, dict[str, Any]] = {}
    for document_index in range(start_document, len(documents)):
        payload = _load_training_shard(
            run_dir,
            pass_index,
            document_index,
            documents[document_index],
            signature,
        )
        if payload is not None:
            existing_documents[document_index] = payload

    todo = tuple(
        bundle
        for document_index in range(start_document, len(documents))
        if document_index not in existing_documents
        for bundle in plan.by_document[document_index]
    )
    repair_engine = ComposedPieceInference(
        NeutralPieceScorer(),
        model_config=config.piece_model_config,
        cache_config=config.piece_cache_config,
    )
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=config.workers,
        mp_context=context,
        initializer=_initialize_training_worker,
        initargs=(pass_index, store.path, config, vocabulary),
    ) as executor:
        max_inflight = config.workers * 2
        telemetry.maximum("training_pending_shard_limit", max_inflight)
        telemetry.maximum("training_bundle_inflight_limit", max_inflight)
        inflight: dict[Future[dict[str, Any]], ExecutionBundle] = {}
        ready: dict[tuple[int, int], dict[str, Any]] = {}
        validated_topology: set[int] = set()
        next_submit = 0
        reduction_document_index = start_document
        dispatch_error: BaseException | None = None
        dispatch_done = False
        dispatch_stop = False
        condition = threading.Condition()

        def fill_inflight() -> None:
            nonlocal next_submit
            while (
                next_submit < len(todo)
                and len(inflight) < max_inflight
                and (
                    todo[next_submit].document_index
                    <= reduction_document_index
                    or (
                        len(inflight)
                        + sum(
                            key[0] > reduction_document_index
                            for key in ready
                        )
                        < max_inflight * 2
                    )
                )
            ):
                bundle = todo[next_submit]
                document = documents[bundle.document_index]
                existing = _load_training_bundle_shard(
                    run_dir=run_dir,
                    pass_index=pass_index,
                    bundle=bundle,
                    document=document,
                    config_signature=signature,
                    plan_sha256=plan.plan_sha256,
                )
                if existing is not None:
                    ready[bundle.key] = existing
                    telemetry.increment("training_bundle_shards_resumed", 1)
                    next_submit += 1
                    continue
                if (
                    not COMPACT_EXACT_S1M2
                    and pass_index > 1
                    and bundle.document_index not in validated_topology
                ):
                    _validate_bundle_topology_archive(
                        document=document,
                        document_index=bundle.document_index,
                        config=config,
                        run_dir=run_dir,
                        config_signature=signature,
                        grammar=grammar,
                        piece_engine=repair_engine,
                        telemetry=telemetry,
                    )
                    validated_topology.add(bundle.document_index)
                future = executor.submit(
                    _write_training_bundle_shard,
                    bundle,
                    document,
                    config,
                    pass_index,
                    run_dir,
                    signature,
                    plan.plan_sha256,
                )
                inflight[future] = bundle
                next_submit += 1
            telemetry.maximum("training_pending_shards", len(inflight))
            telemetry.maximum("training_bundle_true_inflight", len(inflight))
            telemetry.maximum("training_bundle_ready_shards", len(ready))

        def dispatch() -> None:
            nonlocal dispatch_error, dispatch_done
            try:
                while True:
                    with condition:
                        if dispatch_stop:
                            return
                        fill_inflight()
                        if not inflight:
                            dispatch_done = next_submit == len(todo)
                            condition.notify_all()
                            if dispatch_done:
                                return
                            condition.wait()
                            continue
                        futures = tuple(inflight)
                    wait(futures, return_when=FIRST_COMPLETED)
                    with condition:
                        for future in tuple(item for item in inflight if item.done()):
                            bundle = inflight.pop(future)
                            ready[bundle.key] = future.result()
                        telemetry.observe("training_bundle_true_inflight", len(inflight))
                        telemetry.observe("training_bundle_ready_shards", len(ready))
                        condition.notify_all()
            except BaseException as error:
                with condition:
                    dispatch_error = error
                    condition.notify_all()

        dispatcher = threading.Thread(target=dispatch, name="s1m2-training-dispatch")
        dispatcher.start()
        try:
            for document_index in range(start_document, len(documents)):
                document_bundles = plan.by_document[document_index]
                compact_bundle_apply = False
                if document_index in existing_documents:
                    payload = existing_documents[document_index]
                    telemetry.add_seconds("training_reducer_stall", 0.0)
                else:
                    expected_keys = tuple(bundle.key for bundle in document_bundles)
                    wait_started = telemetry.now()
                    with condition:
                        while any(key not in ready for key in expected_keys):
                            if dispatch_error is not None:
                                raise dispatch_error
                            if dispatch_done:
                                raise RuntimeError(
                                    "Bundle scheduler exhausted work before "
                                    f"document {document_index} became ready."
                                )
                            condition.wait()
                        telemetry.add_seconds(
                            "training_reducer_stall",
                            time.perf_counter() - wait_started,
                        )
                        payloads = {key: ready[key] for key in expected_keys}
                    if COMPACT_EXACT_S1M2:
                        compact_bundle_apply = True
                    else:
                        payload = _coalesce_training_bundle_shards(
                            bundles=document_bundles,
                            payloads=payloads,
                            document=documents[document_index],
                            config=config,
                            pass_index=pass_index,
                            run_dir=run_dir,
                            config_signature=signature,
                        )
                if compact_bundle_apply:
                    metrics = _apply_compact_training_bundle_shards(
                        bundles=document_bundles,
                        payloads=payloads,
                        store=store,
                        config=config,
                        checkpoint=checkpoint,
                        metrics=metrics,
                        run_dir=run_dir,
                        pass_index=pass_index,
                        telemetry=telemetry,
                    )
                else:
                    metrics = _apply_training_shard(
                        payload=payload,
                        store=store,
                        config=config,
                        checkpoint=checkpoint,
                        metrics=metrics,
                        run_dir=run_dir,
                        telemetry=telemetry,
                    )
                _retire_training_bundle_shards(
                    run_dir, pass_index, document_bundles
                )
                with condition:
                    for bundle in document_bundles:
                        ready.pop(bundle.key, None)
                    reduction_document_index = document_index + 1
                    telemetry.observe("training_bundle_ready_shards", len(ready))
                    condition.notify_all()
        finally:
            with condition:
                dispatch_stop = True
                condition.notify_all()
            dispatcher.join()
        if dispatch_error is not None:
            raise dispatch_error

    parallel_seconds = time.perf_counter() - parallel_started
    telemetry.add_seconds("training_parallel_wall", parallel_seconds)
    telemetry.add_seconds("training_document_total", parallel_seconds)
    return metrics


def _training_pass(
    *,
    pass_index: int,
    documents: tuple[CorpusDocument, ...],
    grammar: StructuredSandhiGrammar,
    store: LexiconStore,
    config: TrainingConfig,
    run_dir: Path,
    checkpoint: dict[str, Any],
    telemetry: RuntimeTelemetry,
    execution_plan: ExecutionBundlePlan | None = None,
) -> dict[str, Any]:
    resuming = checkpoint.get("active_pass") == pass_index
    start_document = int(checkpoint.get("next_document_index", 0)) if resuming else 0
    metrics = _metrics_from_mapping(checkpoint.get("active_metrics") if resuming else None)
    vocabulary = store.load_frozen_vocabulary()
    if config.vocab_budget is not None and pass_index > 1 and vocabulary is None:
        raise RuntimeError("Pass 2+ requires the frozen pass-1 vocabulary.")
    scorer = None
    piece_engine = None
    if config.workers == 1:
        if config.model == S1M1_MODEL:
            scorer = (
                NeutralFormScorer()
                if pass_index == 1
                else store.scorer(
                    alpha=config.lexical_alpha,
                    complexity_weight=config.complexity_weight,
                    complexity_tau=config.complexity_tau,
                    cache_size=config.lexicon_cache_size,
                )
            )
        else:
            piece_scorer = (
                NeutralPieceScorer()
                if pass_index == 1
                else store.piece_scorer(
                    alpha=config.piece_alpha,
                    complexity_weight=config.piece_complexity_weight,
                    complexity_kappa=config.piece_complexity_kappa,
                    complexity_beta=config.piece_complexity_beta,
                    complexity_tau=config.piece_complexity_tau,
                    base_stop_probability=config.piece_base_stop_probability,
                    cache_size=config.lexicon_cache_size,
                )
            )
            piece_engine = ComposedPieceInference(
                piece_scorer,
                model_config=config.piece_model_config,
                cache_config=config.piece_cache_config,
            )
    checkpoint.update(
        {
            "active_pass": pass_index,
            "next_document_index": start_document,
            "active_metrics": asdict(metrics),
        }
    )
    if config.model == S1M1_MODEL:
        store.begin_count_pass(resume=resuming, checkpoint=checkpoint)
    else:
        store.begin_piece_count_pass(resume=resuming, checkpoint=checkpoint)
    _timed_checkpoint(run_dir, checkpoint, telemetry)

    if config.workers > 1:
        if execution_plan is None:
            metrics = _parallel_training_documents(
                pass_index=pass_index,
                documents=documents,
                store=store,
                config=config,
                run_dir=run_dir,
                checkpoint=checkpoint,
                telemetry=telemetry,
                start_document=start_document,
                metrics=metrics,
                vocabulary=vocabulary,
            )
        else:
            metrics = _parallel_training_bundles(
                pass_index=pass_index,
                documents=documents,
                grammar=grammar,
                store=store,
                config=config,
                run_dir=run_dir,
                checkpoint=checkpoint,
                telemetry=telemetry,
                start_document=start_document,
                metrics=metrics,
                vocabulary=vocabulary,
                plan=execution_plan,
            )
        start_document = len(documents)

    for document_index in range(start_document, len(documents)):
        document = documents[document_index]
        counts: Counter[PhonologicalForm] = Counter()
        piece_counts: Counter[PhonologicalForm] = Counter()
        piece_support: Counter[PhonologicalForm] = Counter()
        seen_lines: set[int] = set()
        document_metrics = PassMetrics()
        document_started = telemetry.now()
        topology_path = _topology_archive_path(run_dir, document_index)
        topology_temporary = topology_path.with_suffix(
            topology_path.suffix + ".tmp"
        )
        topology_writer: TopologyArchiveWriter | None = None
        topology_reader: ReconstructibleTopologyArchiveReader | None = None
        store.begin_document_counts()
        try:
            if config.model == S1M2_MODEL and not COMPACT_EXACT_S1M2:
                header = _topology_archive_header(
                    _config_signature(config), document_index, document
                )
                if pass_index == 1:
                    if topology_temporary.exists():
                        topology_temporary.unlink()
                    topology_writer = TopologyArchiveWriter(
                        topology_temporary, header
                    )
                else:
                    assert piece_engine is not None
                    topology_reader = _open_reconstructible_topology_archive(
                        document=document,
                        document_index=document_index,
                        config=config,
                        run_dir=run_dir,
                        config_signature=_config_signature(config),
                        grammar=grammar,
                        piece_engine=piece_engine,
                        telemetry=telemetry,
                    )
            for line_number, segment_index, segment in _profiled_document_segments(
                document,
                config,
                telemetry,
                phase='training',
            ):
                seen_lines.add(line_number)
                started = telemetry.now()
                candidate_profile = (
                    CandidateBuildProfile()
                    if config.model == S1M2_MODEL
                    else None
                )
                if config.model == S1M1_MODEL:
                    graph = build_candidate_graph(
                        segment,
                        grammar,
                        config.candidate_config,
                    )
                else:
                    graph = build_lazy_candidate_graph(
                        segment,
                        grammar,
                        config.candidate_config,
                        profile=candidate_profile,
                    )
                telemetry.elapsed('training_candidate_generation', started)
                candidate_counts = (
                    candidate_graph_statistics(graph)
                    if config.model == S1M1_MODEL
                    else lazy_candidate_graph_statistics(graph)
                )
                if candidate_profile is not None:
                    _record_candidate_telemetry(
                        telemetry,
                        candidate_profile,
                        candidate_counts,
                        phase="training",
                    )
                segment_topology = None
                if config.model == S1M2_MODEL and not COMPACT_EXACT_S1M2:
                    assert piece_engine is not None
                    if topology_writer is not None:
                        segment_topology = compile_composed_segment_topology(
                            graph, piece_engine
                        )
                        topology_writer.write(
                            line_number, segment_index, segment_topology
                        )
                    else:
                        assert topology_reader is not None
                        segment_topology = topology_reader.read(
                            line_number, segment_index
                        )
                started = telemetry.now()
                if config.model == S1M1_MODEL:
                    assert scorer is not None
                    inference = infer_training_segment(
                        graph,
                        scorer,
                        whitespace_merge_penalty=config.whitespace_merge_penalty,
                        vocabulary=vocabulary,
                    )
                else:
                    assert piece_engine is not None
                    inference = infer_composed_segment(
                        graph,
                        piece_engine,
                        whitespace_merge_penalty=config.whitespace_merge_penalty,
                        support_epsilon=config.piece_support_epsilon,
                        topology=segment_topology,
                    )
                    _record_composed_telemetry(
                        telemetry,
                        inference.counters,
                        phase="training",
                        timings=inference.timings,
                    )
                telemetry.elapsed('training_inference', started)
                started = telemetry.now()
                counts.update(
                    inference.expected_counts
                    if config.model == S1M1_MODEL
                    else inference.lexical_expected_counts
                )
                if config.model == S1M2_MODEL:
                    piece_counts.update(inference.piece_expected_counts)
                    piece_support.update(inference.piece_occurrence_support)
                telemetry.elapsed('training_count_aggregation', started)
                document_metrics.update(
                    segment,
                    inference,
                    overflowed_tokens=graph.overflowed_tokens,
                    candidate_factors=candidate_counts["factors"],
                    candidate_nodes=candidate_counts["lattice_nodes"],
                    candidate_edges=(
                        candidate_counts["lexical_edges"]
                        if config.model == S1M1_MODEL
                        else candidate_counts["lexical_span_hypotheses"]
                    ),
                )
                if len(counts) + len(piece_counts) >= config.flush_types:
                    if config.model == S1M1_MODEL:
                        _flush_counts(
                            store,
                            counts,
                            document_transaction=True,
                        )
                    else:
                        _flush_piece_training_counts(
                            store, counts, piece_counts, piece_support
                        )
            if config.model == S1M1_MODEL:
                _flush_counts(
                    store,
                    counts,
                    document_transaction=True,
                )
            else:
                _flush_piece_training_counts(
                    store, counts, piece_counts, piece_support
                )
            if topology_writer is not None:
                topology_writer.close()
                _replace_file(topology_temporary, topology_path)
                telemetry.increment("topology_archives_compiled", 1)
                telemetry.increment(
                    "topology_records_compiled", topology_writer.records
                )
                telemetry.increment(
                    "topology_uncompressed_bytes",
                    topology_writer.uncompressed_bytes,
                )
                telemetry.maximum(
                    "topology_archive_bytes", topology_path.stat().st_size
                )
            elif topology_reader is not None:
                topology_reader.close()
                telemetry.increment("topology_archives_reused", 1)
                telemetry.increment(
                    "topology_records_reused", topology_reader.records
                )
            document_metrics.documents = 1
            document_metrics.lines = len(seen_lines)
            next_metrics = metrics.merged(document_metrics)
            next_checkpoint = {
                **checkpoint,
                "active_pass": pass_index,
                "next_document_index": document_index + 1,
                "active_metrics": asdict(next_metrics),
            }
            store.commit_document(next_checkpoint)
            _record_store_storage(telemetry, store.path)
        except BaseException:
            if topology_writer is not None:
                topology_writer.close()
            if topology_reader is not None:
                topology_reader.close(require_eof=False)
            store.rollback_document()
            raise
        metrics = next_metrics
        checkpoint.update(next_checkpoint)
        telemetry.elapsed('training_document_total', document_started)
        _timed_checkpoint(run_dir, checkpoint, telemetry)

    if config.vocab_budget is not None:
        if pass_index == 1:
            vocabulary = store.select_and_freeze_vocabulary(config.vocab_budget)
        if vocabulary is None:
            raise RuntimeError("Constrained pass has no frozen vocabulary.")
        store.ensure_frozen_count_keys(vocabulary)
        checkpoint["vocabulary_budget"] = vocabulary.checkpoint_payload()
        _materialize_vocabulary_artifacts(run_dir, vocabulary)

    count_table = (
        "counts_next" if config.model == S1M1_MODEL else "piece_counts_next"
    )
    row = store.connection.execute(
        f"SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0) FROM {count_table}"
    ).fetchone()
    assert row is not None
    vocabulary_size = int(row[0])
    total_count = float(row[1])
    summary = metrics.summary(pass_index)
    if config.model == S1M1_MODEL:
        summary["lexicon_types"] = vocabulary_size
        summary["lexical_count_total"] = total_count
    else:
        summary["piece_types"] = vocabulary_size
        summary["piece_count_total"] = total_count
    checkpoint["history"].append(summary)
    checkpoint.update(
        {
            "completed_passes": pass_index,
            "active_pass": None,
            "next_document_index": 0,
            "active_metrics": None,
        }
    )
    started = telemetry.now()
    if config.model == S1M1_MODEL:
        store.finalize_count_pass(
            alpha=config.lexical_alpha,
            checkpoint=checkpoint,
        )
        telemetry.elapsed('lexicon_finalize', started)
    else:
        all_types, active_types, active_total = store.finalize_piece_count_pass(
            min_reuse_occurrences=config.piece_min_reuse_occurrences,
            checkpoint=checkpoint,
        )
        summary["piece_types"] = all_types
        summary["active_piece_types"] = active_types
        summary["active_piece_count_total"] = active_total
        checkpoint["history"][-1].update(
            {
                "piece_types": all_types,
                "active_piece_types": active_types,
                "active_piece_count_total": active_total,
            }
        )
        telemetry.elapsed('piece_finalize', started)
    _timed_checkpoint(run_dir, checkpoint, telemetry)
    return summary


def _analysis_payload(analysis: AnalysisPosterior) -> dict[str, Any]:
    return {
        "latent_units": [
            {
                "form_key": word.key,
                "iast": word.iast,
                "phoneme_ids": list(word.phoneme_ids),
            }
            for word in analysis.words
        ],
        "debug_serialization": " | ".join(word.iast for word in analysis.words),
        "posterior": analysis.probability,
        "log_score": analysis.log_score,
        "rule_ids": list(analysis.rule_ids),
        "boundaries": [
            {
                "boundary_id": boundary.boundary_id,
                "cue_kind": boundary.cue_kind,
                "source_start": boundary.source_start,
                "source_end": boundary.source_end,
            }
            for boundary in analysis.boundaries
        ],
    }


def _composed_analysis_payload(
    analysis: ComposedAnalysisPosterior,
) -> dict[str, Any]:
    payload = _analysis_payload(analysis)  # identical outer presentation fields
    payload["piece_segmentations"] = [
        [
            {
                "piece_key": piece.key,
                "iast": piece.iast,
                "phoneme_ids": list(piece.phoneme_ids),
            }
            for piece in segmentation
        ]
        for segmentation in analysis.piece_segmentations
    ]
    return payload


def _boundary_posterior_payload(item: BoundaryPosterior) -> dict[str, Any]:
    return {
        "boundary_id": item.boundary_id,
        "cue_kind": item.cue_kind,
        "source_start": item.source_start,
        "source_end": item.source_end,
        "probability": item.probability,
    }


def _push_report(
    heap: list[tuple[float, int, dict[str, Any]]],
    score: float,
    serial: int,
    payload: dict[str, Any],
    *,
    limit: int = 20,
) -> None:
    item = (float(score), serial, payload)
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif item[:2] > heap[0][:2]:
        heapq.heapreplace(heap, item)


def _sorted_report(
    heap: list[tuple[float, int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [item[2] for item in sorted(heap, reverse=True)]


@dataclass(slots=True)
class _InspectionAggregate:
    metrics: PassMetrics = field(default_factory=PassMetrics)
    rule_usage: Counter[str] = field(default_factory=Counter)
    top1_sum: float = 0.0
    entropy_sum: float = 0.0
    high_confidence: list[tuple[float, int, dict[str, Any]]] = field(
        default_factory=list
    )
    ambiguous: list[tuple[float, int, dict[str, Any]]] = field(default_factory=list)
    shifts: list[tuple[float, int, dict[str, Any]]] = field(default_factory=list)
    serial: int = 0


_INSPECTION_STREAM_SHARD_KINDS = (
    "analyses",
    "boundaries",
    "reductions",
)
_INSPECTION_AGGREGATE_FORMAT = "ordered_sqlite_v1"
_INSPECTION_SHARD_KINDS = (
    *_INSPECTION_STREAM_SHARD_KINDS,
    "aggregates",
)
_LEGACY_INSPECTION_SHARD_KINDS = (
    "analyses",
    "boundaries",
    "counts",
    "pieces",
    "surfaces",
    "contexts",
    "reductions",
)
_S1M2_CANONICAL_SCIENTIFIC_ARTIFACTS = (
    "iteration_metrics.json",
    "piece_inventory.tsv",
    "lexical_diagnostics.tsv",
    "analyses.jsonl",
    "boundary_posteriors.jsonl",
    "rule_usage.tsv",
    "summary.json",
)


def _inspection_shard_paths(
    run_dir: Path,
    document_index: int,
) -> dict[str, Path]:
    root = run_dir / "shards" / "inspection"
    stem = f"document_{document_index:08d}"
    return {
        "analyses": root / f"{stem}.analyses.jsonl",
        "boundaries": root / f"{stem}.boundaries.jsonl",
        "aggregates": root / f"{stem}.aggregates.sqlite",
        "counts": root / f"{stem}.counts.tsv",
        "pieces": root / f"{stem}.pieces.tsv",
        "surfaces": root / f"{stem}.surfaces.tsv",
        "contexts": root / f"{stem}.contexts.tsv",
        "reductions": root / f"{stem}.reductions.jsonl",
        "marker": root / f"{stem}.complete.json",
    }


def _inspection_bundle_paths(
    run_dir: Path,
    bundle: ExecutionBundle,
) -> dict[str, Path]:
    root = run_dir / "shards" / "inspection" / "bundles"
    stem = (
        f"document_{bundle.document_index:08d}."
        f"bundle_{bundle.bundle_index:06d}"
    )
    return {
        "segments": root / f"{stem}.segments.jsonl",
        "marker": root / f"{stem}.complete.json",
    }


def _initialize_inspection_worker(
    database_path: Path,
    config: TrainingConfig,
    vocabulary: FrozenVocabulary | None,
) -> None:
    global _WORKER_PIECE_ENGINE
    _initialize_training_worker(2, database_path, config, vocabulary)
    if config.model == S1M2_MODEL:
        assert _WORKER_PIECE_ENGINE is not None
        _WORKER_PIECE_ENGINE = ComposedPieceInference(
            _WORKER_PIECE_ENGINE.scorer,
            model_config=config.piece_model_config,
            cache_config=config.piece_cache_config,
            inspection_top_k=config.analysis_top_k,
        )


def _write_inspection_shard(
    document_index: int,
    document: CorpusDocument,
    config: TrainingConfig,
    run_dir: Path,
    config_signature: str,
) -> dict[str, Any]:
    if _WORKER_GRAMMAR is None or (
        config.model == S1M1_MODEL and _WORKER_SCORER is None
    ) or (
        config.model == S1M2_MODEL and _WORKER_PIECE_ENGINE is None
    ):
        raise RuntimeError("Inspection worker was not initialized.")
    paths = _inspection_shard_paths(run_dir, document_index)
    paths["marker"].parent.mkdir(parents=True, exist_ok=True)
    shard_kinds = (
        _INSPECTION_SHARD_KINDS
        if config.model == S1M2_MODEL
        else _LEGACY_INSPECTION_SHARD_KINDS
    )
    temporary = {
        kind: paths[kind].with_suffix(paths[kind].suffix + ".tmp")
        for kind in shard_kinds
    }
    counts: Counter[PhonologicalForm] = Counter()
    piece_counts: Counter[PhonologicalForm] = Counter()
    piece_support: Counter[PhonologicalForm] = Counter()
    seen_lines: set[int] = set()
    count_rows = 0
    piece_rows = 0
    surface_rows = 0
    context_rows = 0
    reduction_rows = 0
    candidate_seconds = 0.0
    inference_seconds = 0.0
    aggregation_seconds = 0.0
    frontend_seconds = 0.0
    serialization_seconds = 0.0
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    active_scorer = (
        _WORKER_SCORER
        if config.model == S1M1_MODEL
        else _WORKER_PIECE_ENGINE.scorer
    )
    scorer_calls_before = int(getattr(active_scorer, "score_calls", 0))
    sqlite_selects_before = int(getattr(active_scorer, "sqlite_selects", 0))
    sqlite_seconds_before = float(getattr(active_scorer, "sqlite_seconds", 0.0))
    piece_counters_before = (
        _WORKER_PIECE_ENGINE.counter_snapshot()
        if config.model == S1M2_MODEL
        else None
    )
    engineering = RuntimeTelemetry()
    aggregate_row_numbers = {
        "counts": 0,
        "pieces": 0,
        "surfaces": 0,
        "contexts": 0,
    }
    surface_rows_buffer: list[tuple[str, str, float]] = []
    context_rows_buffer: list[tuple[str, str, float]] = []
    shard_database_seconds = 0.0

    aggregate_temporary = temporary.get("aggregates")
    aggregate_connection = None
    if aggregate_temporary is not None:
        if aggregate_temporary.exists():
            aggregate_temporary.unlink()
        aggregate_connection = sqlite3.connect(aggregate_temporary)
        aggregate_connection.execute("PRAGMA journal_mode=OFF")
        aggregate_connection.execute("PRAGMA synchronous=OFF")
        aggregate_connection.execute("PRAGMA temp_store=MEMORY")
        aggregate_connection.executescript(
            "CREATE TABLE count_rows ("
            "row_number INTEGER PRIMARY KEY, form_key TEXT NOT NULL, "
            "expected_count REAL NOT NULL);"
            "CREATE TABLE piece_rows ("
            "row_number INTEGER PRIMARY KEY, form_key TEXT NOT NULL, "
            "expected_count REAL NOT NULL, occurrence_support INTEGER NOT NULL);"
            "CREATE TABLE surface_rows ("
            "row_number INTEGER PRIMARY KEY, form_key TEXT NOT NULL, "
            "surface TEXT NOT NULL, expected_mass REAL NOT NULL);"
            "CREATE TABLE context_rows ("
            "row_number INTEGER PRIMARY KEY, form_key TEXT NOT NULL, "
            "context TEXT NOT NULL, expected_mass REAL NOT NULL);"
        )

    def flush_counts() -> None:
        nonlocal count_rows, shard_database_seconds
        if not counts:
            return
        started = time.perf_counter()
        ordered = sorted(counts.items(), key=lambda item: item[0].key)
        if aggregate_connection is None:
            for form, value in ordered:
                handles["counts"].write(
                    f"{form.key}\t{float(value).hex()}\n"
                )
        else:
            rows = []
            for form, value in ordered:
                aggregate_row_numbers["counts"] += 1
                rows.append(
                    (aggregate_row_numbers["counts"], form.key, float(value))
                )
            aggregate_connection.executemany(
                "INSERT INTO count_rows VALUES (?, ?, ?)",
                rows,
            )
        count_rows += len(ordered)
        counts.clear()
        shard_database_seconds += time.perf_counter() - started

    def flush_pieces() -> None:
        nonlocal piece_rows, shard_database_seconds
        if not piece_counts:
            return
        assert aggregate_connection is not None
        started = time.perf_counter()
        rows = []
        for piece, value in sorted(
            piece_counts.items(), key=lambda item: item[0].key
        ):
            aggregate_row_numbers["pieces"] += 1
            rows.append(
                (
                    aggregate_row_numbers["pieces"],
                    piece.key,
                    float(value),
                    int(piece_support[piece]),
                )
            )
        aggregate_connection.executemany(
            "INSERT INTO piece_rows VALUES (?, ?, ?, ?)",
            rows,
        )
        piece_rows += len(rows)
        piece_counts.clear()
        piece_support.clear()
        shard_database_seconds += time.perf_counter() - started

    def flush_usage_rows() -> None:
        nonlocal shard_database_seconds
        if not surface_rows_buffer and not context_rows_buffer:
            return
        started = time.perf_counter()
        if aggregate_connection is None:
            for key, surface, mass in surface_rows_buffer:
                handles["surfaces"].write(
                    f"{key}\t{json.dumps(surface, ensure_ascii=False)}\t"
                    f"{float(mass).hex()}\n"
                )
            for key, context, mass in context_rows_buffer:
                handles["contexts"].write(
                    f"{key}\t{json.dumps(context, ensure_ascii=False)}\t"
                    f"{float(mass).hex()}\n"
                )
        else:
            surface_rows = []
            for key, surface, mass in surface_rows_buffer:
                aggregate_row_numbers["surfaces"] += 1
                surface_rows.append(
                    (
                        aggregate_row_numbers["surfaces"],
                        key,
                        surface,
                        float(mass),
                    )
                )
            context_rows = []
            for key, context, mass in context_rows_buffer:
                aggregate_row_numbers["contexts"] += 1
                context_rows.append(
                    (
                        aggregate_row_numbers["contexts"],
                        key,
                        context,
                        float(mass),
                    )
                )
            aggregate_connection.executemany(
                "INSERT INTO surface_rows VALUES (?, ?, ?, ?)",
                surface_rows,
            )
            aggregate_connection.executemany(
                "INSERT INTO context_rows VALUES (?, ?, ?, ?)",
                context_rows,
            )
        surface_rows_buffer.clear()
        context_rows_buffer.clear()
        shard_database_seconds += time.perf_counter() - started

    handles: dict[str, Any] = {}
    topology_reader: ReconstructibleTopologyArchiveReader | None = None
    try:
        stream_kinds = (
            _INSPECTION_STREAM_SHARD_KINDS
            if aggregate_connection is not None
            else _LEGACY_INSPECTION_SHARD_KINDS
        )
        for kind in stream_kinds:
            handles[kind] = temporary[kind].open(
                "w",
                encoding="utf-8",
                newline="",
            )
        if config.model == S1M2_MODEL and not COMPACT_EXACT_S1M2:
            assert _WORKER_GRAMMAR is not None
            assert _WORKER_PIECE_ENGINE is not None
            topology_reader = _open_reconstructible_topology_archive(
                document=document,
                document_index=document_index,
                config=config,
                run_dir=run_dir,
                config_signature=config_signature,
                grammar=_WORKER_GRAMMAR,
                piece_engine=_WORKER_PIECE_ENGINE,
                telemetry=engineering,
            )
        iterator = _iter_document_segments(document, config)
        while True:
            started = time.perf_counter()
            try:
                line_number, segment_index, segment = next(iterator)
            except StopIteration:
                frontend_seconds += time.perf_counter() - started
                break
            frontend_seconds += time.perf_counter() - started
            seen_lines.add(line_number)
            _observe_segment_telemetry(
                engineering,
                segment,
                config,
                phase="inspection",
            )
            started = time.perf_counter()
            candidate_profile = (
                CandidateBuildProfile() if config.model == S1M2_MODEL else None
            )
            if config.model == S1M1_MODEL:
                graph = build_candidate_graph(
                    segment,
                    _WORKER_GRAMMAR,
                    config.candidate_config,
                )
            else:
                graph = build_lazy_candidate_graph(
                    segment,
                    _WORKER_GRAMMAR,
                    config.candidate_config,
                    profile=candidate_profile,
                )
            candidate_seconds += time.perf_counter() - started
            candidate_values = (
                candidate_graph_statistics(graph)
                if config.model == S1M1_MODEL
                else lazy_candidate_graph_statistics(graph)
            )
            if candidate_profile is not None:
                _record_candidate_telemetry(
                    engineering,
                    candidate_profile,
                    candidate_values,
                    phase="inspection",
                )
            segment_topology = None
            if config.model == S1M2_MODEL and not COMPACT_EXACT_S1M2:
                assert topology_reader is not None
                segment_topology = topology_reader.read(
                    line_number, segment_index
                )
            started = time.perf_counter()
            if config.model == S1M1_MODEL:
                inference = infer_segment(
                    graph,
                    _WORKER_SCORER,
                    whitespace_merge_penalty=config.whitespace_merge_penalty,
                    top_k=config.analysis_top_k,
                    vocabulary=_WORKER_VOCABULARY,
                )
            else:
                inference = infer_composed_segment(
                    graph,
                    _WORKER_PIECE_ENGINE,
                    whitespace_merge_penalty=config.whitespace_merge_penalty,
                    support_epsilon=config.piece_support_epsilon,
                    topology=segment_topology,
                )
                _record_composed_timings(
                    engineering,
                    inference.timings,
                    phase="inspection",
                )
            inference_seconds += time.perf_counter() - started
            started = time.perf_counter()
            counts.update(
                inference.expected_counts
                if config.model == S1M1_MODEL
                else inference.lexical_expected_counts
            )
            if config.model == S1M2_MODEL:
                piece_counts.update(inference.piece_expected_counts)
                piece_support.update(inference.piece_occurrence_support)
            aggregation_seconds += time.perf_counter() - started

            serialization_started = time.perf_counter()
            segment_id = (
                f"{document.document_id}:l{line_number:08d}:"
                f"s{segment_index:04d}"
            )
            analysis_row = {
                "schema_version": 1 if config.model == S1M1_MODEL else 2,
                "segment_id": segment_id,
                "document": document.relative_path,
                "line_number": line_number,
                "source_start": segment.source_start,
                "source_end": segment.source_end,
                "surface": segment.written,
                "top_analyses": [
                    (
                        _analysis_payload(analysis)
                        if config.model == S1M1_MODEL
                        else _composed_analysis_payload(analysis)
                    )
                    for analysis in inference.top_analyses
                ],
                "top_analysis_mass": inference.top_analysis_mass,
                "residual_posterior": max(
                    0.0,
                    1.0 - inference.top_analysis_mass,
                ),
                "identity_mass": inference.identity_mass,
                "latent_mass": inference.latent_mass,
                "entropy": inference.entropy,
                "log_partition": inference.log_partition,
                "candidate_counts": candidate_values,
            }
            if isinstance(inference, ComposedSegmentInference):
                analysis_row["piece_posterior"] = {
                    "expected_piece_tokens": inference.expected_piece_tokens,
                    "segmentation_entropy": inference.piece_segmentation_entropy,
                    "whole_form_uses": inference.expected_whole_form_uses,
                    "singleton_path_uses": (
                        inference.expected_singleton_path_uses
                    ),
                    "multi_piece_uses": inference.expected_multi_piece_uses,
                }
            if config.equivalence_diagnostics:
                analysis_row["candidate_fingerprint"] = (
                    candidate_graph_fingerprint(graph)
                    if config.model == S1M1_MODEL
                    else _sha256_bytes(_canonical_json(candidate_values).encode("utf-8"))
                )
            handles["analyses"].write(
                json.dumps(analysis_row, ensure_ascii=False, sort_keys=True) + "\n"
            )
            boundary_row = {
                "schema_version": 1 if config.model == S1M1_MODEL else 2,
                "segment_id": segment_id,
                "surface": segment.written,
                "boundaries": [
                    _boundary_posterior_payload(item)
                    for item in inference.boundary_posteriors
                ],
            }
            handles["boundaries"].write(
                json.dumps(boundary_row, ensure_ascii=False, sort_keys=True) + "\n"
            )
            serialization_seconds += time.perf_counter() - serialization_started

            top_probability = (
                inference.top_analyses[0].probability
                if inference.top_analyses
                else 0.0
            )
            report_payload = {
                "segment_id": segment_id,
                "surface": segment.written,
                "analysis": (
                    " | ".join(
                        word.iast for word in inference.top_analyses[0].words
                    )
                    if inference.top_analyses
                    else ""
                ),
                "posterior": top_probability,
                "identity_mass": inference.identity_mass,
                "latent_mass": inference.latent_mass,
                "entropy": inference.entropy,
                "rule_ids": (
                    list(inference.top_analyses[0].rule_ids)
                    if inference.top_analyses
                    else []
                ),
            }
            reduction_row = {
                "characters": len(segment.written),
                "log_partition": inference.log_partition,
                "identity_mass": inference.identity_mass,
                "latent_mass": inference.latent_mass,
                "expected_lexical_tokens": inference.expected_lexical_tokens,
                "overflowed_tokens": graph.overflowed_tokens,
                "candidate_factors": candidate_values["factors"],
                "candidate_nodes": candidate_values["lattice_nodes"],
                "candidate_edges": (
                    candidate_values["lexical_edges"]
                    if config.model == S1M1_MODEL
                    else candidate_values["lexical_span_hypotheses"]
                ),
                "expected_piece_tokens": getattr(
                    inference, "expected_piece_tokens", 0.0
                ),
                "piece_segmentation_entropy": getattr(
                    inference, "piece_segmentation_entropy", 0.0
                ),
                "expected_whole_form_uses": getattr(
                    inference, "expected_whole_form_uses", 0.0
                ),
                "expected_singleton_path_uses": getattr(
                    inference, "expected_singleton_path_uses", 0.0
                ),
                "expected_multi_piece_uses": getattr(
                    inference, "expected_multi_piece_uses", 0.0
                ),
                "top_probability": top_probability,
                "entropy": inference.entropy,
                "rule_usage": dict(inference.rule_usage),
                "composed_counters": (
                    asdict(inference.counters)
                    if isinstance(inference, ComposedSegmentInference)
                    else {}
                ),
                "report": report_payload,
            }
            handles["reductions"].write(
                json.dumps(reduction_row, ensure_ascii=False, sort_keys=True) + "\n"
            )
            reduction_rows += 1

            inference_lexical_counts = (
                inference.expected_counts
                if config.model == S1M1_MODEL
                else inference.lexical_expected_counts
            )
            for form, mass in inference_lexical_counts.items():
                if mass >= config.usage_posterior_threshold:
                    if aggregate_connection is None:
                        surface = json.dumps(
                            segment.written,
                            ensure_ascii=False,
                        )
                        handles["surfaces"].write(
                            f"{form.key}\t{surface}\t{float(mass).hex()}\n"
                        )
                    else:
                        surface_rows_buffer.append(
                            (form.key, segment.written, float(mass))
                        )
                    surface_rows += 1
            for analysis in inference.top_analyses:
                if analysis.probability < config.usage_posterior_threshold:
                    continue
                for word_index, word in enumerate(analysis.words):
                    left = (
                        analysis.words[word_index - 1].key
                        if word_index
                        else "<BOS>"
                    )
                    right = (
                        analysis.words[word_index + 1].key
                        if word_index + 1 < len(analysis.words)
                        else "<EOS>"
                    )
                    context = f"{left}>{right}"
                    if aggregate_connection is None:
                        encoded_context = json.dumps(
                            context,
                            ensure_ascii=False,
                        )
                        handles["contexts"].write(
                            f"{word.key}\t{encoded_context}\t"
                            f"{float(analysis.probability).hex()}\n"
                        )
                    else:
                        context_rows_buffer.append(
                            (word.key, context, float(analysis.probability))
                        )
                    context_rows += 1
            if len(counts) + len(piece_counts) >= config.flush_types:
                flush_counts()
                flush_pieces()
            if len(surface_rows_buffer) + len(context_rows_buffer) >= config.flush_types:
                flush_usage_rows()
        flush_counts()
        flush_pieces()
        flush_usage_rows()
        for handle in handles.values():
            handle.flush()
            os.fsync(handle.fileno())
        if topology_reader is not None:
            topology_reader.close()
            engineering.increment("topology_archives_reused", 1)
            engineering.increment(
                "topology_records_reused", topology_reader.records
            )
    finally:
        if topology_reader is not None:
            topology_reader.close(require_eof=False)
        for handle in handles.values():
            handle.close()
        if aggregate_connection is not None:
            aggregate_connection.commit()
            aggregate_connection.close()
    for kind in stream_kinds:
        _replace_file(temporary[kind], paths[kind])
    if aggregate_temporary is not None:
        _replace_file(aggregate_temporary, paths["aggregates"])
    payload = {
        "schema_version": 2 if aggregate_connection is not None else 1,
        "config_signature": config_signature,
        "document_index": document_index,
        "relative_path": document.relative_path,
        "lines": len(seen_lines),
        "rows": {
            "counts": count_rows,
            "pieces": piece_rows,
            "surfaces": surface_rows,
            "contexts": context_rows,
            "reductions": reduction_rows,
        },
        "sha256": {
            kind: _file_sha256(paths[kind]) for kind in shard_kinds
        },
        "runtime": {
            "inspection_candidate_generation": candidate_seconds,
            "inspection_inference": inference_seconds,
            "inspection_count_aggregation": aggregation_seconds,
            "inspection_frontend_io": frontend_seconds,
            "inspection_serialization": serialization_seconds,
            "inspection_worker_document_total": time.perf_counter() - wall_started,
            "inspection_worker_cpu": time.process_time() - cpu_started,
            "lexical_score_calls": (
                int(getattr(active_scorer, "score_calls", 0))
                - scorer_calls_before
            ),
            "sqlite_selects": (
                int(getattr(active_scorer, "sqlite_selects", 0))
                - sqlite_selects_before
            ),
            "sqlite_seconds": (
                float(getattr(active_scorer, "sqlite_seconds", 0.0))
                - sqlite_seconds_before
            ),
            "composed_counters": (
                asdict(
                    _WORKER_PIECE_ENGINE.counter_delta(piece_counters_before)
                )
                if piece_counters_before is not None
                else {}
            ),
            "engineering_telemetry": engineering.payload(),
        },
    }
    if aggregate_connection is not None:
        payload["aggregate_format"] = _INSPECTION_AGGREGATE_FORMAT
        payload["runtime"]["inspection_worker_shard_database"] = (
            shard_database_seconds
        )
    _write_json(paths["marker"], payload)
    return payload


def _write_inspection_bundle_shard(
    bundle: ExecutionBundle,
    document: CorpusDocument,
    config: TrainingConfig,
    run_dir: Path,
    config_signature: str,
    plan_sha256: str,
) -> dict[str, Any]:
    """Compute one atomic segment range into an execution-only shard."""

    if _WORKER_GRAMMAR is None or _WORKER_PIECE_ENGINE is None:
        raise RuntimeError("S1M2 inspection bundle worker was not initialized.")
    paths = _inspection_bundle_paths(run_dir, bundle)
    paths["segments"].parent.mkdir(parents=True, exist_ok=True)
    temporary = paths["segments"].with_suffix(".jsonl.tmp")
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    candidate_seconds = 0.0
    inference_seconds = 0.0
    aggregation_seconds = 0.0
    frontend_seconds = 0.0
    serialization_seconds = 0.0
    active_scorer = _WORKER_PIECE_ENGINE.scorer
    scorer_calls_before = int(getattr(active_scorer, "score_calls", 0))
    sqlite_selects_before = int(getattr(active_scorer, "sqlite_selects", 0))
    sqlite_seconds_before = float(getattr(active_scorer, "sqlite_seconds", 0.0))
    piece_counters_before = _WORKER_PIECE_ENGINE.counter_snapshot()
    engineering = RuntimeTelemetry()
    records = 0
    first_identity: tuple[int, int] | None = None
    last_identity: tuple[int, int] | None = None
    topology_reader: TopologyArchiveReader | None = None
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            iterator = _iter_execution_bundle_segments(document, config, bundle)
            while True:
                started = time.perf_counter()
                try:
                    line_number, segment_index, segment = next(iterator)
                except StopIteration:
                    frontend_seconds += time.perf_counter() - started
                    break
                frontend_seconds += time.perf_counter() - started
                identity = (line_number, segment_index)
                if first_identity is None:
                    first_identity = identity
                last_identity = identity
                _observe_segment_telemetry(
                    engineering, segment, config, phase="inspection"
                )

                started = time.perf_counter()
                candidate_profile = CandidateBuildProfile()
                graph = build_lazy_candidate_graph(
                    segment,
                    _WORKER_GRAMMAR,
                    config.candidate_config,
                    profile=candidate_profile,
                )
                candidate_seconds += time.perf_counter() - started
                candidate_values = lazy_candidate_graph_statistics(graph)
                _record_candidate_telemetry(
                    engineering,
                    candidate_profile,
                    candidate_values,
                    phase="inspection",
                )
                topology = None

                started = time.perf_counter()
                inference = infer_composed_segment(
                    graph,
                    _WORKER_PIECE_ENGINE,
                    whitespace_merge_penalty=config.whitespace_merge_penalty,
                    support_epsilon=config.piece_support_epsilon,
                    topology=topology,
                )
                _record_composed_timings(
                    engineering, inference.timings, phase="inspection"
                )
                inference_seconds += time.perf_counter() - started

                serialization_started = time.perf_counter()
                segment_id = (
                    f"{document.document_id}:l{line_number:08d}:"
                    f"s{segment_index:04d}"
                )
                analysis_row = {
                    "schema_version": 2,
                    "segment_id": segment_id,
                    "document": document.relative_path,
                    "line_number": line_number,
                    "source_start": segment.source_start,
                    "source_end": segment.source_end,
                    "surface": segment.written,
                    "top_analyses": [
                        _composed_analysis_payload(analysis)
                        for analysis in inference.top_analyses
                    ],
                    "top_analysis_mass": inference.top_analysis_mass,
                    "residual_posterior": max(
                        0.0, 1.0 - inference.top_analysis_mass
                    ),
                    "identity_mass": inference.identity_mass,
                    "latent_mass": inference.latent_mass,
                    "entropy": inference.entropy,
                    "log_partition": inference.log_partition,
                    "candidate_counts": candidate_values,
                    "piece_posterior": {
                        "expected_piece_tokens": inference.expected_piece_tokens,
                        "segmentation_entropy": (
                            inference.piece_segmentation_entropy
                        ),
                        "whole_form_uses": inference.expected_whole_form_uses,
                        "singleton_path_uses": (
                            inference.expected_singleton_path_uses
                        ),
                        "multi_piece_uses": inference.expected_multi_piece_uses,
                    },
                }
                if config.equivalence_diagnostics:
                    analysis_row["candidate_fingerprint"] = _sha256_bytes(
                        _canonical_json(candidate_values).encode("utf-8")
                    )
                boundary_row = {
                    "schema_version": 2,
                    "segment_id": segment_id,
                    "surface": segment.written,
                    "boundaries": [
                        _boundary_posterior_payload(item)
                        for item in inference.boundary_posteriors
                    ],
                }
                top_probability = (
                    inference.top_analyses[0].probability
                    if inference.top_analyses
                    else 0.0
                )
                report_payload = {
                    "segment_id": segment_id,
                    "surface": segment.written,
                    "analysis": (
                        " | ".join(
                            word.iast for word in inference.top_analyses[0].words
                        )
                        if inference.top_analyses
                        else ""
                    ),
                    "posterior": top_probability,
                    "identity_mass": inference.identity_mass,
                    "latent_mass": inference.latent_mass,
                    "entropy": inference.entropy,
                    "rule_ids": (
                        list(inference.top_analyses[0].rule_ids)
                        if inference.top_analyses
                        else []
                    ),
                }
                reduction_row = {
                    "characters": len(segment.written),
                    "log_partition": inference.log_partition,
                    "identity_mass": inference.identity_mass,
                    "latent_mass": inference.latent_mass,
                    "expected_lexical_tokens": inference.expected_lexical_tokens,
                    "overflowed_tokens": graph.overflowed_tokens,
                    "candidate_factors": candidate_values["factors"],
                    "candidate_nodes": candidate_values["lattice_nodes"],
                    "candidate_edges": candidate_values[
                        "lexical_span_hypotheses"
                    ],
                    "expected_piece_tokens": inference.expected_piece_tokens,
                    "piece_segmentation_entropy": (
                        inference.piece_segmentation_entropy
                    ),
                    "expected_whole_form_uses": (
                        inference.expected_whole_form_uses
                    ),
                    "expected_singleton_path_uses": (
                        inference.expected_singleton_path_uses
                    ),
                    "expected_multi_piece_uses": (
                        inference.expected_multi_piece_uses
                    ),
                    "top_probability": top_probability,
                    "entropy": inference.entropy,
                    "rule_usage": dict(inference.rule_usage),
                    "composed_counters": asdict(inference.counters),
                    "report": report_payload,
                }

                started = time.perf_counter()
                surface_usage = [
                    (form.key, segment.written, float(mass).hex())
                    for form, mass in inference.lexical_expected_counts.items()
                    if mass >= config.usage_posterior_threshold
                ]
                context_usage = []
                for analysis in inference.top_analyses:
                    if analysis.probability < config.usage_posterior_threshold:
                        continue
                    for word_index, word in enumerate(analysis.words):
                        left = (
                            analysis.words[word_index - 1].key
                            if word_index
                            else "<BOS>"
                        )
                        right = (
                            analysis.words[word_index + 1].key
                            if word_index + 1 < len(analysis.words)
                            else "<EOS>"
                        )
                        context_usage.append(
                            (
                                word.key,
                                f"{left}>{right}",
                                float(analysis.probability).hex(),
                            )
                        )
                record = {
                    "schema_version": "sktlm-s1m2-inspection-segment-result/v1",
                    "line_number": line_number,
                    "segment_index": segment_index,
                    "analysis": analysis_row,
                    "boundary": boundary_row,
                    "reduction": reduction_row,
                    "lexical_counts": [
                        (form.key, float(value).hex())
                        for form, value in inference.lexical_expected_counts.items()
                    ],
                    "piece_counts": [
                        (
                            piece.key,
                            float(value).hex(),
                            int(inference.piece_occurrence_support[piece]),
                        )
                        for piece, value in inference.piece_expected_counts.items()
                    ],
                    "surface_usage": surface_usage,
                    "context_usage": context_usage,
                }
                aggregation_seconds += time.perf_counter() - started
                handle.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                serialization_seconds += (
                    time.perf_counter() - serialization_started
                )
                records += 1
            handle.flush()
            os.fsync(handle.fileno())
        _replace_file(temporary, paths["segments"])
        payload = {
            "schema_version": "sktlm-s1m2-inspection-bundle-shard/v1",
            "config_signature": config_signature,
            "plan_sha256": plan_sha256,
            "document_index": bundle.document_index,
            "relative_path": document.relative_path,
            "bundle_index": bundle.bundle_index,
            "first_segment_ordinal": bundle.first_segment_ordinal,
            "last_segment_ordinal_exclusive": (
                bundle.last_segment_ordinal_exclusive
            ),
            "first_line_number": bundle.first_line_number,
            "first_segment_index": bundle.first_segment_index,
            "last_line_number": bundle.last_line_number,
            "last_segment_index": bundle.last_segment_index,
            "segment_count": records,
            "segment_shard_sha256": _file_sha256(paths["segments"]),
            "runtime": {
                "inspection_candidate_generation": candidate_seconds,
                "inspection_inference": inference_seconds,
                "inspection_count_aggregation": aggregation_seconds,
                "inspection_frontend_io": frontend_seconds,
                "inspection_serialization": serialization_seconds,
                "inspection_worker_bundle_total": (
                    time.perf_counter() - wall_started
                ),
                "inspection_worker_cpu": time.process_time() - cpu_started,
                "lexical_score_calls": (
                    int(getattr(active_scorer, "score_calls", 0))
                    - scorer_calls_before
                ),
                "sqlite_selects": (
                    int(getattr(active_scorer, "sqlite_selects", 0))
                    - sqlite_selects_before
                ),
                "sqlite_seconds": (
                    float(getattr(active_scorer, "sqlite_seconds", 0.0))
                    - sqlite_seconds_before
                ),
                "composed_counters": asdict(
                    _WORKER_PIECE_ENGINE.counter_delta(piece_counters_before)
                ),
                "engineering_telemetry": engineering.payload(),
            },
        }
        if (
            records != bundle.segment_count
            or first_identity
            != (bundle.first_line_number, bundle.first_segment_index)
            or last_identity
            != (bundle.last_line_number, bundle.last_segment_index)
        ):
            raise RuntimeError("Inspection bundle segment coverage changed.")
        _write_json(paths["marker"], payload)
        return payload
    except BaseException:
        if topology_reader is not None:
            topology_reader.close(require_eof=False)
        if temporary.exists():
            temporary.unlink()
        raise


def _load_inspection_bundle_shard(
    *,
    run_dir: Path,
    bundle: ExecutionBundle,
    document: CorpusDocument,
    config_signature: str,
    plan_sha256: str,
) -> dict[str, Any] | None:
    paths = _inspection_bundle_paths(run_dir, bundle)
    if not paths["segments"].is_file() or not paths["marker"].is_file():
        return None
    payload = json.loads(paths["marker"].read_text(encoding="utf-8"))
    expected = (
        payload.get("schema_version")
        == "sktlm-s1m2-inspection-bundle-shard/v1"
        and payload.get("config_signature") == config_signature
        and payload.get("plan_sha256") == plan_sha256
        and int(payload.get("document_index", -1)) == bundle.document_index
        and payload.get("relative_path") == document.relative_path
        and int(payload.get("bundle_index", -1)) == bundle.bundle_index
        and int(payload.get("first_segment_ordinal", -1))
        == bundle.first_segment_ordinal
        and int(payload.get("last_segment_ordinal_exclusive", -1))
        == bundle.last_segment_ordinal_exclusive
        and int(payload.get("segment_count", -1)) == bundle.segment_count
    )
    if not expected:
        raise RuntimeError(
            f"Stale or mismatched inspection bundle shard: {paths['marker']}"
        )
    if payload.get("segment_shard_sha256") != _file_sha256(paths["segments"]):
        raise RuntimeError(
            f"Inspection bundle shard checksum mismatch: {paths['segments']}"
        )
    return payload


def _coalesce_inspection_bundle_shards(
    *,
    bundles: tuple[ExecutionBundle, ...],
    payloads: dict[tuple[int, int], dict[str, Any]],
    document: CorpusDocument,
    config: TrainingConfig,
    run_dir: Path,
    config_signature: str,
) -> dict[str, Any]:
    """Rebuild the existing document shard in canonical segment order."""

    if not bundles:
        raise RuntimeError("Cannot coalesce an empty inspection bundle set.")
    document_index = bundles[0].document_index
    paths = _inspection_shard_paths(run_dir, document_index)
    paths["marker"].parent.mkdir(parents=True, exist_ok=True)
    temporary = {
        kind: paths[kind].with_suffix(paths[kind].suffix + ".tmp")
        for kind in _INSPECTION_SHARD_KINDS
    }
    aggregate_temporary = temporary["aggregates"]
    if aggregate_temporary.exists():
        aggregate_temporary.unlink()
    aggregate_connection = sqlite3.connect(aggregate_temporary)
    aggregate_connection.execute("PRAGMA journal_mode=OFF")
    aggregate_connection.execute("PRAGMA synchronous=OFF")
    aggregate_connection.execute("PRAGMA temp_store=MEMORY")
    aggregate_connection.executescript(
        "CREATE TABLE count_rows ("
        "row_number INTEGER PRIMARY KEY, form_key TEXT NOT NULL, "
        "expected_count REAL NOT NULL);"
        "CREATE TABLE piece_rows ("
        "row_number INTEGER PRIMARY KEY, form_key TEXT NOT NULL, "
        "expected_count REAL NOT NULL, occurrence_support INTEGER NOT NULL);"
        "CREATE TABLE surface_rows ("
        "row_number INTEGER PRIMARY KEY, form_key TEXT NOT NULL, "
        "surface TEXT NOT NULL, expected_mass REAL NOT NULL);"
        "CREATE TABLE context_rows ("
        "row_number INTEGER PRIMARY KEY, form_key TEXT NOT NULL, "
        "context TEXT NOT NULL, expected_mass REAL NOT NULL);"
    )
    counts: Counter[PhonologicalForm] = Counter()
    piece_counts: Counter[PhonologicalForm] = Counter()
    piece_support: Counter[PhonologicalForm] = Counter()
    surface_buffer: list[tuple[str, str, float]] = []
    context_buffer: list[tuple[str, str, float]] = []
    row_numbers = {"counts": 0, "pieces": 0, "surfaces": 0, "contexts": 0}
    row_counts = {"counts": 0, "pieces": 0, "surfaces": 0, "contexts": 0}
    seen_lines: set[int] = set()
    reduction_rows = 0
    shard_database_seconds = 0.0
    coalesce_started = time.perf_counter()
    runtime_totals: Counter[str] = Counter()
    composed_totals: Counter[str] = Counter()
    engineering = RuntimeTelemetry()

    def flush_counts() -> None:
        nonlocal shard_database_seconds
        started = time.perf_counter()
        count_rows = []
        for form, value in sorted(counts.items(), key=lambda item: item[0].key):
            row_numbers["counts"] += 1
            count_rows.append((row_numbers["counts"], form.key, float(value)))
        if count_rows:
            aggregate_connection.executemany(
                "INSERT INTO count_rows VALUES (?, ?, ?)", count_rows
            )
            row_counts["counts"] += len(count_rows)
            counts.clear()
        piece_rows = []
        for piece, value in sorted(
            piece_counts.items(), key=lambda item: item[0].key
        ):
            row_numbers["pieces"] += 1
            piece_rows.append(
                (
                    row_numbers["pieces"],
                    piece.key,
                    float(value),
                    int(piece_support[piece]),
                )
            )
        if piece_rows:
            aggregate_connection.executemany(
                "INSERT INTO piece_rows VALUES (?, ?, ?, ?)", piece_rows
            )
            row_counts["pieces"] += len(piece_rows)
            piece_counts.clear()
            piece_support.clear()
        shard_database_seconds += time.perf_counter() - started

    def flush_usage() -> None:
        nonlocal shard_database_seconds
        if not surface_buffer and not context_buffer:
            return
        started = time.perf_counter()
        surface_rows = []
        for key, surface, mass in surface_buffer:
            row_numbers["surfaces"] += 1
            surface_rows.append(
                (row_numbers["surfaces"], key, surface, float(mass))
            )
        context_rows = []
        for key, context, mass in context_buffer:
            row_numbers["contexts"] += 1
            context_rows.append(
                (row_numbers["contexts"], key, context, float(mass))
            )
        if surface_rows:
            aggregate_connection.executemany(
                "INSERT INTO surface_rows VALUES (?, ?, ?, ?)", surface_rows
            )
        if context_rows:
            aggregate_connection.executemany(
                "INSERT INTO context_rows VALUES (?, ?, ?, ?)", context_rows
            )
        row_counts["surfaces"] += len(surface_rows)
        row_counts["contexts"] += len(context_rows)
        surface_buffer.clear()
        context_buffer.clear()
        shard_database_seconds += time.perf_counter() - started

    handles: dict[str, Any] = {}
    try:
        for kind in _INSPECTION_STREAM_SHARD_KINDS:
            handles[kind] = temporary[kind].open(
                "w", encoding="utf-8", newline=""
            )
        expected_ordinal = 0
        for bundle in bundles:
            if bundle.document_index != document_index:
                raise RuntimeError("Inspection bundle coalescing crossed documents.")
            payload = payloads[bundle.key]
            runtime = payload["runtime"]
            for label in (
                "inspection_candidate_generation",
                "inspection_inference",
                "inspection_count_aggregation",
                "inspection_frontend_io",
                "inspection_serialization",
                "inspection_worker_bundle_total",
                "inspection_worker_cpu",
                "lexical_score_calls",
                "sqlite_selects",
                "sqlite_seconds",
            ):
                runtime_totals[label] += runtime.get(label, 0)
            composed_totals.update(runtime.get("composed_counters", {}))
            engineering.merge_payload(runtime.get("engineering_telemetry", {}))
            bundle_records = 0
            first_identity: tuple[int, int] | None = None
            last_identity: tuple[int, int] | None = None
            bundle_paths = _inspection_bundle_paths(run_dir, bundle)
            with bundle_paths["segments"].open(encoding="utf-8") as source:
                for line in source:
                    record = json.loads(line)
                    if record.get("schema_version") != (
                        "sktlm-s1m2-inspection-segment-result/v1"
                    ):
                        raise RuntimeError("Invalid inspection segment shard.")
                    identity = (
                        int(record["line_number"]),
                        int(record["segment_index"]),
                    )
                    if first_identity is None:
                        first_identity = identity
                    last_identity = identity
                    seen_lines.add(identity[0])
                    for key, value in record["lexical_counts"]:
                        counts[PhonologicalForm.from_key(key)] += float.fromhex(
                            value
                        )
                    for key, value, support in record["piece_counts"]:
                        piece = PhonologicalForm.from_key(key)
                        piece_counts[piece] += float.fromhex(value)
                        piece_support[piece] += int(support)
                    handles["analyses"].write(
                        json.dumps(
                            record["analysis"],
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    handles["boundaries"].write(
                        json.dumps(
                            record["boundary"],
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    handles["reductions"].write(
                        json.dumps(
                            record["reduction"],
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    surface_buffer.extend(
                        (key, surface, float.fromhex(mass))
                        for key, surface, mass in record["surface_usage"]
                    )
                    context_buffer.extend(
                        (key, context, float.fromhex(mass))
                        for key, context, mass in record["context_usage"]
                    )
                    if len(counts) + len(piece_counts) >= config.flush_types:
                        flush_counts()
                    if len(surface_buffer) + len(context_buffer) >= config.flush_types:
                        flush_usage()
                    bundle_records += 1
                    reduction_rows += 1
            if (
                bundle.first_segment_ordinal != expected_ordinal
                or bundle_records != bundle.segment_count
                or first_identity
                != (bundle.first_line_number, bundle.first_segment_index)
                or last_identity
                != (bundle.last_line_number, bundle.last_segment_index)
            ):
                raise RuntimeError("Inspection bundle coverage is not canonical.")
            expected_ordinal = bundle.last_segment_ordinal_exclusive
        flush_counts()
        flush_usage()
        for handle in handles.values():
            handle.flush()
            os.fsync(handle.fileno())
        aggregate_connection.commit()
    finally:
        for handle in handles.values():
            handle.close()
        aggregate_connection.close()
    for kind in _INSPECTION_STREAM_SHARD_KINDS:
        _replace_file(temporary[kind], paths[kind])
    _replace_file(aggregate_temporary, paths["aggregates"])
    runtime = {
        "inspection_candidate_generation": runtime_totals[
            "inspection_candidate_generation"
        ],
        "inspection_inference": runtime_totals["inspection_inference"],
        "inspection_count_aggregation": runtime_totals[
            "inspection_count_aggregation"
        ],
        "inspection_frontend_io": runtime_totals["inspection_frontend_io"],
        "inspection_serialization": runtime_totals["inspection_serialization"],
        "inspection_worker_document_total": runtime_totals[
            "inspection_worker_bundle_total"
        ],
        "inspection_worker_cpu": runtime_totals["inspection_worker_cpu"],
        "inspection_worker_shard_database": shard_database_seconds,
        "inspection_bundle_coalescing": time.perf_counter() - coalesce_started,
        "lexical_score_calls": int(runtime_totals["lexical_score_calls"]),
        "sqlite_selects": int(runtime_totals["sqlite_selects"]),
        "sqlite_seconds": runtime_totals["sqlite_seconds"],
        "composed_counters": {
            key: int(value) for key, value in composed_totals.items()
        },
        "engineering_telemetry": engineering.payload(),
    }
    payload = {
        "schema_version": 2,
        "config_signature": config_signature,
        "document_index": document_index,
        "relative_path": document.relative_path,
        "lines": len(seen_lines),
        "rows": {**row_counts, "reductions": reduction_rows},
        "sha256": {
            kind: _file_sha256(paths[kind])
            for kind in _INSPECTION_SHARD_KINDS
        },
        "runtime": runtime,
        "aggregate_format": _INSPECTION_AGGREGATE_FORMAT,
    }
    _write_json(paths["marker"], payload)
    return payload


def _load_inspection_shard(
    run_dir: Path,
    document_index: int,
    document: CorpusDocument,
    config_signature: str,
) -> dict[str, Any] | None:
    paths = _inspection_shard_paths(run_dir, document_index)
    marker_path = paths["marker"]
    if not marker_path.is_file():
        return None
    payload = json.loads(marker_path.read_text(encoding="utf-8"))
    expected = (
        payload.get("config_signature") == config_signature
        and int(payload.get("document_index", -1)) == document_index
        and payload.get("relative_path") == document.relative_path
    )
    if not expected:
        raise RuntimeError(f"Stale or mismatched inspection shard: {marker_path}")
    shard_kinds = (
        _INSPECTION_SHARD_KINDS
        if payload.get("aggregate_format") == _INSPECTION_AGGREGATE_FORMAT
        else _LEGACY_INSPECTION_SHARD_KINDS
    )
    for kind in shard_kinds:
        if not paths[kind].is_file():
            raise RuntimeError(f"Inspection shard file is missing: {paths[kind]}")
        if payload["sha256"].get(kind) != _file_sha256(paths[kind]):
            raise RuntimeError(f"Inspection shard checksum mismatch: {paths[kind]}")
    return payload


def _apply_inspection_shard(
    *,
    payload: dict[str, Any],
    store: LexiconStore,
    config: TrainingConfig,
    run_dir: Path,
    analyses_handle: Any,
    boundaries_handle: Any,
    aggregate: _InspectionAggregate,
    telemetry: RuntimeTelemetry,
) -> None:
    reducer_started = telemetry.now()
    document_index = int(payload["document_index"])
    paths = _inspection_shard_paths(run_dir, document_index)
    with paths["analyses"].open("rb") as source:
        shutil.copyfileobj(source, analyses_handle, length=1024 * 1024)
    with paths["boundaries"].open("rb") as source:
        shutil.copyfileobj(source, boundaries_handle, length=1024 * 1024)

    if payload.get("aggregate_format") == _INSPECTION_AGGREGATE_FORMAT:
        merge_started = telemetry.now()
        store.merge_inspection_shard(
            paths["aggregates"],
            row_counts={
                key: int(value) for key, value in payload["rows"].items()
                if key in {"counts", "pieces", "surfaces", "contexts"}
            },
        )
        telemetry.elapsed("inspection_reducer_database_merge", merge_started)
    else:
        buffered_counts: list[tuple[PhonologicalForm, float]] = []
        with paths["counts"].open(encoding="utf-8") as handle:
            for line in handle:
                key, value = line.rstrip("\n").split("\t", 1)
                buffered_counts.append(
                    (PhonologicalForm.from_key(key), float.fromhex(value))
                )
                if len(buffered_counts) >= config.flush_types:
                    store.add_counts(buffered_counts, table="inspection_counts")
                    buffered_counts.clear()
        if buffered_counts:
            store.add_counts(buffered_counts, table="inspection_counts")

        if config.model == S1M2_MODEL:
            buffered_piece_counts: list[
                tuple[PhonologicalForm, float, int]
            ] = []
            with paths["pieces"].open(encoding="utf-8") as handle:
                for line in handle:
                    key, value, support = line.rstrip("\n").split("\t", 2)
                    buffered_piece_counts.append(
                        (
                            PhonologicalForm.from_key(key),
                            float.fromhex(value),
                            int(support),
                        )
                    )
                    if len(buffered_piece_counts) >= config.flush_types:
                        store.add_inspection_piece_counts(buffered_piece_counts)
                        buffered_piece_counts.clear()
            if buffered_piece_counts:
                store.add_inspection_piece_counts(buffered_piece_counts)

        for kind in ("surfaces", "contexts"):
            buffered_usage: list[tuple[str, str, float]] = []
            with paths[kind].open(encoding="utf-8") as handle:
                for line in handle:
                    key, encoded_value, mass = line.rstrip("\n").split("\t", 2)
                    buffered_usage.append(
                        (key, str(json.loads(encoded_value)), float.fromhex(mass))
                    )
                    if len(buffered_usage) >= config.flush_types:
                        if kind == "surfaces":
                            store.add_usage(surfaces=buffered_usage)
                        else:
                            store.add_usage(contexts=buffered_usage)
                        buffered_usage.clear()
            if buffered_usage:
                if kind == "surfaces":
                    store.add_usage(surfaces=buffered_usage)
                else:
                    store.add_usage(contexts=buffered_usage)

    with paths["reductions"].open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            metrics = aggregate.metrics
            metrics.segments += 1
            metrics.characters += int(row["characters"])
            metrics.log_partition += float(row["log_partition"])
            metrics.identity_mass_sum += float(row["identity_mass"])
            metrics.latent_mass_sum += float(row["latent_mass"])
            metrics.expected_lexical_tokens += float(
                row["expected_lexical_tokens"]
            )
            metrics.expected_piece_tokens += float(
                row.get("expected_piece_tokens", 0.0)
            )
            metrics.piece_segmentation_entropy += float(
                row.get("piece_segmentation_entropy", 0.0)
            )
            metrics.expected_whole_form_uses += float(
                row.get("expected_whole_form_uses", 0.0)
            )
            metrics.expected_singleton_path_uses += float(
                row.get("expected_singleton_path_uses", 0.0)
            )
            metrics.expected_multi_piece_uses += float(
                row.get("expected_multi_piece_uses", 0.0)
            )
            metrics.overflowed_tokens += int(row["overflowed_tokens"])
            metrics.candidate_factors += int(row["candidate_factors"])
            metrics.candidate_nodes += int(row["candidate_nodes"])
            metrics.candidate_edges += int(row["candidate_edges"])
            composed_counters = row.get("composed_counters", {})
            metrics.lazy_span_traversals += int(
                composed_counters.get("lazy_span_traversals", 0)
            )
            metrics.composed_states += int(
                composed_counters.get("composed_state_count", 0)
            )
            metrics.composed_transitions += int(
                composed_counters.get("composed_transition_count", 0)
            )
            metrics.piece_score_calls += int(
                composed_counters.get("piece_score_calls", 0)
            )
            metrics.piece_score_cache_hits += int(
                composed_counters.get("piece_score_cache_hits", 0)
            )
            metrics.piece_score_cache_misses += int(
                composed_counters.get("piece_score_cache_misses", 0)
            )
            metrics.form_cache_hits += int(
                composed_counters.get("form_cache_hits", 0)
            )
            metrics.form_cache_misses += int(
                composed_counters.get("form_cache_misses", 0)
            )
            metrics.piece_store_lookups += int(
                composed_counters.get("store_lookups", 0)
            )
            aggregate.rule_usage.update(row["rule_usage"])
            top_probability = float(row["top_probability"])
            entropy = float(row["entropy"])
            aggregate.top1_sum += top_probability
            aggregate.entropy_sum += entropy
            report_payload = row["report"]
            if (
                report_payload["rule_ids"]
                and top_probability >= config.high_confidence_threshold
            ):
                _push_report(
                    aggregate.high_confidence,
                    top_probability,
                    aggregate.serial,
                    report_payload,
                )
            _push_report(
                aggregate.ambiguous,
                entropy,
                aggregate.serial,
                report_payload,
            )
            _push_report(
                aggregate.shifts,
                float(row["latent_mass"]),
                aggregate.serial,
                report_payload,
            )
            aggregate.serial += 1
    aggregate.metrics.documents += 1
    aggregate.metrics.lines += int(payload["lines"])

    runtime = payload["runtime"]
    for label in (
        "inspection_candidate_generation",
        "inspection_inference",
        "inspection_count_aggregation",
        "inspection_frontend_io",
        "inspection_serialization",
        "inspection_worker_document_total",
        "inspection_worker_cpu",
        "inspection_worker_shard_database",
    ):
        if label in runtime:
            telemetry.add_seconds(label, float(runtime[label]))
    telemetry.increment(
        "inspection_worker_lexical_score_calls",
        int(runtime["lexical_score_calls"]),
    )
    telemetry.increment(
        "inspection_worker_sqlite_selects",
        int(runtime["sqlite_selects"]),
    )
    telemetry.add_seconds("inspection_worker_sqlite", float(runtime["sqlite_seconds"]))
    if runtime.get("composed_counters"):
        _record_composed_telemetry(
            telemetry,
            ComposedInferenceCounters(**runtime["composed_counters"]),
            phase="inspection",
        )
    if runtime.get("engineering_telemetry"):
        telemetry.merge_payload(runtime["engineering_telemetry"])
    _record_store_storage(telemetry, store.path)
    telemetry.elapsed("inspection_reducer_apply", reducer_started)


def _retire_inspection_shard(
    run_dir: Path,
    document_index: int,
    telemetry: RuntimeTelemetry,
) -> None:
    """Retire one reconstructible shard after successful canonical reduction."""

    paths = _inspection_shard_paths(run_dir, document_index)
    existing = tuple(path for path in paths.values() if path.is_file())
    retired_bytes = _existing_path_bytes(existing)
    for path in existing:
        path.unlink()
    telemetry.increment("inspection_shard_files_retired", len(existing))
    telemetry.increment("inspection_shard_bytes_retired", retired_bytes)


def _retire_inspection_bundle_shards(
    run_dir: Path,
    bundles: tuple[ExecutionBundle, ...],
    telemetry: RuntimeTelemetry,
) -> None:
    existing = tuple(
        path
        for bundle in bundles
        for path in _inspection_bundle_paths(run_dir, bundle).values()
        if path.is_file()
    )
    retired_bytes = _existing_path_bytes(existing)
    for path in existing:
        path.unlink()
    telemetry.increment("inspection_bundle_shard_files_retired", len(existing))
    telemetry.increment("inspection_bundle_shard_bytes_retired", retired_bytes)


def _finalize_inspection(
    *,
    store: LexiconStore,
    grammar: StructuredSandhiGrammar,
    config: TrainingConfig,
    run_dir: Path,
    analyses_tmp: Path,
    boundaries_tmp: Path,
    aggregate: _InspectionAggregate,
) -> dict[str, Any]:
    _replace_file(analyses_tmp, run_dir / "analyses.jsonl")
    _replace_file(boundaries_tmp, run_dir / "boundary_posteriors.jsonl")
    if config.model == S1M1_MODEL:
        store.export_lexicon(
            run_dir / "latent_lexicon.tsv",
            usage_threshold=config.usage_posterior_threshold,
        )
    else:
        store.export_lexical_diagnostics(
            run_dir / "lexical_diagnostics.tsv",
            usage_threshold=config.usage_posterior_threshold,
        )
        store.export_piece_inventory(
            run_dir / "piece_inventory.tsv",
            alpha=config.piece_alpha,
            complexity_weight=config.piece_complexity_weight,
            complexity_kappa=config.piece_complexity_kappa,
            complexity_beta=config.piece_complexity_beta,
            complexity_tau=config.piece_complexity_tau,
            base_stop_probability=config.piece_base_stop_probability,
        )
    with (run_dir / "rule_usage.tsv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("rule_id", "expected_usage"))
        for rule in grammar.rules:
            writer.writerow(
                (rule.rule_id, aggregate.rule_usage.get(rule.rule_id, 0.0))
            )

    lexical_complexity = store.complexity_summary(
        weight=config.complexity_weight,
        tau=config.complexity_tau,
        low_count_threshold=config.low_count_threshold,
    )
    complexity = (
        lexical_complexity
        if config.model == S1M1_MODEL
        else store.piece_summary(
            low_support_threshold=config.low_count_threshold,
            complexity_weight=config.piece_complexity_weight,
            complexity_kappa=config.piece_complexity_kappa,
            complexity_beta=config.piece_complexity_beta,
            complexity_tau=config.piece_complexity_tau,
        )
    )
    denominator = max(1, aggregate.metrics.segments)
    summary: dict[str, Any] = {
        **aggregate.metrics.summary(config.passes),
        "mean_top1_posterior": aggregate.top1_sum / denominator,
        "mean_entropy": aggregate.entropy_sum / denominator,
        "rule_expected_usage_total": sum(
            aggregate.rule_usage[key] for key in sorted(aggregate.rule_usage)
        ),
        "identity_mass_total": aggregate.metrics.identity_mass_sum,
        "latent_mass_total": aggregate.metrics.latent_mass_sum,
        "complexity": complexity,
        "usage_count_semantics": (
            "Distinct surface/context counts include associations whose "
            "posterior mass reaches usage_posterior_threshold; contexts use "
            "the bounded reported top-k analyses."
        ),
    }
    if config.model == S1M2_MODEL:
        expected_lexical = max(
            1e-300,
            aggregate.metrics.expected_lexical_tokens,
        )
        summary["lexical_diagnostics"] = lexical_complexity
        summary["piece_posterior"] = {
            "mean_segmentation_entropy_per_expected_lexical_token": (
                aggregate.metrics.piece_segmentation_entropy / expected_lexical
            ),
            "whole_form_memorization_mass": (
                aggregate.metrics.expected_whole_form_uses / expected_lexical
            ),
            "singleton_atomization_mass": (
                aggregate.metrics.expected_singleton_path_uses / expected_lexical
            ),
            "multi_piece_compositional_mass": (
                aggregate.metrics.expected_multi_piece_uses / expected_lexical
            ),
        }
    vocabulary = store.load_frozen_vocabulary()
    if vocabulary is not None:
        summary["vocabulary_budget"] = vocabulary.checkpoint_payload()
    _write_json(run_dir / "summary.json", summary)
    report_builder = (
        _human_report if config.model == S1M1_MODEL else _human_piece_report
    )
    report = report_builder(
        store=store,
        summary=summary,
        rule_usage=aggregate.rule_usage,
        high_confidence=_sorted_report(aggregate.high_confidence),
        ambiguous=_sorted_report(aggregate.ambiguous),
        shifts=_sorted_report(aggregate.shifts),
        config=config,
    )
    (run_dir / "inspection_report.md").write_text(
        report,
        encoding="utf-8",
        newline="",
    )
    return summary


def _parallel_inspection_bundles(
    *,
    documents: tuple[CorpusDocument, ...],
    grammar: StructuredSandhiGrammar,
    store: LexiconStore,
    config: TrainingConfig,
    inspection_workers: int,
    run_dir: Path,
    telemetry: RuntimeTelemetry,
    plan: ExecutionBundlePlan,
) -> dict[str, Any]:
    """Run true inflight inspection bundles and reduce documents canonically."""

    signature = _config_signature(config)
    vocabulary = store.load_frozen_vocabulary()
    if config.vocab_budget is not None and vocabulary is None:
        raise RuntimeError("Inspection requires the frozen pass-1 vocabulary.")
    analyses_tmp = run_dir / "analyses.jsonl.tmp"
    boundaries_tmp = run_dir / "boundary_posteriors.jsonl.tmp"
    aggregate = _InspectionAggregate()
    parallel_started = telemetry.now()
    existing_documents: dict[int, dict[str, Any]] = {}
    for document_index, document in enumerate(documents):
        payload = _load_inspection_shard(
            run_dir, document_index, document, signature
        )
        if payload is not None:
            existing_documents[document_index] = payload
    todo = tuple(
        bundle
        for document_index in range(len(documents))
        if document_index not in existing_documents
        for bundle in plan.by_document[document_index]
    )
    bundle_by_key = {bundle.key: bundle for bundle in plan.bundles}
    repair_engine = ComposedPieceInference(
        NeutralPieceScorer(),
        model_config=config.piece_model_config,
        cache_config=config.piece_cache_config,
    )
    context = multiprocessing.get_context("spawn")
    with analyses_tmp.open("wb") as analyses_handle, boundaries_tmp.open(
        "wb"
    ) as boundaries_handle, ProcessPoolExecutor(
        max_workers=inspection_workers,
        mp_context=context,
        initializer=_initialize_inspection_worker,
        initargs=(store.path, config, vocabulary),
    ) as executor:
        max_inflight = inspection_workers * 2
        telemetry.maximum("inspection_pending_shard_limit", max_inflight)
        telemetry.maximum("inspection_bundle_inflight_limit", max_inflight)
        inflight: dict[Future[dict[str, Any]], ExecutionBundle] = {}
        ready: dict[tuple[int, int], dict[str, Any]] = {}
        validated_topology: set[int] = set()
        next_submit = 0
        reduction_document_index = 0
        dispatch_error: BaseException | None = None
        dispatch_done = False
        dispatch_stop = False
        condition = threading.Condition()

        def fill_inflight() -> None:
            nonlocal next_submit
            while (
                next_submit < len(todo)
                and len(inflight) < max_inflight
                and (
                    todo[next_submit].document_index
                    <= reduction_document_index
                    or (
                        len(inflight)
                        + sum(
                            key[0] > reduction_document_index
                            for key in ready
                        )
                        < max_inflight * 2
                    )
                )
            ):
                bundle = todo[next_submit]
                document = documents[bundle.document_index]
                existing = _load_inspection_bundle_shard(
                    run_dir=run_dir,
                    bundle=bundle,
                    document=document,
                    config_signature=signature,
                    plan_sha256=plan.plan_sha256,
                )
                if existing is not None:
                    ready[bundle.key] = existing
                    telemetry.increment("inspection_bundle_shards_resumed", 1)
                    next_submit += 1
                    continue
                if bundle.document_index not in validated_topology:
                    if COMPACT_EXACT_S1M2:
                        validated_topology.add(bundle.document_index)
                    else:
                        _validate_bundle_topology_archive(
                            document=document,
                            document_index=bundle.document_index,
                            config=config,
                            run_dir=run_dir,
                            config_signature=signature,
                            grammar=grammar,
                            piece_engine=repair_engine,
                            telemetry=telemetry,
                        )
                        validated_topology.add(bundle.document_index)
                future = executor.submit(
                    _write_inspection_bundle_shard,
                    bundle,
                    document,
                    config,
                    run_dir,
                    signature,
                    plan.plan_sha256,
                )
                inflight[future] = bundle
                next_submit += 1
            telemetry.maximum("inspection_pending_shards", len(inflight))
            telemetry.maximum("inspection_bundle_true_inflight", len(inflight))
            telemetry.maximum("inspection_bundle_ready_shards", len(ready))

        def dispatch() -> None:
            nonlocal dispatch_error, dispatch_done
            try:
                while True:
                    with condition:
                        if dispatch_stop:
                            return
                        fill_inflight()
                        if not inflight:
                            dispatch_done = next_submit == len(todo)
                            condition.notify_all()
                            if dispatch_done:
                                return
                            condition.wait()
                            continue
                        futures = tuple(inflight)
                    wait(futures, return_when=FIRST_COMPLETED)
                    with condition:
                        for future in tuple(item for item in inflight if item.done()):
                            bundle = inflight.pop(future)
                            ready[bundle.key] = future.result()
                        telemetry.observe("inspection_bundle_true_inflight", len(inflight))
                        telemetry.observe("inspection_bundle_ready_shards", len(ready))
                        condition.notify_all()
            except BaseException as error:
                with condition:
                    dispatch_error = error
                    condition.notify_all()

        dispatcher = threading.Thread(target=dispatch, name="s1m2-inspection-dispatch")
        dispatcher.start()
        try:
            for document_index, document in enumerate(documents):
                document_bundles = plan.by_document[document_index]
                if document_index in existing_documents:
                    payload = existing_documents[document_index]
                    telemetry.add_seconds("inspection_reducer_stall", 0.0)
                else:
                    expected_keys = tuple(bundle.key for bundle in document_bundles)
                    wait_started = telemetry.now()
                    with condition:
                        while any(key not in ready for key in expected_keys):
                            if dispatch_error is not None:
                                raise dispatch_error
                            if dispatch_done:
                                raise RuntimeError(
                                    "Inspection bundle scheduler exhausted work "
                                    f"before document {document_index} became ready."
                                )
                            condition.wait()
                        telemetry.add_seconds(
                            "inspection_reducer_stall",
                            time.perf_counter() - wait_started,
                        )
                        payloads = {key: ready[key] for key in expected_keys}
                if document_index not in existing_documents:
                    payload = _coalesce_inspection_bundle_shards(
                        bundles=document_bundles,
                        payloads=payloads,
                        document=document,
                        config=config,
                        run_dir=run_dir,
                        config_signature=signature,
                    )
                with condition:
                    completed_but_blocked = len(ready) - sum(
                        bundle.key in ready for bundle in document_bundles
                    )
                    pending_bundles = {
                        bundle.key: bundle for bundle in inflight.values()
                    }
                    pending_bundles.update(
                        {key: bundle_by_key[key] for key in ready}
                    )
                telemetry.observe(
                    "inspection_completed_but_blocked_shards_per_reduction",
                    completed_but_blocked,
                )
                telemetry.maximum(
                    "inspection_completed_but_blocked_shards",
                    completed_but_blocked,
                )
                pending_paths = [
                    path
                    for bundle in pending_bundles.values()
                    for path in _inspection_bundle_paths(run_dir, bundle).values()
                ]
                pending_paths.extend(
                    _inspection_shard_paths(run_dir, document_index).values()
                )
                telemetry.maximum(
                    "inspection_pending_shard_bytes",
                    _existing_path_bytes(pending_paths),
                )
                _apply_inspection_shard(
                    payload=payload,
                    store=store,
                    config=config,
                    run_dir=run_dir,
                    analyses_handle=analyses_handle,
                    boundaries_handle=boundaries_handle,
                    aggregate=aggregate,
                    telemetry=telemetry,
                )
                _record_run_storage(telemetry, run_dir)
                _retire_inspection_shard(run_dir, document_index, telemetry)
                _retire_inspection_bundle_shards(
                    run_dir, document_bundles, telemetry
                )
                with condition:
                    for bundle in document_bundles:
                        ready.pop(bundle.key, None)
                    reduction_document_index = document_index + 1
                    telemetry.observe("inspection_bundle_ready_shards", len(ready))
                    condition.notify_all()
        finally:
            with condition:
                dispatch_stop = True
                condition.notify_all()
            dispatcher.join()
        if dispatch_error is not None:
            raise dispatch_error
    parallel_seconds = time.perf_counter() - parallel_started
    telemetry.add_seconds("inspection_parallel_wall", parallel_seconds)
    telemetry.add_seconds("inspection_document_total", parallel_seconds)
    return _finalize_inspection(
        store=store,
        grammar=grammar,
        config=config,
        run_dir=run_dir,
        analyses_tmp=analyses_tmp,
        boundaries_tmp=boundaries_tmp,
        aggregate=aggregate,
    )


def _parallel_inspection_pass(
    *,
    documents: tuple[CorpusDocument, ...],
    grammar: StructuredSandhiGrammar,
    store: LexiconStore,
    config: TrainingConfig,
    inspection_workers: int,
    run_dir: Path,
    telemetry: RuntimeTelemetry,
) -> dict[str, Any]:
    signature = _config_signature(config)
    vocabulary = store.load_frozen_vocabulary()
    if config.vocab_budget is not None and vocabulary is None:
        raise RuntimeError("Inspection requires the frozen pass-1 vocabulary.")
    analyses_tmp = run_dir / "analyses.jsonl.tmp"
    boundaries_tmp = run_dir / "boundary_posteriors.jsonl.tmp"
    aggregate = _InspectionAggregate()
    parallel_started = telemetry.now()
    context = multiprocessing.get_context("spawn")
    with analyses_tmp.open("wb") as analyses_handle, boundaries_tmp.open(
        "wb"
    ) as boundaries_handle, ProcessPoolExecutor(
        max_workers=inspection_workers,
        mp_context=context,
        initializer=_initialize_inspection_worker,
        initargs=(store.path, config, vocabulary),
    ) as executor:
        max_pending = inspection_workers * 2
        telemetry.maximum("inspection_pending_shard_limit", max_pending)
        pending: dict[int, Future[dict[str, Any]] | dict[str, Any]] = {}
        next_submit = 0

        def fill_pending() -> None:
            nonlocal next_submit
            while next_submit < len(documents) and len(pending) < max_pending:
                document_index = next_submit
                document = documents[document_index]
                existing = _load_inspection_shard(
                    run_dir,
                    document_index,
                    document,
                    signature,
                )
                if existing is not None:
                    pending[document_index] = existing
                else:
                    pending[document_index] = executor.submit(
                        _write_inspection_shard,
                        document_index,
                        document,
                        config,
                        run_dir,
                        signature,
                    )
                next_submit += 1
            telemetry.maximum("inspection_pending_shards", len(pending))

        fill_pending()
        for document_index in range(len(documents)):
            telemetry.observe("inspection_pending_shards_per_reduction", len(pending))
            item = pending.pop(document_index)
            if isinstance(item, Future):
                ready = item.done()
                wait_started = telemetry.now()
                payload = item.result()
                telemetry.add_seconds(
                    "inspection_reducer_stall",
                    0.0 if ready else time.perf_counter() - wait_started,
                )
            else:
                payload = item
                telemetry.add_seconds("inspection_reducer_stall", 0.0)
            completed_but_blocked = sum(
                1
                for pending_item in pending.values()
                if not isinstance(pending_item, Future) or pending_item.done()
            )
            telemetry.observe(
                "inspection_completed_but_blocked_shards_per_reduction",
                completed_but_blocked,
            )
            telemetry.maximum(
                "inspection_completed_but_blocked_shards",
                completed_but_blocked,
            )
            pending_paths: list[Path] = []
            for pending_index in (document_index, *pending):
                pending_paths.extend(
                    _inspection_shard_paths(run_dir, pending_index).values()
                )
            telemetry.maximum(
                "inspection_pending_shard_bytes",
                _existing_path_bytes(pending_paths),
            )
            _apply_inspection_shard(
                payload=payload,
                store=store,
                config=config,
                run_dir=run_dir,
                analyses_handle=analyses_handle,
                boundaries_handle=boundaries_handle,
                aggregate=aggregate,
                telemetry=telemetry,
            )
            _record_run_storage(telemetry, run_dir)
            _retire_inspection_shard(
                run_dir,
                document_index,
                telemetry,
            )
            fill_pending()
    parallel_seconds = time.perf_counter() - parallel_started
    telemetry.add_seconds("inspection_parallel_wall", parallel_seconds)
    telemetry.add_seconds("inspection_document_total", parallel_seconds)
    return _finalize_inspection(
        store=store,
        grammar=grammar,
        config=config,
        run_dir=run_dir,
        analyses_tmp=analyses_tmp,
        boundaries_tmp=boundaries_tmp,
        aggregate=aggregate,
    )


def _cleanup_inspection_shards(run_dir: Path) -> None:
    root = run_dir / "shards" / "inspection"
    if not root.is_dir():
        return
    for path in root.iterdir():
        if path.is_file():
            path.unlink()


def _compact_completed_s1m2_storage(
    *,
    store: LexiconStore,
    run_dir: Path,
) -> dict[str, Any]:
    compaction = store.compact_completed_piece_state()
    before = int(compaction["before_bytes"]["total"])
    after = int(compaction["after_bytes"]["total"])
    saved = before - after
    payload = {
        "schema_version": "sktlm-s1m2-completed-storage/v1",
        "status": "COMPACT",
        **compaction,
        "bytes_saved": saved,
        "reduction_fraction": saved / max(1, before),
        "authoritative_state": {
            "metadata": "configuration signature and transactional checkpoint",
            "piece_lexicon": "fixed active piece parameters used by final inspection",
        },
        "compiled_topology": {
            "path": None,
            "role": (
                "compact structural form tries are deterministic transient "
                "execution state, never authoritative state"
            ),
            "compression": None,
            "mutable_scores_or_posteriors_stored": False,
            "validation": (
                "each pass rebuilds exact document-local candidate geometry and "
                "factor-local direct structural tries from frozen inputs"
            ),
        },
        "canonical_scientific_artifacts": list(
            _S1M2_CANONICAL_SCIENTIFIC_ARTIFACTS
        ),
        "reconstructibility": (
            "The dropped tables are final-pass diagnostic or inspection indexes. "
            "Canonical scientific values remain in the listed artifacts; final "
            "inspection indexes are exactly regenerable from the retained active "
            "piece state, frozen inputs, configuration, and code identity."
        ),
        "transient_lifecycle": {
            "training_pass_diagnostics": (
                "piece_inventory and lexical_diagnostics are retired in the same "
                "transaction that installs the durable active piece state and "
                "completed-pass checkpoint"
            ),
            "inspection_worker_shards": (
                "each reconstructible worker shard is retired immediately after "
                "successful canonical reduction; interruption recovery regenerates "
                "retired shards from durable active parameters and frozen inputs"
            ),
            "compiled_topology": (
                "rebuilt directly from boundary-node geometry for each factor and "
                "released after inference; legacy topology archives are reference-"
                "only and are not required by training or inspection-only"
            ),
        },
    }
    _write_json(run_dir / "storage_manifest.json", payload)
    return payload


def _inspection_pass(
    *,
    documents: tuple[CorpusDocument, ...],
    grammar: StructuredSandhiGrammar,
    store: LexiconStore,
    config: TrainingConfig,
    inspection_workers: int,
    run_dir: Path,
    telemetry: RuntimeTelemetry,
    execution_plan: ExecutionBundlePlan | None = None,
) -> dict[str, Any]:
    if config.model == S1M1_MODEL:
        store.begin_inspection()
    else:
        store.begin_piece_inspection()
    if (
        config.model == S1M2_MODEL
        and inspection_workers > 1
        and execution_plan is not None
    ):
        return _parallel_inspection_bundles(
            documents=documents,
            grammar=grammar,
            store=store,
            config=config,
            inspection_workers=inspection_workers,
            run_dir=run_dir,
            telemetry=telemetry,
            plan=execution_plan,
        )
    if inspection_workers > 1:
        return _parallel_inspection_pass(
            documents=documents,
            grammar=grammar,
            store=store,
            config=config,
            inspection_workers=inspection_workers,
            run_dir=run_dir,
            telemetry=telemetry,
        )
    scorer = None
    piece_engine = None
    if config.model == S1M1_MODEL:
        scorer = store.scorer(
            alpha=config.lexical_alpha,
            complexity_weight=config.complexity_weight,
            complexity_tau=config.complexity_tau,
            cache_size=config.lexicon_cache_size,
        )
    else:
        piece_scorer = store.piece_scorer(
            alpha=config.piece_alpha,
            complexity_weight=config.piece_complexity_weight,
            complexity_kappa=config.piece_complexity_kappa,
            complexity_beta=config.piece_complexity_beta,
            complexity_tau=config.piece_complexity_tau,
            base_stop_probability=config.piece_base_stop_probability,
            cache_size=config.lexicon_cache_size,
        )
        piece_engine = ComposedPieceInference(
            piece_scorer,
            model_config=config.piece_model_config,
            cache_config=config.piece_cache_config,
            inspection_top_k=config.analysis_top_k,
        )
    vocabulary = store.load_frozen_vocabulary()
    if config.vocab_budget is not None and vocabulary is None:
        raise RuntimeError("Inspection requires the frozen pass-1 vocabulary.")
    analyses_tmp = run_dir / "analyses.jsonl.tmp"
    boundaries_tmp = run_dir / "boundary_posteriors.jsonl.tmp"
    rule_usage: Counter[str] = Counter()
    counts: Counter[PhonologicalForm] = Counter()
    piece_counts: Counter[PhonologicalForm] = Counter()
    piece_support: Counter[PhonologicalForm] = Counter()
    metrics = PassMetrics()
    top1_sum = 0.0
    entropy_sum = 0.0
    high_confidence: list[tuple[float, int, dict[str, Any]]] = []
    ambiguous: list[tuple[float, int, dict[str, Any]]] = []
    shifts: list[tuple[float, int, dict[str, Any]]] = []
    serial = 0

    with analyses_tmp.open("w", encoding="utf-8", newline="\n") as analyses_handle, (
        boundaries_tmp.open("w", encoding="utf-8", newline="\n")
    ) as boundaries_handle:
        signature = _config_signature(config)
        for document_index, document in enumerate(documents):
            document_started = telemetry.now()
            seen_lines: set[int] = set()
            surface_usage: list[tuple[str, str, float]] = []
            context_usage: list[tuple[str, str, float]] = []
            for (
                line_number,
                segment_index,
                segment,
                segment_topology,
            ) in _profiled_document_segments_with_topology(
                document,
                document_index,
                config,
                run_dir,
                telemetry,
                phase='inspection',
                config_signature=signature,
                grammar=grammar,
                piece_engine=piece_engine,
            ):
                seen_lines.add(line_number)
                started = telemetry.now()
                candidate_profile = (
                    CandidateBuildProfile()
                    if config.model == S1M2_MODEL
                    else None
                )
                if config.model == S1M1_MODEL:
                    graph = build_candidate_graph(
                        segment,
                        grammar,
                        config.candidate_config,
                    )
                else:
                    graph = build_lazy_candidate_graph(
                        segment,
                        grammar,
                        config.candidate_config,
                        profile=candidate_profile,
                    )
                telemetry.elapsed('inspection_candidate_generation', started)
                candidate_counts = (
                    candidate_graph_statistics(graph)
                    if config.model == S1M1_MODEL
                    else lazy_candidate_graph_statistics(graph)
                )
                if candidate_profile is not None:
                    _record_candidate_telemetry(
                        telemetry,
                        candidate_profile,
                        candidate_counts,
                        phase="inspection",
                    )
                started = telemetry.now()
                if config.model == S1M1_MODEL:
                    assert scorer is not None
                    inference = infer_segment(
                        graph,
                        scorer,
                        whitespace_merge_penalty=config.whitespace_merge_penalty,
                        top_k=config.analysis_top_k,
                        vocabulary=vocabulary,
                    )
                else:
                    assert piece_engine is not None
                    inference = infer_composed_segment(
                        graph,
                        piece_engine,
                        whitespace_merge_penalty=config.whitespace_merge_penalty,
                        support_epsilon=config.piece_support_epsilon,
                        topology=segment_topology,
                    )
                    _record_composed_telemetry(
                        telemetry,
                        inference.counters,
                        phase="inspection",
                        timings=inference.timings,
                    )
                telemetry.elapsed('inspection_inference', started)
                started = telemetry.now()
                counts.update(
                    inference.expected_counts
                    if config.model == S1M1_MODEL
                    else inference.lexical_expected_counts
                )
                if config.model == S1M2_MODEL:
                    piece_counts.update(inference.piece_expected_counts)
                    piece_support.update(inference.piece_occurrence_support)
                rule_usage.update(inference.rule_usage)
                telemetry.elapsed('inspection_count_aggregation', started)
                metrics.update(
                    segment,
                    inference,
                    overflowed_tokens=graph.overflowed_tokens,
                    candidate_factors=candidate_counts["factors"],
                    candidate_nodes=candidate_counts["lattice_nodes"],
                    candidate_edges=(
                        candidate_counts["lexical_edges"]
                        if config.model == S1M1_MODEL
                        else candidate_counts["lexical_span_hypotheses"]
                    ),
                )
                serialization_started = telemetry.now()
                segment_id = (
                    f"{document.document_id}:l{line_number:08d}:"
                    f"s{segment_index:04d}"
                )
                row = {
                    "schema_version": 1 if config.model == S1M1_MODEL else 2,
                    "segment_id": segment_id,
                    "document": document.relative_path,
                    "line_number": line_number,
                    "source_start": segment.source_start,
                    "source_end": segment.source_end,
                    "surface": segment.written,
                    "top_analyses": [
                        (
                            _analysis_payload(analysis)
                            if config.model == S1M1_MODEL
                            else _composed_analysis_payload(analysis)
                        )
                        for analysis in inference.top_analyses
                    ],
                    "top_analysis_mass": inference.top_analysis_mass,
                    "residual_posterior": max(
                        0.0,
                        1.0 - inference.top_analysis_mass,
                    ),
                    "identity_mass": inference.identity_mass,
                    "latent_mass": inference.latent_mass,
                    "entropy": inference.entropy,
                    "log_partition": inference.log_partition,
                    "candidate_counts": candidate_counts,
                }
                if isinstance(inference, ComposedSegmentInference):
                    row["piece_posterior"] = {
                        "expected_piece_tokens": inference.expected_piece_tokens,
                        "segmentation_entropy": (
                            inference.piece_segmentation_entropy
                        ),
                        "whole_form_uses": inference.expected_whole_form_uses,
                        "singleton_path_uses": (
                            inference.expected_singleton_path_uses
                        ),
                        "multi_piece_uses": inference.expected_multi_piece_uses,
                    }
                if config.equivalence_diagnostics:
                    row["candidate_fingerprint"] = (
                        candidate_graph_fingerprint(graph)
                        if config.model == S1M1_MODEL
                        else _sha256_bytes(
                            _canonical_json(candidate_counts).encode("utf-8")
                        )
                    )
                analyses_handle.write(
                    json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                )
                boundary_row = {
                    "schema_version": 1 if config.model == S1M1_MODEL else 2,
                    "segment_id": segment_id,
                    "surface": segment.written,
                    "boundaries": [
                        _boundary_posterior_payload(item)
                        for item in inference.boundary_posteriors
                    ],
                }
                boundaries_handle.write(
                    json.dumps(boundary_row, ensure_ascii=False, sort_keys=True) + "\n"
                )

                telemetry.elapsed('inspection_serialization', serialization_started)
                top_probability = (
                    inference.top_analyses[0].probability
                    if inference.top_analyses
                    else 0.0
                )
                top1_sum += top_probability
                entropy_sum += inference.entropy
                report_payload = {
                    "segment_id": segment_id,
                    "surface": segment.written,
                    "analysis": (
                        " | ".join(
                            word.iast for word in inference.top_analyses[0].words
                        )
                        if inference.top_analyses
                        else ""
                    ),
                    "posterior": top_probability,
                    "identity_mass": inference.identity_mass,
                    "latent_mass": inference.latent_mass,
                    "entropy": inference.entropy,
                    "rule_ids": (
                        list(inference.top_analyses[0].rule_ids)
                        if inference.top_analyses
                        else []
                    ),
                }
                if (
                    report_payload["rule_ids"]
                    and top_probability >= config.high_confidence_threshold
                ):
                    _push_report(
                        high_confidence,
                        top_probability,
                        serial,
                        report_payload,
                    )
                _push_report(
                    ambiguous,
                    inference.entropy,
                    serial,
                    report_payload,
                )
                _push_report(
                    shifts,
                    inference.latent_mass,
                    serial,
                    report_payload,
                )
                serial += 1

                inference_lexical_counts = (
                    inference.expected_counts
                    if config.model == S1M1_MODEL
                    else inference.lexical_expected_counts
                )
                for form, mass in inference_lexical_counts.items():
                    if mass >= config.usage_posterior_threshold:
                        surface_usage.append((form.key, segment.written, mass))
                for analysis in inference.top_analyses:
                    if analysis.probability < config.usage_posterior_threshold:
                        continue
                    for word_index, word in enumerate(analysis.words):
                        left = (
                            analysis.words[word_index - 1].key
                            if word_index
                            else "<BOS>"
                        )
                        right = (
                            analysis.words[word_index + 1].key
                            if word_index + 1 < len(analysis.words)
                            else "<EOS>"
                        )
                        context_usage.append(
                            (word.key, f"{left}>{right}", analysis.probability)
                        )
                if len(counts) >= config.flush_types:
                    _flush_counts(store, counts, table="inspection_counts")
                if len(piece_counts) >= config.flush_types:
                    store.add_inspection_piece_counts(
                        (
                            (piece, value, piece_support[piece])
                            for piece, value in piece_counts.items()
                        )
                    )
                    piece_counts.clear()
                    piece_support.clear()
                if len(surface_usage) + len(context_usage) >= config.flush_types:
                    store.add_usage(
                        surfaces=surface_usage,
                        contexts=context_usage,
                    )
                    surface_usage.clear()
                    context_usage.clear()
            _flush_counts(store, counts, table="inspection_counts")
            if piece_counts:
                store.add_inspection_piece_counts(
                    (
                        (piece, value, piece_support[piece])
                        for piece, value in piece_counts.items()
                    )
                )
                piece_counts.clear()
                piece_support.clear()
            store.add_usage(surfaces=surface_usage, contexts=context_usage)
            metrics.documents += 1
            metrics.lines += len(seen_lines)
            telemetry.elapsed('inspection_document_total', document_started)

    aggregate = _InspectionAggregate(
        metrics=metrics,
        rule_usage=rule_usage,
        top1_sum=top1_sum,
        entropy_sum=entropy_sum,
        high_confidence=high_confidence,
        ambiguous=ambiguous,
        shifts=shifts,
        serial=serial,
    )
    return _finalize_inspection(
        store=store,
        grammar=grammar,
        config=config,
        run_dir=run_dir,
        analyses_tmp=analyses_tmp,
        boundaries_tmp=boundaries_tmp,
        aggregate=aggregate,
    )


def _human_report(
    *,
    store: LexiconStore,
    summary: dict[str, Any],
    rule_usage: Counter[str],
    high_confidence: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
    shifts: list[dict[str, Any]],
    config: TrainingConfig,
) -> str:
    lines = [
        "# Latent Sanskrit lexicon inspection",
        "",
        f"- implementation: `{IMPLEMENTATION}`",
        "- condition: `IAST + surface_word`",
        f"- segments: {summary['segments']}",
        f"- mean identity mass: {summary['mean_identity_mass']:.6f}",
        f"- mean latent mass: {summary['mean_latent_mass']:.6f}",
        f"- active lexical types: {summary['complexity']['active_lexical_types']}",
        f"- low-count types: {summary['complexity']['low_count_types']}",
        f"- complexity penalty: {summary['complexity']['complexity_penalty']:.6f}",
        "",
        "## Highest-frequency latent forms",
        "",
        "| latent form | expected count | model probability |",
        "|---|---:|---:|",
    ]
    for form, count, probability in store.top_lexicon(20):
        lines.append(f"| {form} | {count:.6f} | {probability:.8g} |")

    def add_cases(title: str, cases: list[dict[str, Any]]) -> None:
        lines.extend(["", f"## {title}", ""])
        if not cases:
            lines.append("_None in the bounded run._")
            return
        lines.extend(
            [
                "| surface | top latent analysis | posterior | identity | latent | entropy |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for case in cases:
            surface = str(case["surface"]).replace("|", "&#124;")
            analysis = str(case["analysis"]).replace("|", "&#124;")
            lines.append(
                f"| {surface} | {analysis} | {case['posterior']:.6f} | "
                f"{case['identity_mass']:.6f} | {case['latent_mass']:.6f} | "
                f"{case['entropy']:.6f} |"
            )

    add_cases("High-confidence sandhi analyses", high_confidence)
    add_cases("Most ambiguous cases", ambiguous)
    add_cases("Largest identity-to-latent shifts", shifts)
    lines.extend(
        [
            "",
            "## Suspicious low-frequency forms",
            "",
            "| latent form | expected count |",
            "|---|---:|",
        ]
    )
    for form, count in store.low_count_lexicon(20, config.low_count_threshold):
        lines.append(f"| {form} | {count:.6f} |")
    lines.extend(
        [
            "",
            "## Most-used external sandhi rules",
            "",
            "| rule | expected usage |",
            "|---|---:|",
        ]
    )
    positive_rules = [
        (rule_id, usage)
        for rule_id, usage in rule_usage.most_common()
        if usage > 0.0
    ]
    for rule_id, usage in positive_rules[:20]:
        lines.append(f"| {rule_id} | {usage:.6f} |")
    lines.extend(
        [
            "",
            "## Regularizer",
            "",
            (
                r"(R(c)=\lambda\sum_w\log(1+c_w/\tau)), with "
                f"\\(\\lambda={config.complexity_weight}\\) and "
                f"\\(\\tau={config.complexity_tau}\\)."
            ),
            "No rule-use or generic sandhi reward is present.",
            "",
        ]
    )
    return "\n".join(lines)


def _human_piece_report(
    *,
    store: LexiconStore,
    summary: dict[str, Any],
    rule_usage: Counter[str],
    high_confidence: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
    shifts: list[dict[str, Any]],
    config: TrainingConfig,
) -> str:
    piece = summary["complexity"]
    posterior = summary["piece_posterior"]
    lines = [
        "# S1M2 reusable-piece inspection",
        "",
        f"- implementation: `{S1M2_MODEL}`",
        f"- representation: `{config.script} + {config.condition}`",
        f"- segments: {summary['segments']}",
        f"- mean identity mass: {summary['mean_identity_mass']:.6f}",
        f"- mean latent mass: {summary['mean_latent_mass']:.6f}",
        f"- active piece types: {piece['active_piece_types']}",
        f"- observed piece types: {piece['piece_types']}",
        (
            "- whole-form memorization mass: "
            f"{posterior['whole_form_memorization_mass']:.6f}"
        ),
        (
            "- singleton atomization mass: "
            f"{posterior['singleton_atomization_mass']:.6f}"
        ),
        (
            "- multi-piece compositional mass: "
            f"{posterior['multi_piece_compositional_mass']:.6f}"
        ),
        "",
        "## Highest-frequency reusable pieces",
        "",
        "| piece | length | expected count | reuse occurrences | active |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, count, support, active in store.connection.execute(
        "SELECT i.form_key, i.expected_count, i.occurrence_support, "
        "CASE WHEN a.form_key IS NULL THEN 0 ELSE 1 END "
        "FROM inspection_piece_counts i LEFT JOIN piece_lexicon a "
        "ON a.form_key=i.form_key ORDER BY i.expected_count DESC, i.form_key "
        "LIMIT 20"
    ):
        form = PhonologicalForm.from_key(str(key))
        lines.append(
            f"| {form.iast} | {len(form.symbols)} | {float(count):.6f} | "
            f"{int(support)} | {int(active)} |"
        )

    def add_cases(title: str, cases: list[dict[str, Any]]) -> None:
        lines.extend(["", f"## {title}", ""])
        if not cases:
            lines.append("_None in the bounded run._")
            return
        lines.extend(
            [
                "| surface | top lexical analysis | posterior | identity | latent | entropy |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for case in cases:
            surface = str(case["surface"]).replace("|", "&#124;")
            analysis = str(case["analysis"]).replace("|", "&#124;")
            lines.append(
                f"| {surface} | {analysis} | {case['posterior']:.6f} | "
                f"{case['identity_mass']:.6f} | {case['latent_mass']:.6f} | "
                f"{case['entropy']:.6f} |"
            )

    add_cases("High-confidence sandhi analyses", high_confidence)
    add_cases("Most ambiguous composed cases", ambiguous)
    add_cases("Largest identity-to-latent shifts", shifts)
    lines.extend(
        [
            "",
            "## Piece-length expected-count distribution",
            "",
            "| length | expected count |",
            "|---:|---:|",
        ]
    )
    for length, count in piece["expected_count_by_length"].items():
        lines.append(f"| {length} | {float(count):.6f} |")
    lines.extend(
        [
            "",
            "## Most-used external sandhi rules",
            "",
            "| rule | expected usage |",
            "|---|---:|",
        ]
    )
    positive_rules = [item for item in rule_usage.most_common() if item[1] > 0.0]
    for rule_id, usage in positive_rules[:20]:
        lines.append(f"| {rule_id} | {usage:.6f} |")
    lines.extend(
        [
            "",
            "## Active/inactive semantics",
            "",
            (
                "All legal pieces remain exactly scoreable. Persistent active "
                "parameters are observed singletons plus pieces supported in at "
                f"least {config.piece_min_reuse_occurrences} distinct lexical "
                "occurrences."
            ),
            "No rule-use or generic sandhi reward is present.",
            "",
        ]
    )
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class TrainingResult:
    run_dir: Path
    history: tuple[dict[str, Any], ...]
    summary: dict[str, Any]
    runtime: dict[str, Any]
    inspection_complete: bool = True


def _validate_inspection_only_state(
    *,
    store: LexiconStore,
    checkpoint: dict[str, Any],
    config: TrainingConfig,
    run_dir: Path,
) -> None:
    """Fail closed unless the requested final training state is authoritative."""

    completed = int(checkpoint.get("completed_passes", 0))
    history = checkpoint.get("history")
    if completed != config.passes:
        raise RuntimeError(
            "Inspection-only requires completed_passes to equal requested passes."
        )
    if checkpoint.get("active_pass") is not None:
        raise RuntimeError("Inspection-only refuses an active training pass.")
    if int(checkpoint.get("next_document_index", 0)) != 0:
        raise RuntimeError("Inspection-only refuses partial document progress.")
    if checkpoint.get("active_metrics") is not None:
        raise RuntimeError("Inspection-only refuses active pass metrics.")
    if not isinstance(history, list) or len(history) != config.passes:
        raise RuntimeError("Inspection-only checkpoint history is incomplete.")
    metrics_path = run_dir / "iteration_metrics.json"
    if not metrics_path.is_file() or json.loads(
        metrics_path.read_text(encoding="utf-8")
    ) != history:
        raise RuntimeError(
            "Inspection-only iteration metrics do not match the checkpoint."
        )
    for table in (
        "counts_next",
        "piece_counts_next",
        "lexical_diagnostics_next",
    ):
        if store.has_table(table):
            raise RuntimeError(
                f"Inspection-only refuses unfinished training table: {table}."
            )
    final = history[-1]
    if config.model == S1M2_MODEL:
        if not store.has_table("piece_lexicon"):
            raise RuntimeError(
                "Inspection-only requires the final learned piece_lexicon."
            )
        row = store.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0) "
            "FROM piece_lexicon"
        ).fetchone()
        assert row is not None
        if (
            int(row[0]) != int(final.get("active_piece_types", -1))
            or float(row[1])
            != float(final.get("active_piece_count_total", -1.0))
        ):
            raise RuntimeError(
                "Inspection-only learned piece state differs from checkpoint history."
            )
    else:
        if not store.has_table("lexicon"):
            raise RuntimeError(
                "Inspection-only requires the final learned lexicon."
            )
        row = store.connection.execute("SELECT COUNT(*) FROM lexicon").fetchone()
        assert row is not None
        if int(row[0]) != int(final.get("lexicon_types", -1)):
            raise RuntimeError(
                "Inspection-only learned lexicon differs from checkpoint history."
            )


def _begin_inspection_provenance(
    *,
    run_dir: Path,
    training_provenance: dict[str, Any],
    inspection_git_commit: str,
    training_workers: int,
    inspection_workers: int,
    inspection_retained_factor_bytes: int,
    inspection_only: bool,
    execution_plan: ExecutionBundlePlan | None = None,
) -> dict[str, Any]:
    path = run_dir / "inspection_provenance.json"
    attempt = 1
    if path.is_file():
        previous = json.loads(path.read_text(encoding="utf-8"))
        attempt = int(previous.get("attempt", 0)) + 1
    payload = {
        "schema_version": "sktlm-inspection-execution/v1",
        "status": "running",
        "attempt": attempt,
        "mode": "inspection_only" if inspection_only else "train_then_inspect",
        "config_signature": training_provenance["config_signature"],
        "training_git_commit": training_provenance["git_commit"],
        "training_provenance_sha256": _file_sha256(
            run_dir / "provenance.json"
        ),
        "inspection_git_commit": inspection_git_commit,
        "training_workers": training_workers,
        "inspection_workers": inspection_workers,
        "adaptive_factor_retention": {
            "formula": INSPECTION_RETENTION_FORMULA,
            "segment_budget_bytes": inspection_retained_factor_bytes,
        },
    }
    if execution_plan is not None:
        payload["inspection_execution_bundle_plan"] = (
            execution_plan.provenance_payload()
        )
    _write_json(path, payload)
    return payload


def _complete_inspection_provenance(
    *,
    run_dir: Path,
    payload: dict[str, Any],
) -> None:
    completed = dict(payload)
    completed["status"] = "complete"
    completed["checkpoint_sha256"] = _file_sha256(run_dir / "checkpoint.json")
    completed["canonical_artifact_sha256"] = {
        name: _file_sha256(run_dir / name)
        for name in _S1M2_CANONICAL_SCIENTIFIC_ARTIFACTS
        if (run_dir / name).is_file()
    }
    _write_json(run_dir / "inspection_provenance.json", completed)


def run_training(
    config: TrainingConfig,
    *,
    repo_root: Path = Path("."),
    stop_after_training: bool = False,
    next_pass_only: bool = False,
    inspection_only: bool = False,
    inspection_workers: int | None = None,
) -> TrainingResult:
    """Train and inspect, or execute either durable phase independently."""

    if sum((stop_after_training, next_pass_only, inspection_only)) > 1:
        raise ValueError(
            "stop_after_training, next_pass_only, and inspection_only are "
            "mutually exclusive"
        )
    actual_inspection_workers = (
        config.workers if inspection_workers is None else inspection_workers
    )
    if actual_inspection_workers < 1:
        raise ValueError("inspection_workers must be >= 1")
    continuing = config.resume or inspection_only

    repo_root = repo_root.resolve()
    manifest = (
        config.manifest
        if config.manifest.is_absolute()
        else repo_root / config.manifest
    )
    run_dir = (
        config.output_root
        if config.output_root.is_absolute()
        else repo_root / config.output_root
    ) / _run_id(config)
    if run_dir.exists() and not continuing:
        raise FileExistsError(
            f"Run directory already exists; pass --resume to continue: {run_dir}"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    signature = _config_signature(config)
    store = LexiconStore(run_dir / "learner.sqlite")
    telemetry = store.telemetry
    try:
        stored_signature = store.get_metadata("config_signature")
        if stored_signature is not None and stored_signature != signature:
            raise ValueError(
                "Checkpoint config does not match the requested configuration."
            )
        if inspection_only and stored_signature is None:
            raise RuntimeError(
                "Inspection-only requires a durable configuration signature."
            )
        if stored_signature is None:
            store.set_metadata("config_signature", signature)
        documents = load_documents(
            manifest,
            repo_root=repo_root,
            max_documents=config.max_documents,
            script=config.script,
            condition=config.condition,
            document_list=(
                None
                if config.document_list is None
                else (
                    config.document_list
                    if config.document_list.is_absolute()
                    else repo_root / config.document_list
                )
            ),
        )
        execution_plan = None
        if config.execution_bundle_plan is not None:
            execution_plan = load_execution_bundle_plan(
                config.execution_bundle_plan,
                repo_root=repo_root,
                manifest=manifest,
                documents=documents,
                script=config.script,
                condition=config.condition,
                max_segment_tokens=config.max_segment_tokens,
                max_lines_per_document=config.max_lines_per_document,
                document_list=config.document_list,
            )
        grammar = StructuredSandhiGrammar.from_default_inventory()
        rules_path = repo_root / "data" / "rules" / "external_sandhi.tsv"
        current_git_commit = _git_commit(repo_root)
        expected_provenance = {
            "implementation": (
                IMPLEMENTATION if config.model == S1M1_MODEL else S1M2_MODEL
            ),
            "git_commit": current_git_commit,
            "training_git_commit": current_git_commit,
            "training_workers": config.workers,
            "freeze_id": EXPECTED_FREEZE_ID,
            "manifest": manifest.as_posix(),
            "manifest_sha256": _file_sha256(manifest),
            "rules_path": rules_path.as_posix(),
            "rules_sha256": _file_sha256(rules_path),
            "external_rule_count": len(grammar.rules),
            "script": config.script,
            "condition": config.condition,
            "document_count": len(documents),
            "document_list": (
                None
                if config.document_list is None
                else config.document_list.as_posix()
            ),
            "document_list_sha256": (
                None
                if config.document_list is None
                else _file_sha256(
                    config.document_list
                    if config.document_list.is_absolute()
                    else repo_root / config.document_list
                )
            ),
            "config_signature": signature,
            "seed": config.seed,
            "determinism": (
                "sorted manifest order, file order, rule IDs, graph nodes, and "
                "tie-break keys; no stochastic update"
            ),
        }
        if config.vocab_budget is not None:
            expected_provenance["vocabulary_budget"] = _pending_vocabulary_payload(
                config.vocab_budget
            )
        if execution_plan is not None:
            expected_provenance["training_execution_bundle_plan"] = (
                execution_plan.provenance_payload()
            )
        config_path = run_dir / "config.json"
        provenance_path = run_dir / "provenance.json"
        if continuing and config_path.is_file() and provenance_path.is_file():
            stored_config = json.loads(config_path.read_text(encoding="utf-8"))
            if stored_config != config.payload():
                raise ValueError(
                    "Stored config does not match the requested training identity."
                )
            provenance = json.loads(
                provenance_path.read_text(encoding="utf-8")
            )
            identity_fields = (
                "implementation",
                "freeze_id",
                "manifest_sha256",
                "rules_sha256",
                "external_rule_count",
                "script",
                "condition",
                "document_count",
                "document_list_sha256",
                "config_signature",
                "seed",
            )
            mismatches = tuple(
                name
                for name in identity_fields
                if provenance.get(name) != expected_provenance.get(name)
            )
            if mismatches:
                raise RuntimeError(
                    "Stored training provenance does not match frozen inputs: "
                    + ", ".join(mismatches)
                )
        elif inspection_only:
            raise RuntimeError(
                "Inspection-only requires existing config and training provenance."
            )
        else:
            provenance = expected_provenance
            _write_json(config_path, config.payload())
            _write_json(provenance_path, provenance)
        disk_checkpoint = _load_checkpoint(run_dir)
        database_checkpoint = store.load_training_checkpoint()
        if continuing:
            unsafe_legacy_progress = (
                database_checkpoint is None
                and (
                    store.has_table("counts_next")
                    or store.has_table("piece_counts_next")
                    or store.has_table("lexical_diagnostics_next")
                    or disk_checkpoint.get("active_pass") is not None
                    or int(disk_checkpoint.get("completed_passes", 0)) > 0
                )
            )
            if unsafe_legacy_progress:
                raise RuntimeError(
                    "This run predates transactionally coupled checkpoints and "
                    "cannot be resumed safely. Preserve it for diagnostics and "
                    "start a new run ID."
                )
            checkpoint = database_checkpoint or disk_checkpoint
            if inspection_only:
                if database_checkpoint is None:
                    raise RuntimeError(
                        "Inspection-only requires a durable database checkpoint."
                    )
                if database_checkpoint != disk_checkpoint:
                    raise RuntimeError(
                        "Inspection-only database and JSON checkpoints differ."
                    )
            elif (
                database_checkpoint is not None
                and database_checkpoint != disk_checkpoint
            ):
                _save_checkpoint(run_dir, database_checkpoint)
        else:
            checkpoint = disk_checkpoint
            store.save_training_checkpoint(checkpoint)
        completed_before_training = int(checkpoint.get("completed_passes", 0))
        active_pass = checkpoint.get("active_pass")
        stored_execution_plan = checkpoint.get("execution_bundle_plan")
        requested_execution_plan = (
            None
            if execution_plan is None
            else execution_plan.checkpoint_payload()
        )
        training_incomplete = completed_before_training < config.passes
        fresh_training_state = (
            completed_before_training == 0
            and active_pass is None
            and int(checkpoint.get("next_document_index", 0)) == 0
            and not checkpoint.get("history")
        )
        if not inspection_only and training_incomplete:
            if stored_execution_plan is None and requested_execution_plan is not None:
                if not fresh_training_state:
                    raise RuntimeError(
                        "Cannot introduce an execution bundle plan after training started."
                    )
                checkpoint["execution_bundle_plan"] = requested_execution_plan
                store.save_training_checkpoint(checkpoint)
                _save_checkpoint(run_dir, checkpoint)
            elif stored_execution_plan is not None:
                if requested_execution_plan is None:
                    raise RuntimeError(
                        "Active bundled training requires its original execution plan."
                    )
                if stored_execution_plan != requested_execution_plan:
                    raise RuntimeError(
                        "Execution bundle plan does not match the active checkpoint."
                    )
        frozen_vocabulary = store.load_frozen_vocabulary()
        if config.vocab_budget is None:
            if frozen_vocabulary is not None:
                raise RuntimeError(
                    "Unrestricted configuration cannot reuse a constrained learner."
                )
        else:
            recorded_budget = checkpoint.get("vocabulary_budget")
            if (
                recorded_budget is not None
                and int(recorded_budget.get("total_budget", -1))
                != config.vocab_budget
            ):
                raise ValueError(
                    "Checkpoint vocabulary budget does not match the configuration."
                )
            if frozen_vocabulary is None:
                if (
                    recorded_budget is not None
                    and recorded_budget.get("status") == "frozen"
                ):
                    raise RuntimeError(
                        "Checkpoint names a frozen vocabulary, but its durable table is missing."
                    )
                checkpoint["vocabulary_budget"] = _pending_vocabulary_payload(
                    config.vocab_budget
                )
            else:
                if frozen_vocabulary.total_budget != config.vocab_budget:
                    raise ValueError(
                        "Stored frozen vocabulary does not match vocab_budget."
                    )
                if (
                    recorded_budget is not None
                    and recorded_budget.get("allowed_key_sha256") is not None
                    and recorded_budget.get("allowed_key_sha256")
                    != frozen_vocabulary.allowed_sha256
                ):
                    raise RuntimeError(
                        "Checkpoint frozen-vocabulary SHA-256 does not match SQLite."
                    )
                checkpoint["vocabulary_budget"] = (
                    frozen_vocabulary.checkpoint_payload()
                )
                _materialize_vocabulary_artifacts(run_dir, frozen_vocabulary)
            store.save_training_checkpoint(checkpoint)
            _save_checkpoint(run_dir, checkpoint)
        completed = int(checkpoint.get("completed_passes", 0))
        if completed > config.passes:
            raise ValueError("Checkpoint has more passes than requested.")
        if inspection_only:
            _validate_inspection_only_state(
                store=store,
                checkpoint=checkpoint,
                config=config,
                run_dir=run_dir,
            )
        else:
            final_pass = (
                min(completed + 1, config.passes)
                if next_pass_only
                else config.passes
            )
            for pass_index in range(completed + 1, final_pass + 1):
                _training_pass(
                    pass_index=pass_index,
                    documents=documents,
                    grammar=grammar,
                    store=store,
                    config=config,
                    run_dir=run_dir,
                    checkpoint=checkpoint,
                    telemetry=telemetry,
                    execution_plan=execution_plan,
                )
            _write_json(
                run_dir / "iteration_metrics.json",
                checkpoint["history"],
            )
        if checkpoint.get("inspection_complete"):
            summary = json.loads(
                (run_dir / "summary.json").read_text(encoding="utf-8")
            )
            runtime = json.loads(
                (run_dir / "timing_metrics.json").read_text(encoding="utf-8")
            )
            _cleanup_inspection_shards(run_dir)
            inspection_provenance_path = run_dir / "inspection_provenance.json"
            if inspection_provenance_path.is_file():
                inspection_provenance = json.loads(
                    inspection_provenance_path.read_text(encoding="utf-8")
                )
                if inspection_provenance.get("status") != "complete":
                    _complete_inspection_provenance(
                        run_dir=run_dir,
                        payload=inspection_provenance,
                    )
            return TrainingResult(
                run_dir=run_dir,
                history=tuple(checkpoint["history"]),
                summary=summary,
                runtime=runtime,
            )
        if stop_after_training or next_pass_only:
            runtime = store.runtime_payload()
            runtime["grammar_cache"] = grammar.cache_statistics()
            return TrainingResult(
                run_dir=run_dir,
                history=tuple(checkpoint["history"]),
                summary=dict(checkpoint["history"][-1]),
                runtime=runtime,
                inspection_complete=False,
            )
        inspection_provenance = _begin_inspection_provenance(
            run_dir=run_dir,
            training_provenance=provenance,
            inspection_git_commit=current_git_commit,
            training_workers=config.workers,
            inspection_workers=actual_inspection_workers,
            inspection_retained_factor_bytes=(
                config.inspection_retained_factor_bytes
            ),
            inspection_only=inspection_only,
            execution_plan=execution_plan,
        )
        summary = _inspection_pass(
            documents=documents,
            grammar=grammar,
            store=store,
            config=config,
            inspection_workers=actual_inspection_workers,
            run_dir=run_dir,
            telemetry=telemetry,
            execution_plan=execution_plan,
        )
        _record_store_storage(telemetry, store.path)
        telemetry.maximum(
            "artifact_bytes_before_timing_metrics",
            _existing_path_bytes(run_dir.rglob("*")),
        )
        if config.model == S1M2_MODEL:
            storage_manifest = _compact_completed_s1m2_storage(
                store=store,
                run_dir=run_dir,
            )
            telemetry.gauges["sqlite_compacted_database_bytes"] = int(
                storage_manifest["after_bytes"]["database"]
            )
            telemetry.gauges["sqlite_compacted_total_bytes"] = int(
                storage_manifest["after_bytes"]["total"]
            )
            telemetry.gauges["sqlite_completed_state_bytes_saved"] = int(
                storage_manifest["bytes_saved"]
            )
        checkpoint["inspection_complete"] = True
        if config.model == S1M2_MODEL:
            store.save_training_checkpoint(checkpoint)
            store.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            _timed_checkpoint(run_dir, checkpoint, telemetry)
            _cleanup_inspection_shards(run_dir)
            runtime = store.runtime_payload()
            runtime['grammar_cache'] = grammar.cache_statistics()
            _write_json(run_dir / 'timing_metrics.json', runtime)
        else:
            runtime = store.runtime_payload()
            runtime['grammar_cache'] = grammar.cache_statistics()
            _write_json(run_dir / 'timing_metrics.json', runtime)
            store.save_training_checkpoint(checkpoint)
            _timed_checkpoint(run_dir, checkpoint, telemetry)
            _cleanup_inspection_shards(run_dir)
        _complete_inspection_provenance(
            run_dir=run_dir,
            payload=inspection_provenance,
        )
        return TrainingResult(
            run_dir=run_dir,
            history=tuple(checkpoint["history"]),
            summary=summary,
            runtime=runtime,
        )
    finally:
        store.close()
