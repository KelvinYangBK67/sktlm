"""Bounded read-only M1 runtime diagnosis for post-freeze manual runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sktlm.latent.candidates import (
    CandidateConfig,
    CandidateGraph,
    build_candidate_graph,
    candidate_graph_statistics,
)
from sktlm.latent.frontend import ObservedSegment, iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.inference import (
    FormScorer,
    TrainingSegmentInference,
    infer_training_segment,
)
from sktlm.latent.phonology import PhonologicalForm
from sktlm.latent.store import LexiconScorer
from sktlm.latent.telemetry import RuntimeTelemetry
from sktlm.latent.training import load_documents


PROFILE_IMPLEMENTATION = "m1-bounded-runtime-profile-v1"


@dataclass(frozen=True, slots=True)
class M1ProfileConfig:
    run_dir: Path
    repo_root: Path = Path(".")
    document_list: Path | None = None
    max_documents: int = 1
    max_lines_per_document: int = 5
    max_segments: int = 32
    expected_script: str | None = None
    expected_condition: str | None = None

    def __post_init__(self) -> None:
        if self.max_documents < 1:
            raise ValueError("max_documents must be >= 1")
        if self.max_lines_per_document < 1:
            raise ValueError("max_lines_per_document must be >= 1")
        if self.max_segments < 1:
            raise ValueError("max_segments must be >= 1")


@dataclass(slots=True)
class M1RuntimeProfile:
    documents: int = 0
    lines: int = 0
    segments: int = 0
    characters: int = 0
    phonemes: int = 0
    candidate_factors: int = 0
    raw_internal_matches: int = 0
    retained_internal_matches: int = 0
    lattice_nodes: int = 0
    lexical_edges: int = 0
    overflowed_tokens: int = 0
    candidate_build_seconds: float = 0.0
    inference_seconds: float = 0.0
    lexical_scoring_seconds: float = 0.0
    unique_forms: set[PhonologicalForm] = field(default_factory=set)
    _fingerprint: Any = field(default_factory=hashlib.sha256)

    def observe(
        self,
        segment: ObservedSegment,
        graph: CandidateGraph,
        inference: TrainingSegmentInference,
    ) -> None:
        statistics = candidate_graph_statistics(graph)
        self.segments += 1
        self.characters += len(segment.written)
        self.phonemes += sum(len(token.phonemes) for token in segment.tokens)
        self.candidate_factors += statistics["factors"]
        self.raw_internal_matches += statistics["raw_internal_matches"]
        self.retained_internal_matches += statistics["retained_internal_matches"]
        self.lattice_nodes += statistics["lattice_nodes"]
        self.lexical_edges += statistics["lexical_edges"]
        self.overflowed_tokens += statistics["overflowed_tokens"]
        for factor in graph.factors:
            if factor.merged_word is not None:
                self.unique_forms.add(factor.merged_word)
            elif factor.lattice is not None:
                self.unique_forms.update(edge.word for edge in factor.lattice.edges)
        self._fingerprint.update(
            bytes.fromhex(m1_inference_fingerprint(graph, inference))
        )

    @property
    def result_fingerprint(self) -> str:
        return self._fingerprint.hexdigest()


@dataclass(frozen=True, slots=True)
class M1SegmentEvaluation:
    graph: CandidateGraph
    inference: TrainingSegmentInference
    result_fingerprint: str


@dataclass(slots=True)
class _TimedFormScorer:
    scorer: FormScorer
    profile: M1RuntimeProfile

    def score(self, form: PhonologicalForm) -> float:
        started = time.perf_counter()
        value = self.scorer.score(form)
        self.profile.lexical_scoring_seconds += time.perf_counter() - started
        return value


def m1_inference_fingerprint(
    graph: CandidateGraph,
    inference: TrainingSegmentInference,
) -> str:
    """Hash the graph plus every training-inference result deterministically."""

    digest = hashlib.sha256()

    def add(value: str) -> None:
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")

    statistics = candidate_graph_statistics(graph)
    add(str(statistics["factors"]))
    add(str(statistics["lattice_nodes"]))
    add(str(statistics["lexical_edges"]))
    add(inference.log_partition.hex())
    add(inference.identity_mass.hex())
    add(inference.latent_mass.hex())
    add(inference.expected_lexical_tokens.hex())
    for form, mass in sorted(
        inference.expected_counts.items(),
        key=lambda item: item[0].key,
    ):
        add(form.key)
        add(mass.hex())
    return digest.hexdigest()


def evaluate_m1_segment(
    segment: ObservedSegment,
    grammar: StructuredSandhiGrammar,
    scorer: FormScorer,
    *,
    candidate_config: CandidateConfig,
    profile: M1RuntimeProfile | None = None,
) -> M1SegmentEvaluation:
    """Run unchanged M1 inference, optionally observing engineering counters."""

    if profile is None:
        graph = build_candidate_graph(segment, grammar, candidate_config)
        inference = infer_training_segment(
            graph,
            scorer,
            whitespace_merge_penalty=candidate_config.whitespace_merge_penalty,
        )
    else:
        started = time.perf_counter()
        graph = build_candidate_graph(segment, grammar, candidate_config)
        profile.candidate_build_seconds += time.perf_counter() - started
        started = time.perf_counter()
        inference = infer_training_segment(
            graph,
            _TimedFormScorer(scorer, profile),
            whitespace_merge_penalty=candidate_config.whitespace_merge_penalty,
        )
        profile.inference_seconds += time.perf_counter() - started
        profile.observe(segment, graph, inference)
    return M1SegmentEvaluation(
        graph=graph,
        inference=inference,
        result_fingerprint=m1_inference_fingerprint(graph, inference),
    )


def _resolved(path: Path, root: Path) -> Path:
    return path if path.is_absolute() else root / path


def _ratio(numerator: float | int, denominator: float | int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def profile_m1_runtime(config: M1ProfileConfig) -> dict[str, Any]:
    """Profile one explicitly bounded subset against an existing M1 lexicon."""

    wall_started = time.perf_counter()
    repo_root = config.repo_root.resolve()
    run_dir = _resolved(config.run_dir, repo_root).resolve()
    run_config_path = run_dir / "config.json"
    database_path = run_dir / "learner.sqlite"
    if not run_config_path.is_file():
        raise FileNotFoundError(run_config_path)
    if not database_path.is_file():
        raise FileNotFoundError(database_path)
    run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    if "vocab_budget" in run_config:
        raise ValueError("The P0 M1 profiler accepts unrestricted runs only.")
    script = str(run_config["script"])
    condition = str(run_config["condition"])
    if config.expected_script is not None and script != config.expected_script:
        raise ValueError(
            f"Run script is {script!r}, not expected {config.expected_script!r}."
        )
    if config.expected_condition is not None and condition != config.expected_condition:
        raise ValueError(
            f"Run condition is {condition!r}, not expected "
            f"{config.expected_condition!r}."
        )

    manifest = _resolved(Path(run_config["manifest"]), repo_root)
    document_list = (
        None
        if config.document_list is None
        else _resolved(config.document_list, repo_root)
    )
    documents = load_documents(
        manifest,
        repo_root=repo_root,
        max_documents=config.max_documents,
        document_list=document_list,
        script=script,
        condition=condition,
    )
    candidate_config = CandidateConfig(
        max_internal_matches=int(run_config["max_internal_matches"]),
        allow_whitespace_merge=bool(run_config["allow_whitespace_merge"]),
        whitespace_merge_penalty=float(run_config["whitespace_merge_penalty"]),
    )
    grammar = StructuredSandhiGrammar.from_default_inventory()
    telemetry = RuntimeTelemetry()
    connection = sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    scorer = LexiconScorer(
        connection,
        alpha=float(run_config["lexical_alpha"]),
        complexity_weight=float(run_config["complexity_weight"]),
        complexity_tau=float(run_config["complexity_tau"]),
        cache_size=int(run_config["lexicon_cache_size"]),
        telemetry=telemetry,
    )
    profile = M1RuntimeProfile()
    stop = False
    try:
        for document in documents:
            document_used = False
            line_count = 0
            with document.path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if line_number > config.max_lines_per_document:
                        break
                    if not line.strip():
                        continue
                    line_used = False
                    for segment in iter_observed_segments(
                        line.rstrip("\r\n"),
                        max_tokens=int(run_config["max_segment_tokens"]),
                        script=script,
                    ):
                        evaluate_m1_segment(
                            segment,
                            grammar,
                            scorer,
                            candidate_config=candidate_config,
                            profile=profile,
                        )
                        document_used = True
                        line_used = True
                        if profile.segments >= config.max_segments:
                            stop = True
                            break
                    if line_used:
                        line_count += 1
                    if stop:
                        break
            if document_used:
                profile.documents += 1
                profile.lines += line_count
            if stop:
                break
    finally:
        connection.close()

    if profile.segments == 0:
        raise ValueError("The bounded profile subset contained no observed segments.")
    total_wall_seconds = time.perf_counter() - wall_started
    sqlite_seconds = scorer.sqlite_seconds
    unique_count = len(profile.unique_forms)
    return {
        "schema_version": 1,
        "implementation": PROFILE_IMPLEMENTATION,
        "script": script,
        "condition": condition,
        "subset": {
            "document_list": (
                None if document_list is None else document_list.as_posix()
            ),
            "max_documents": config.max_documents,
            "max_lines_per_document": config.max_lines_per_document,
            "max_segments": config.max_segments,
        },
        "documents": profile.documents,
        "lines": profile.lines,
        "segments": profile.segments,
        "characters": profile.characters,
        "phonemes": profile.phonemes,
        "candidate_factors": profile.candidate_factors,
        "raw_internal_matches": profile.raw_internal_matches,
        "retained_internal_matches": profile.retained_internal_matches,
        "lattice_nodes": profile.lattice_nodes,
        "lexical_edges": profile.lexical_edges,
        "overflowed_tokens": profile.overflowed_tokens,
        "unique_lexical_forms": unique_count,
        "candidate_build_seconds": profile.candidate_build_seconds,
        "inference_seconds": profile.inference_seconds,
        "lexical_scoring_seconds": profile.lexical_scoring_seconds,
        "sqlite_seconds": sqlite_seconds,
        "inference_non_scoring_seconds": max(
            0.0,
            profile.inference_seconds - profile.lexical_scoring_seconds,
        ),
        "lexical_scoring_non_sqlite_seconds": max(
            0.0,
            profile.lexical_scoring_seconds - sqlite_seconds,
        ),
        "total_wall_seconds": total_wall_seconds,
        "score_calls": scorer.score_calls,
        "cache_hits": scorer.cache_hits,
        "cache_misses": scorer.cache_misses,
        "sqlite_selects": scorer.sqlite_selects,
        "edges_per_segment": _ratio(profile.lexical_edges, profile.segments),
        "edges_per_phoneme": _ratio(profile.lexical_edges, profile.phonemes),
        "unique_forms_per_lexical_edge": _ratio(
            unique_count,
            profile.lexical_edges,
        ),
        "seconds_per_lexical_edge": _ratio(
            profile.inference_seconds,
            profile.lexical_edges,
        ),
        "result_fingerprint": profile.result_fingerprint,
        "timing_nesting": {
            "inference_seconds_includes_lexical_scoring": True,
            "lexical_scoring_seconds_includes_sqlite_selects": True,
        },
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Profile unchanged M1 inference on one short, bounded subset."
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--document-list", type=Path)
    parser.add_argument("--max-documents", type=int, default=1)
    parser.add_argument("--max-lines-per-document", type=int, default=5)
    parser.add_argument("--max-segments", type=int, default=32)
    parser.add_argument("--expected-script", choices=("iast", "devanagari"))
    parser.add_argument(
        "--expected-condition",
        choices=("surface_word", "legacy_joined", "continuous"),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    payload = profile_m1_runtime(
        M1ProfileConfig(
            run_dir=args.run_dir,
            repo_root=args.repo_root,
            document_list=args.document_list,
            max_documents=args.max_documents,
            max_lines_per_document=args.max_lines_per_document,
            max_segments=args.max_segments,
            expected_script=args.expected_script,
            expected_condition=args.expected_condition,
        )
    )
    output = _resolved(args.output, args.repo_root.resolve())
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite profile output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    print(f"profile: {output}")
    print(f"segments: {payload['segments']}")
    print(f"result fingerprint: {payload['result_fingerprint']}")


if __name__ == "__main__":
    main()
