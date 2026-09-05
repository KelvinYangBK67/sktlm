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
import time
from collections import Counter
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from sktlm.latent.candidates import (
    CandidateConfig,
    build_candidate_graph,
    candidate_graph_fingerprint,
    candidate_graph_statistics,
)
from sktlm.latent.frontend import ObservedSegment, iter_observed_segments
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
    ComposedPieceInference,
    ComposedSegmentInference,
    infer_composed_segment,
)
from sktlm.pieces.model import PieceModelConfig
from sktlm.pieces.scorer import NeutralPieceScorer


EXPECTED_FREEZE_ID = "9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40"
IMPLEMENTATION = "latent-lexicon-v1"
S1M1_MODEL = "latent_lexicon_v1"
S1M2_MODEL = "reusable_pieces_v1"
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
        )

    def payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["manifest"] = self.manifest.as_posix()
        payload["document_list"] = (
            None if self.document_list is None else self.document_list.as_posix()
        )
        payload["output_root"] = self.output_root.as_posix()
        payload.pop("resume")
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
) -> None:
    gauges = {
        "piece_score_cache_entries",
        "piece_score_cache_estimated_bytes",
        "form_cache_entries",
        "form_cache_estimated_bytes",
    }
    for name, value in asdict(counters).items():
        label = f"{phase}_{name}"
        if name in gauges:
            telemetry.maximum(label, int(value))
        else:
            telemetry.increment(label, int(value))


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

    with temporary.open('w', encoding='utf-8', newline='') as handle:
        iterator = _iter_document_segments(document, config)
        while True:
            started = time.perf_counter()
            try:
                line_number, _, segment = next(iterator)
            except StopIteration:
                frontend_seconds += time.perf_counter() - started
                break
            frontend_seconds += time.perf_counter() - started
            seen_lines.add(line_number)
            started = time.perf_counter()
            graph = (
                build_candidate_graph(
                    segment,
                    _WORKER_GRAMMAR,
                    config.candidate_config,
                )
                if config.model == S1M1_MODEL
                else build_lazy_candidate_graph(
                    segment,
                    _WORKER_GRAMMAR,
                    config.candidate_config,
                )
            )
            candidate_seconds += time.perf_counter() - started
            candidate_counts = (
                candidate_graph_statistics(graph)
                if config.model == S1M1_MODEL
                else lazy_candidate_graph_statistics(graph)
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
        },
    }
    _write_json(marker_path, payload)
    return payload


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

        fill_pending()
        for document_index in range(start_document, len(documents)):
            item = pending.pop(document_index)
            payload = item.result() if isinstance(item, Future) else item
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
        start_document = len(documents)

    for document_index in range(start_document, len(documents)):
        document = documents[document_index]
        counts: Counter[PhonologicalForm] = Counter()
        piece_counts: Counter[PhonologicalForm] = Counter()
        piece_support: Counter[PhonologicalForm] = Counter()
        seen_lines: set[int] = set()
        document_metrics = PassMetrics()
        document_started = telemetry.now()
        store.begin_document_counts()
        try:
            for line_number, _, segment in _profiled_document_segments(
                document,
                config,
                telemetry,
                phase='training',
            ):
                seen_lines.add(line_number)
                started = telemetry.now()
                graph = (
                    build_candidate_graph(segment, grammar, config.candidate_config)
                    if config.model == S1M1_MODEL
                    else build_lazy_candidate_graph(
                        segment, grammar, config.candidate_config
                    )
                )
                telemetry.elapsed('training_candidate_generation', started)
                candidate_counts = (
                    candidate_graph_statistics(graph)
                    if config.model == S1M1_MODEL
                    else lazy_candidate_graph_statistics(graph)
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
                    )
                    _record_composed_telemetry(
                        telemetry,
                        inference.counters,
                        phase="training",
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
        except BaseException:
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


_INSPECTION_SHARD_KINDS = (
    "analyses",
    "boundaries",
    "counts",
    "pieces",
    "surfaces",
    "contexts",
    "reductions",
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
        "counts": root / f"{stem}.counts.tsv",
        "pieces": root / f"{stem}.pieces.tsv",
        "surfaces": root / f"{stem}.surfaces.tsv",
        "contexts": root / f"{stem}.contexts.tsv",
        "reductions": root / f"{stem}.reductions.jsonl",
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
    temporary = {
        kind: paths[kind].with_suffix(paths[kind].suffix + ".tmp")
        for kind in _INSPECTION_SHARD_KINDS
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

    def flush_counts(handle: Any) -> None:
        nonlocal count_rows
        if not counts:
            return
        for form, value in sorted(counts.items(), key=lambda item: item[0].key):
            handle.write(f"{form.key}\t{float(value).hex()}\n")
            count_rows += 1
        counts.clear()

    def flush_pieces(handle: Any) -> None:
        nonlocal piece_rows
        if not piece_counts:
            return
        for piece, value in sorted(
            piece_counts.items(), key=lambda item: item[0].key
        ):
            handle.write(
                f"{piece.key}\t{float(value).hex()}\t{piece_support[piece]}\n"
            )
            piece_rows += 1
        piece_counts.clear()
        piece_support.clear()

    handles: dict[str, Any] = {}
    try:
        for kind in _INSPECTION_SHARD_KINDS:
            handles[kind] = temporary[kind].open(
                "w",
                encoding="utf-8",
                newline="",
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
            started = time.perf_counter()
            graph = (
                build_candidate_graph(
                    segment,
                    _WORKER_GRAMMAR,
                    config.candidate_config,
                )
                if config.model == S1M1_MODEL
                else build_lazy_candidate_graph(
                    segment,
                    _WORKER_GRAMMAR,
                    config.candidate_config,
                )
            )
            candidate_seconds += time.perf_counter() - started
            candidate_values = (
                candidate_graph_statistics(graph)
                if config.model == S1M1_MODEL
                else lazy_candidate_graph_statistics(graph)
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
                    surface = json.dumps(segment.written, ensure_ascii=False)
                    handles["surfaces"].write(
                        f"{form.key}\t{surface}\t{float(mass).hex()}\n"
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
                    context = json.dumps(f"{left}>{right}", ensure_ascii=False)
                    handles["contexts"].write(
                        f"{word.key}\t{context}\t{float(analysis.probability).hex()}\n"
                    )
                    context_rows += 1
            if len(counts) + len(piece_counts) >= config.flush_types:
                flush_counts(handles["counts"])
                flush_pieces(handles["pieces"])
        flush_counts(handles["counts"])
        flush_pieces(handles["pieces"])
        for handle in handles.values():
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        for handle in handles.values():
            handle.close()
    for kind in _INSPECTION_SHARD_KINDS:
        _replace_file(temporary[kind], paths[kind])
    payload = {
        "schema_version": 1,
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
            kind: _file_sha256(paths[kind]) for kind in _INSPECTION_SHARD_KINDS
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
        },
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
    for kind in _INSPECTION_SHARD_KINDS:
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
    document_index = int(payload["document_index"])
    paths = _inspection_shard_paths(run_dir, document_index)
    with paths["analyses"].open("rb") as source:
        shutil.copyfileobj(source, analyses_handle, length=1024 * 1024)
    with paths["boundaries"].open("rb") as source:
        shutil.copyfileobj(source, boundaries_handle, length=1024 * 1024)

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
    ):
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
        "rule_expected_usage_total": sum(aggregate.rule_usage.values()),
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


def _parallel_inspection_pass(
    *,
    documents: tuple[CorpusDocument, ...],
    grammar: StructuredSandhiGrammar,
    store: LexiconStore,
    config: TrainingConfig,
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
        max_workers=config.workers,
        mp_context=context,
        initializer=_initialize_inspection_worker,
        initargs=(store.path, config, vocabulary),
    ) as executor:
        max_pending = config.workers * 2
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

        fill_pending()
        for document_index in range(len(documents)):
            item = pending.pop(document_index)
            payload = item.result() if isinstance(item, Future) else item
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


def _inspection_pass(
    *,
    documents: tuple[CorpusDocument, ...],
    grammar: StructuredSandhiGrammar,
    store: LexiconStore,
    config: TrainingConfig,
    run_dir: Path,
    telemetry: RuntimeTelemetry,
) -> dict[str, Any]:
    if config.model == S1M1_MODEL:
        store.begin_inspection()
    else:
        store.begin_piece_inspection()
    if config.workers > 1:
        return _parallel_inspection_pass(
            documents=documents,
            grammar=grammar,
            store=store,
            config=config,
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
        for document in documents:
            document_started = telemetry.now()
            seen_lines: set[int] = set()
            surface_usage: list[tuple[str, str, float]] = []
            context_usage: list[tuple[str, str, float]] = []
            for line_number, segment_index, segment in _profiled_document_segments(
                document,
                config,
                telemetry,
                phase='inspection',
            ):
                seen_lines.add(line_number)
                started = telemetry.now()
                graph = (
                    build_candidate_graph(segment, grammar, config.candidate_config)
                    if config.model == S1M1_MODEL
                    else build_lazy_candidate_graph(
                        segment, grammar, config.candidate_config
                    )
                )
                telemetry.elapsed('inspection_candidate_generation', started)
                candidate_counts = (
                    candidate_graph_statistics(graph)
                    if config.model == S1M1_MODEL
                    else lazy_candidate_graph_statistics(graph)
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
                    )
                    _record_composed_telemetry(
                        telemetry,
                        inference.counters,
                        phase="inspection",
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


def run_training(
    config: TrainingConfig,
    *,
    repo_root: Path = Path("."),
) -> TrainingResult:
    """Train with streaming passes, then write a final posterior inspection."""

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
    if run_dir.exists() and not config.resume:
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
        grammar = StructuredSandhiGrammar.from_default_inventory()
        rules_path = repo_root / "data" / "rules" / "external_sandhi.tsv"
        provenance = {
            "implementation": (
                IMPLEMENTATION if config.model == S1M1_MODEL else S1M2_MODEL
            ),
            "git_commit": _git_commit(repo_root),
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
            provenance["vocabulary_budget"] = _pending_vocabulary_payload(
                config.vocab_budget
            )
        _write_json(run_dir / "config.json", config.payload())
        _write_json(run_dir / "provenance.json", provenance)
        disk_checkpoint = _load_checkpoint(run_dir)
        database_checkpoint = store.load_training_checkpoint()
        if config.resume:
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
            if database_checkpoint is not None and database_checkpoint != disk_checkpoint:
                _save_checkpoint(run_dir, database_checkpoint)
        else:
            checkpoint = disk_checkpoint
            store.save_training_checkpoint(checkpoint)
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
        for pass_index in range(completed + 1, config.passes + 1):
            _training_pass(
                pass_index=pass_index,
                documents=documents,
                grammar=grammar,
                store=store,
                config=config,
                run_dir=run_dir,
                checkpoint=checkpoint,
                telemetry=telemetry,
            )
        _write_json(run_dir / "iteration_metrics.json", checkpoint["history"])
        if checkpoint.get("inspection_complete"):
            summary = json.loads(
                (run_dir / "summary.json").read_text(encoding="utf-8")
            )
            runtime = json.loads(
                (run_dir / "timing_metrics.json").read_text(encoding="utf-8")
            )
            _cleanup_inspection_shards(run_dir)
            return TrainingResult(
                run_dir=run_dir,
                history=tuple(checkpoint["history"]),
                summary=summary,
                runtime=runtime,
            )
        summary = _inspection_pass(
            documents=documents,
            grammar=grammar,
            store=store,
            config=config,
            run_dir=run_dir,
            telemetry=telemetry,
        )
        runtime = store.runtime_payload()
        runtime['grammar_cache'] = grammar.cache_statistics()
        _write_json(run_dir / 'timing_metrics.json', runtime)
        checkpoint["inspection_complete"] = True
        store.save_training_checkpoint(checkpoint)
        _timed_checkpoint(run_dir, checkpoint, telemetry)
        _cleanup_inspection_shards(run_dir)
        return TrainingResult(
            run_dir=run_dir,
            history=tuple(checkpoint["history"]),
            summary=summary,
            runtime=runtime,
        )
    finally:
        store.close()
