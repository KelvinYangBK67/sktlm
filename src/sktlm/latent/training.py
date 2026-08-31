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
from sktlm.latent.store import LexiconScorer, LexiconStore
from sktlm.latent.telemetry import RuntimeTelemetry
from sktlm.latent.vocabulary import (
    BASE_UNIT_COUNT,
    RANKING_RULE,
    SELECTION_PASS,
    FrozenVocabulary,
)


EXPECTED_FREEZE_ID = "9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40"
IMPLEMENTATION = "latent-lexicon-v1"

_WORKER_GRAMMAR: StructuredSandhiGrammar | None = None
_WORKER_SCORER: NeutralFormScorer | LexiconScorer | None = None
_WORKER_CONNECTION: sqlite3.Connection | None = None
_WORKER_VOCABULARY: FrozenVocabulary | None = None


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    manifest: Path = Path("data/manifests/representations.csv")
    document_list: Path | None = None
    output_root: Path = Path("artifacts/latent_lexicon")
    run_id: str | None = None
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
    resume: bool = False

    def __post_init__(self) -> None:
        if self.passes < 1:
            raise ValueError("passes must be >= 1")
        if self.vocab_budget is not None and self.vocab_budget < BASE_UNIT_COUNT:
            raise ValueError(
                f"vocab_budget must be >= {BASE_UNIT_COUNT}; got {self.vocab_budget}"
            )
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
        return payload

    @property
    def candidate_config(self) -> CandidateConfig:
        return CandidateConfig(
            max_internal_matches=self.max_internal_matches,
            allow_whitespace_merge=self.allow_whitespace_merge,
            whitespace_merge_penalty=self.whitespace_merge_penalty,
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
    overflowed_tokens: int = 0
    candidate_factors: int = 0
    candidate_nodes: int = 0
    candidate_edges: int = 0

    def update(
        self,
        segment: ObservedSegment,
        inference: SegmentInference | TrainingSegmentInference,
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
            "overflowed_tokens": self.overflowed_tokens,
            "candidate_factors": self.candidate_factors,
            "candidate_nodes": self.candidate_nodes,
            "candidate_edges": self.candidate_edges,
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
            overflowed_tokens=self.overflowed_tokens + other.overflowed_tokens,
            candidate_factors=self.candidate_factors + other.candidate_factors,
            candidate_nodes=self.candidate_nodes + other.candidate_nodes,
            candidate_edges=self.candidate_edges + other.candidate_edges,
        )


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
    return config.run_id or f"m0_iast_surface_word_{_config_signature(config)[:12]}"


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
) -> tuple[CorpusDocument, ...]:
    with manifest.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("script") == "iast"
            and row.get("condition") == "surface_word"
        ]
    if not rows:
        raise ValueError("Manifest has no IAST + surface_word rows.")
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
        overflowed_tokens=int(payload.get("overflowed_tokens", 0)),
        candidate_factors=int(payload.get("candidate_factors", 0)),
        candidate_nodes=int(payload.get("candidate_nodes", 0)),
        candidate_edges=int(payload.get("candidate_edges", 0)),
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
    global _WORKER_CONNECTION, _WORKER_GRAMMAR, _WORKER_SCORER, _WORKER_VOCABULARY
    _WORKER_GRAMMAR = StructuredSandhiGrammar.from_default_inventory()
    _WORKER_VOCABULARY = vocabulary
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
    if _WORKER_GRAMMAR is None or _WORKER_SCORER is None:
        raise RuntimeError('Training worker was not initialized.')
    shard_path, marker_path = _training_shard_paths(
        run_dir,
        pass_index,
        document_index,
    )
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = shard_path.with_suffix(shard_path.suffix + '.tmp')
    counts: Counter[PhonologicalForm] = Counter()
    metrics = PassMetrics()
    seen_lines: set[int] = set()
    row_count = 0
    candidate_seconds = 0.0
    inference_seconds = 0.0
    aggregation_seconds = 0.0
    frontend_seconds = 0.0
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    scorer_calls_before = int(getattr(_WORKER_SCORER, 'score_calls', 0))
    sqlite_selects_before = int(getattr(_WORKER_SCORER, 'sqlite_selects', 0))
    sqlite_seconds_before = float(getattr(_WORKER_SCORER, 'sqlite_seconds', 0.0))

    def flush(handle: Any) -> None:
        nonlocal row_count
        if not counts:
            return
        for form, value in sorted(counts.items(), key=lambda item: item[0].key):
            handle.write(f'{form.key}\t{float(value).hex()}\n')
            row_count += 1
        counts.clear()

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
            graph = build_candidate_graph(
                segment,
                _WORKER_GRAMMAR,
                config.candidate_config,
            )
            candidate_seconds += time.perf_counter() - started
            candidate_counts = candidate_graph_statistics(graph)
            started = time.perf_counter()
            inference = infer_training_segment(
                graph,
                _WORKER_SCORER,
                whitespace_merge_penalty=config.whitespace_merge_penalty,
                vocabulary=_WORKER_VOCABULARY,
            )
            inference_seconds += time.perf_counter() - started
            started = time.perf_counter()
            counts.update(inference.expected_counts)
            aggregation_seconds += time.perf_counter() - started
            metrics.update(
                segment,
                inference,
                overflowed_tokens=graph.overflowed_tokens,
                candidate_factors=candidate_counts['factors'],
                candidate_nodes=candidate_counts['lattice_nodes'],
                candidate_edges=candidate_counts['lexical_edges'],
            )
            if len(counts) >= config.flush_types:
                flush(handle)
        flush(handle)
        handle.flush()
        os.fsync(handle.fileno())
    _replace_file(temporary, shard_path)
    metrics.documents = 1
    metrics.lines = len(seen_lines)
    payload = {
        'schema_version': 1,
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
                int(getattr(_WORKER_SCORER, 'score_calls', 0))
                - scorer_calls_before
            ),
            'sqlite_selects': (
                int(getattr(_WORKER_SCORER, 'sqlite_selects', 0))
                - sqlite_selects_before
            ),
            'sqlite_seconds': (
                float(getattr(_WORKER_SCORER, 'sqlite_seconds', 0.0))
                - sqlite_seconds_before
            ),
        },
    }
    _write_json(marker_path, payload)
    return payload


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
        with shard_path.open(encoding='utf-8') as handle:
            for line in handle:
                key, value = line.rstrip('\n').split('\t', 1)
                buffered.append((PhonologicalForm.from_key(key), float.fromhex(value)))
                if len(buffered) >= config.flush_types:
                    store.add_document_counts(buffered)
                    buffered.clear()
        if buffered:
            store.add_document_counts(buffered)
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
    if config.workers == 1:
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
    checkpoint.update(
        {
            "active_pass": pass_index,
            "next_document_index": start_document,
            "active_metrics": asdict(metrics),
        }
    )
    store.begin_count_pass(resume=resuming, checkpoint=checkpoint)
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
                graph = build_candidate_graph(segment, grammar, config.candidate_config)
                telemetry.elapsed('training_candidate_generation', started)
                candidate_counts = candidate_graph_statistics(graph)
                started = telemetry.now()
                assert scorer is not None
                inference = infer_training_segment(
                    graph,
                    scorer,
                    whitespace_merge_penalty=config.whitespace_merge_penalty,
                    vocabulary=vocabulary,
                )
                telemetry.elapsed('training_inference', started)
                started = telemetry.now()
                counts.update(inference.expected_counts)
                telemetry.elapsed('training_count_aggregation', started)
                document_metrics.update(
                    segment,
                    inference,
                    overflowed_tokens=graph.overflowed_tokens,
                    candidate_factors=candidate_counts["factors"],
                    candidate_nodes=candidate_counts["lattice_nodes"],
                    candidate_edges=candidate_counts["lexical_edges"],
                )
                if len(counts) >= config.flush_types:
                    _flush_counts(
                        store,
                        counts,
                        document_transaction=True,
                    )
            _flush_counts(
                store,
                counts,
                document_transaction=True,
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

    row = store.connection.execute(
        "SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0) FROM counts_next"
    ).fetchone()
    assert row is not None
    vocabulary_size = int(row[0])
    total_count = float(row[1])
    summary = metrics.summary(pass_index)
    summary["lexicon_types"] = vocabulary_size
    summary["lexical_count_total"] = total_count
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
    store.finalize_count_pass(
        alpha=config.lexical_alpha,
        checkpoint=checkpoint,
    )
    telemetry.elapsed('lexicon_finalize', started)
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
    _initialize_training_worker(2, database_path, config, vocabulary)


def _write_inspection_shard(
    document_index: int,
    document: CorpusDocument,
    config: TrainingConfig,
    run_dir: Path,
    config_signature: str,
) -> dict[str, Any]:
    if _WORKER_GRAMMAR is None or _WORKER_SCORER is None:
        raise RuntimeError("Inspection worker was not initialized.")
    paths = _inspection_shard_paths(run_dir, document_index)
    paths["marker"].parent.mkdir(parents=True, exist_ok=True)
    temporary = {
        kind: paths[kind].with_suffix(paths[kind].suffix + ".tmp")
        for kind in _INSPECTION_SHARD_KINDS
    }
    counts: Counter[PhonologicalForm] = Counter()
    seen_lines: set[int] = set()
    count_rows = 0
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
    scorer_calls_before = int(getattr(_WORKER_SCORER, "score_calls", 0))
    sqlite_selects_before = int(getattr(_WORKER_SCORER, "sqlite_selects", 0))
    sqlite_seconds_before = float(getattr(_WORKER_SCORER, "sqlite_seconds", 0.0))

    def flush_counts(handle: Any) -> None:
        nonlocal count_rows
        if not counts:
            return
        for form, value in sorted(counts.items(), key=lambda item: item[0].key):
            handle.write(f"{form.key}\t{float(value).hex()}\n")
            count_rows += 1
        counts.clear()

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
            graph = build_candidate_graph(
                segment,
                _WORKER_GRAMMAR,
                config.candidate_config,
            )
            candidate_seconds += time.perf_counter() - started
            candidate_values = candidate_graph_statistics(graph)
            started = time.perf_counter()
            inference = infer_segment(
                graph,
                _WORKER_SCORER,
                whitespace_merge_penalty=config.whitespace_merge_penalty,
                top_k=config.analysis_top_k,
                vocabulary=_WORKER_VOCABULARY,
            )
            inference_seconds += time.perf_counter() - started
            started = time.perf_counter()
            counts.update(inference.expected_counts)
            aggregation_seconds += time.perf_counter() - started

            serialization_started = time.perf_counter()
            segment_id = (
                f"{document.document_id}:l{line_number:08d}:"
                f"s{segment_index:04d}"
            )
            analysis_row = {
                "schema_version": 1,
                "segment_id": segment_id,
                "document": document.relative_path,
                "line_number": line_number,
                "source_start": segment.source_start,
                "source_end": segment.source_end,
                "surface": segment.written,
                "top_analyses": [
                    _analysis_payload(analysis)
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
            if config.equivalence_diagnostics:
                analysis_row["candidate_fingerprint"] = candidate_graph_fingerprint(
                    graph
                )
            handles["analyses"].write(
                json.dumps(analysis_row, ensure_ascii=False, sort_keys=True) + "\n"
            )
            boundary_row = {
                "schema_version": 1,
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
                "candidate_edges": candidate_values["lexical_edges"],
                "top_probability": top_probability,
                "entropy": inference.entropy,
                "rule_usage": dict(inference.rule_usage),
                "report": report_payload,
            }
            handles["reductions"].write(
                json.dumps(reduction_row, ensure_ascii=False, sort_keys=True) + "\n"
            )
            reduction_rows += 1

            for form, mass in inference.expected_counts.items():
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
            if len(counts) >= config.flush_types:
                flush_counts(handles["counts"])
        flush_counts(handles["counts"])
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
                int(getattr(_WORKER_SCORER, "score_calls", 0))
                - scorer_calls_before
            ),
            "sqlite_selects": (
                int(getattr(_WORKER_SCORER, "sqlite_selects", 0))
                - sqlite_selects_before
            ),
            "sqlite_seconds": (
                float(getattr(_WORKER_SCORER, "sqlite_seconds", 0.0))
                - sqlite_seconds_before
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
            metrics.overflowed_tokens += int(row["overflowed_tokens"])
            metrics.candidate_factors += int(row["candidate_factors"])
            metrics.candidate_nodes += int(row["candidate_nodes"])
            metrics.candidate_edges += int(row["candidate_edges"])
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
    store.export_lexicon(
        run_dir / "latent_lexicon.tsv",
        usage_threshold=config.usage_posterior_threshold,
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

    complexity = store.complexity_summary(
        weight=config.complexity_weight,
        tau=config.complexity_tau,
        low_count_threshold=config.low_count_threshold,
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
    vocabulary = store.load_frozen_vocabulary()
    if vocabulary is not None:
        summary["vocabulary_budget"] = vocabulary.checkpoint_payload()
    _write_json(run_dir / "summary.json", summary)
    report = _human_report(
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
    store.begin_inspection()
    if config.workers > 1:
        return _parallel_inspection_pass(
            documents=documents,
            grammar=grammar,
            store=store,
            config=config,
            run_dir=run_dir,
            telemetry=telemetry,
        )
    scorer = store.scorer(
        alpha=config.lexical_alpha,
        complexity_weight=config.complexity_weight,
        complexity_tau=config.complexity_tau,
        cache_size=config.lexicon_cache_size,
    )
    vocabulary = store.load_frozen_vocabulary()
    if config.vocab_budget is not None and vocabulary is None:
        raise RuntimeError("Inspection requires the frozen pass-1 vocabulary.")
    analyses_tmp = run_dir / "analyses.jsonl.tmp"
    boundaries_tmp = run_dir / "boundary_posteriors.jsonl.tmp"
    rule_usage: Counter[str] = Counter()
    counts: Counter[PhonologicalForm] = Counter()
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
                graph = build_candidate_graph(segment, grammar, config.candidate_config)
                telemetry.elapsed('inspection_candidate_generation', started)
                candidate_counts = candidate_graph_statistics(graph)
                started = telemetry.now()
                inference = infer_segment(
                    graph,
                    scorer,
                    whitespace_merge_penalty=config.whitespace_merge_penalty,
                    top_k=config.analysis_top_k,
                    vocabulary=vocabulary,
                )
                telemetry.elapsed('inspection_inference', started)
                started = telemetry.now()
                counts.update(inference.expected_counts)
                rule_usage.update(inference.rule_usage)
                telemetry.elapsed('inspection_count_aggregation', started)
                metrics.update(
                    segment,
                    inference,
                    overflowed_tokens=graph.overflowed_tokens,
                    candidate_factors=candidate_counts["factors"],
                    candidate_nodes=candidate_counts["lattice_nodes"],
                    candidate_edges=candidate_counts["lexical_edges"],
                )
                serialization_started = telemetry.now()
                segment_id = (
                    f"{document.document_id}:l{line_number:08d}:"
                    f"s{segment_index:04d}"
                )
                row = {
                    "schema_version": 1,
                    "segment_id": segment_id,
                    "document": document.relative_path,
                    "line_number": line_number,
                    "source_start": segment.source_start,
                    "source_end": segment.source_end,
                    "surface": segment.written,
                    "top_analyses": [
                        _analysis_payload(analysis)
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
                if config.equivalence_diagnostics:
                    row["candidate_fingerprint"] = candidate_graph_fingerprint(graph)
                analyses_handle.write(
                    json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                )
                boundary_row = {
                    "schema_version": 1,
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

                for form, mass in inference.expected_counts.items():
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
                if len(surface_usage) + len(context_usage) >= config.flush_types:
                    store.add_usage(
                        surfaces=surface_usage,
                        contexts=context_usage,
                    )
                    surface_usage.clear()
                    context_usage.clear()
            _flush_counts(store, counts, table="inspection_counts")
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
            "implementation": IMPLEMENTATION,
            "git_commit": _git_commit(repo_root),
            "freeze_id": EXPECTED_FREEZE_ID,
            "manifest": manifest.as_posix(),
            "manifest_sha256": _file_sha256(manifest),
            "rules_path": rules_path.as_posix(),
            "rules_sha256": _file_sha256(rules_path),
            "external_rule_count": len(grammar.rules),
            "script": "iast",
            "condition": "surface_word",
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
