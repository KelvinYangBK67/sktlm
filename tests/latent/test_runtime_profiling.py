from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from sktlm.latent.candidates import CandidateConfig, candidate_graph_fingerprint
from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.inference import NeutralFormScorer
from sktlm.latent.profiling import (
    M1ProfileConfig,
    M1RuntimeProfile,
    evaluate_m1_segment,
    profile_m1_runtime,
)
from sktlm.latent.training import EXPECTED_FREEZE_ID


def test_profiling_on_and_off_have_identical_inference_fingerprints() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("devo'pi api ca"))
    candidate_config = CandidateConfig()

    plain = evaluate_m1_segment(
        segment,
        grammar,
        NeutralFormScorer(),
        candidate_config=candidate_config,
    )
    profile = M1RuntimeProfile()
    observed = evaluate_m1_segment(
        segment,
        grammar,
        NeutralFormScorer(),
        candidate_config=candidate_config,
        profile=profile,
    )

    assert observed.result_fingerprint == plain.result_fingerprint
    assert candidate_graph_fingerprint(observed.graph) == candidate_graph_fingerprint(
        plain.graph
    )
    assert observed.inference == plain.inference
    assert profile.segments == 1
    assert profile.candidate_factors == len(observed.graph.factors)
    assert profile.lattice_nodes > 0
    assert profile.lexical_edges > 0
    assert profile.candidate_build_seconds >= 0.0
    assert profile.inference_seconds >= profile.lexical_scoring_seconds


def _make_profile_run(tmp_path: Path) -> Path:
    observed = tmp_path / "observed.txt"
    observed.write_text("devo'pi api ca\n", encoding="utf-8")
    manifest = tmp_path / "representations.csv"
    manifest.write_text(
        "script,condition,freeze_id,relative_path,representation_path\n"
        f"iast,surface_word,{EXPECTED_FREEZE_ID},toy.txt,{observed.as_posix()}\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "manifest": manifest.as_posix(),
                "script": "iast",
                "condition": "surface_word",
                "max_internal_matches": 512,
                "allow_whitespace_merge": True,
                "whitespace_merge_penalty": 8.0,
                "max_segment_tokens": 128,
                "lexical_alpha": 0.1,
                "complexity_weight": 0.5,
                "complexity_tau": 1.0,
                "lexicon_cache_size": 1000,
            }
        ),
        encoding="utf-8",
    )
    connection = sqlite3.connect(run_dir / "learner.sqlite")
    connection.execute(
        "CREATE TABLE lexicon ("
        "form_key TEXT PRIMARY KEY, expected_count REAL NOT NULL, "
        "probability REAL NOT NULL) WITHOUT ROWID"
    )
    connection.execute(
        "INSERT INTO lexicon VALUES ('V_A', 1.0, 1.0)"
    )
    connection.commit()
    connection.close()
    return run_dir


def test_bounded_read_only_profile_emits_required_counts_and_timings(
    tmp_path: Path,
) -> None:
    payload = profile_m1_runtime(
        M1ProfileConfig(
            run_dir=_make_profile_run(tmp_path),
            repo_root=tmp_path,
            max_documents=1,
            max_lines_per_document=1,
            max_segments=1,
            expected_script="iast",
            expected_condition="surface_word",
        )
    )

    assert payload["documents"] == 1
    assert payload["lines"] == 1
    assert payload["segments"] == 1
    assert payload["characters"] > 0
    assert payload["phonemes"] > 0
    assert payload["candidate_factors"] > 0
    assert payload["lattice_nodes"] > 0
    assert payload["lexical_edges"] > 0
    assert payload["unique_lexical_forms"] > 0
    assert payload["score_calls"] > 0
    assert payload["cache_hits"] + payload["cache_misses"] == payload["score_calls"]
    assert payload["sqlite_selects"] == payload["cache_misses"]
    assert payload["candidate_build_seconds"] >= 0.0
    assert payload["inference_seconds"] >= payload["lexical_scoring_seconds"]
    assert payload["lexical_scoring_seconds"] >= payload["sqlite_seconds"]
    assert payload["edges_per_segment"] == pytest.approx(payload["lexical_edges"])
    assert len(payload["result_fingerprint"]) == 64
    assert payload["timing_nesting"] == {
        "inference_seconds_includes_lexical_scoring": True,
        "lexical_scoring_seconds_includes_sqlite_selects": True,
    }
