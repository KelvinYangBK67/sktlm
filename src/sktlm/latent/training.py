"""Streaming corpus training and research artifacts for latent lexicon v1."""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from sktlm.latent.candidates import CandidateConfig, build_candidate_graph
from sktlm.latent.frontend import ObservedSegment, iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.inference import (
    AnalysisPosterior,
    NeutralFormScorer,
    SegmentInference,
    infer_segment,
)
from sktlm.latent.phonology import PhonologicalForm
from sktlm.latent.store import LexiconStore


EXPECTED_FREEZE_ID = "9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40"
IMPLEMENTATION = "latent-lexicon-v1"


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    manifest: Path = Path("data/manifests/representations.csv")
    output_root: Path = Path("artifacts/latent_lexicon")
    run_id: str | None = None
    passes: int = 3
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
    resume: bool = False

    def __post_init__(self) -> None:
        if self.passes < 1:
            raise ValueError("passes must be >= 1")
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
        payload["output_root"] = self.output_root.as_posix()
        payload.pop("resume")
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

    def update(
        self,
        segment: ObservedSegment,
        inference: SegmentInference,
        *,
        overflowed_tokens: int,
    ) -> None:
        self.segments += 1
        self.characters += len(segment.written)
        self.log_partition += inference.log_partition
        self.identity_mass_sum += inference.identity_mass
        self.latent_mass_sum += inference.latent_mass
        self.expected_lexical_tokens += inference.expected_lexical_tokens
        self.overflowed_tokens += overflowed_tokens

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
        }


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


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    temporary.replace(path)


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


def _flush_counts(
    store: LexiconStore,
    counts: Counter[PhonologicalForm],
    *,
    table: str = "counts_next",
) -> None:
    if counts:
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
    )


def _training_pass(
    *,
    pass_index: int,
    documents: tuple[CorpusDocument, ...],
    grammar: StructuredSandhiGrammar,
    store: LexiconStore,
    config: TrainingConfig,
    run_dir: Path,
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    resuming = checkpoint.get("active_pass") == pass_index
    start_document = int(checkpoint.get("next_document_index", 0)) if resuming else 0
    metrics = _metrics_from_mapping(checkpoint.get("active_metrics") if resuming else None)
    store.begin_count_pass(resume=resuming)
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
    _save_checkpoint(run_dir, checkpoint)

    for document_index in range(start_document, len(documents)):
        document = documents[document_index]
        counts: Counter[PhonologicalForm] = Counter()
        seen_lines: set[int] = set()
        for line_number, _, segment in _iter_document_segments(document, config):
            seen_lines.add(line_number)
            graph = build_candidate_graph(segment, grammar, config.candidate_config)
            inference = infer_segment(
                graph,
                scorer,
                whitespace_merge_penalty=config.whitespace_merge_penalty,
                top_k=1,
            )
            counts.update(inference.expected_counts)
            metrics.update(
                segment,
                inference,
                overflowed_tokens=graph.overflowed_tokens,
            )
            if len(counts) >= config.flush_types:
                _flush_counts(store, counts)
        _flush_counts(store, counts)
        metrics.documents += 1
        metrics.lines += len(seen_lines)
        checkpoint.update(
            {
                "active_pass": pass_index,
                "next_document_index": document_index + 1,
                "active_metrics": asdict(metrics),
            }
        )
        _save_checkpoint(run_dir, checkpoint)

    vocabulary_size, total_count = store.finalize_count_pass(
        alpha=config.lexical_alpha
    )
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
    _save_checkpoint(run_dir, checkpoint)
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


def _inspection_pass(
    *,
    documents: tuple[CorpusDocument, ...],
    grammar: StructuredSandhiGrammar,
    store: LexiconStore,
    config: TrainingConfig,
    run_dir: Path,
) -> dict[str, Any]:
    store.begin_inspection()
    scorer = store.scorer(
        alpha=config.lexical_alpha,
        complexity_weight=config.complexity_weight,
        complexity_tau=config.complexity_tau,
        cache_size=config.lexicon_cache_size,
    )
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
            seen_lines: set[int] = set()
            surface_usage: list[tuple[str, str, float]] = []
            context_usage: list[tuple[str, str, float]] = []
            for line_number, segment_index, segment in _iter_document_segments(
                document,
                config,
            ):
                seen_lines.add(line_number)
                graph = build_candidate_graph(segment, grammar, config.candidate_config)
                inference = infer_segment(
                    graph,
                    scorer,
                    whitespace_merge_penalty=config.whitespace_merge_penalty,
                    top_k=config.analysis_top_k,
                )
                counts.update(inference.expected_counts)
                rule_usage.update(inference.rule_usage)
                metrics.update(
                    segment,
                    inference,
                    overflowed_tokens=graph.overflowed_tokens,
                )
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
                }
                analyses_handle.write(
                    json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                )
                boundary_row = {
                    "schema_version": 1,
                    "segment_id": segment_id,
                    "surface": segment.written,
                    "boundaries": [asdict(item) for item in inference.boundary_posteriors],
                }
                boundaries_handle.write(
                    json.dumps(boundary_row, ensure_ascii=False, sort_keys=True) + "\n"
                )

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

    analyses_tmp.replace(run_dir / "analyses.jsonl")
    boundaries_tmp.replace(run_dir / "boundary_posteriors.jsonl")
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
            writer.writerow((rule.rule_id, rule_usage.get(rule.rule_id, 0.0)))

    complexity = store.complexity_summary(
        weight=config.complexity_weight,
        tau=config.complexity_tau,
        low_count_threshold=config.low_count_threshold,
    )
    denominator = max(1, metrics.segments)
    summary: dict[str, Any] = {
        **metrics.summary(config.passes),
        "mean_top1_posterior": top1_sum / denominator,
        "mean_entropy": entropy_sum / denominator,
        "rule_expected_usage_total": sum(rule_usage.values()),
        "identity_mass_total": metrics.identity_mass_sum,
        "latent_mass_total": metrics.latent_mass_sum,
        "complexity": complexity,
        "usage_count_semantics": (
            "Distinct surface/context counts include associations whose "
            "posterior mass reaches usage_posterior_threshold; contexts use "
            "the bounded reported top-k analyses."
        ),
    }
    _write_json(run_dir / "summary.json", summary)
    report = _human_report(
        store=store,
        summary=summary,
        rule_usage=rule_usage,
        high_confidence=_sorted_report(high_confidence),
        ambiguous=_sorted_report(ambiguous),
        shifts=_sorted_report(shifts),
        config=config,
    )
    (run_dir / "inspection_report.md").write_text(
        report,
        encoding="utf-8",
        newline="",
    )
    return summary


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
            "config_signature": signature,
            "seed": config.seed,
            "determinism": (
                "sorted manifest order, file order, rule IDs, graph nodes, and "
                "tie-break keys; no stochastic update"
            ),
        }
        _write_json(run_dir / "config.json", config.payload())
        _write_json(run_dir / "provenance.json", provenance)
        checkpoint = _load_checkpoint(run_dir)
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
            )
        _write_json(run_dir / "iteration_metrics.json", checkpoint["history"])
        summary = _inspection_pass(
            documents=documents,
            grammar=grammar,
            store=store,
            config=config,
            run_dir=run_dir,
        )
        checkpoint["inspection_complete"] = True
        _save_checkpoint(run_dir, checkpoint)
        return TrainingResult(
            run_dir=run_dir,
            history=tuple(checkpoint["history"]),
            summary=summary,
        )
    finally:
        store.close()
