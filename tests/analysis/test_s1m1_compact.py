from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

import sktlm.analysis.s1m1_compact as compact
from sktlm.analysis.s1m1_compact import export_compact_cell


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    run = tmp_path / "run"
    metrics = tmp_path / "metrics"
    run.mkdir()
    metrics.mkdir()
    _json(run / "config.json", {"passes": 3, "script": "iast", "condition": "surface_word"})
    _json(run / "checkpoint.json", {"completed_passes": 3, "inspection_complete": True})
    _json(run / "provenance.json", {"script": "iast", "condition": "surface_word", "git_commit": "a" * 40, "config_signature": "fixture"})
    _json(run / "summary.json", {"segments": 2, "complexity": {"active_lexical_types": 2}})
    _json(run / "iteration_metrics.json", [{"pass": 1, "segments": 2}, {"pass": 2, "segments": 2}, {"pass": 3, "segments": 2}])
    _json(run / "timing_metrics.json", {"timings_seconds": {"training": 1.0}, "counters": {"rows": 2}})
    _json(metrics / "process_tree_summary.json", {"return_code": 0, "wall_seconds": 2.0})
    (run / "rule_usage.tsv").write_text("rule_id\texpected_usage\nR1\t1\n", encoding="utf-8")
    (run / "latent_lexicon.tsv").write_text(
        "form_key\tlatent_form\tphoneme_ids\texpected_count\tprobability\tnumber_of_surface_variants\tnumber_of_contexts\n"
        "A\ta\tV_A\t2\t0.6\t2\t3\nB\tba\tC_B V_A\t1\t0.4\t1\t1\n",
        encoding="utf-8",
    )
    rows = [
        {"segment_id": "s1", "document": "d1", "surface": "a", "source_start": 0, "source_end": 1, "identity_mass": 0.6, "latent_mass": 0.4, "entropy": 0.5, "residual_posterior": 0.0, "log_partition": -1.0, "candidate_counts": {"factors": 1, "lattice_nodes": 2, "lexical_edges": 2, "overflowed_tokens": 0}, "top_analyses": [{"posterior": 0.6, "latent_units": [{"form_key": "A"}], "rule_ids": []}]},
        {"segment_id": "s2", "document": "d2", "surface": "ba", "source_start": 0, "source_end": 2, "identity_mass": 0.2, "latent_mass": 0.8, "entropy": 0.7, "residual_posterior": 0.1, "log_partition": -2.0, "candidate_counts": {"factors": 2, "lattice_nodes": 3, "lexical_edges": 4, "overflowed_tokens": 0}, "top_analyses": [{"posterior": 0.7, "latent_units": [{"form_key": "B"}], "rule_ids": ["R1"]}]},
    ]
    (run / "analyses.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    boundaries = [
        {"segment_id": "s1", "boundaries": []},
        {"segment_id": "s2", "boundaries": [{"boundary_id": "b1", "cue_kind": "space", "source_start": 1, "source_end": 2, "probability": 0.8}]},
    ]
    (run / "boundary_posteriors.jsonl").write_text("".join(json.dumps(row) + "\n" for row in boundaries), encoding="utf-8")
    database = tmp_path / "learner.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(
        "CREATE TABLE lexicon(form_key TEXT PRIMARY KEY, expected_count REAL NOT NULL, probability REAL NOT NULL) WITHOUT ROWID;"
        "CREATE TABLE surface_usage(form_key TEXT NOT NULL, surface TEXT NOT NULL, expected_mass REAL NOT NULL, PRIMARY KEY(form_key,surface));"
        "CREATE TABLE context_usage(form_key TEXT NOT NULL, context TEXT NOT NULL, expected_mass REAL NOT NULL, PRIMARY KEY(form_key,context));"
        "INSERT INTO lexicon VALUES ('A',2,0.6),('B',1,0.4);"
        "INSERT INTO surface_usage VALUES ('A','a',2),('B','ba',1);"
        "INSERT INTO context_usage VALUES ('A','left',2),('B','right',1);"
    )
    connection.commit()
    connection.close()
    return run, metrics, database


def test_compact_export_is_complete_consistent_and_read_only(tmp_path: Path) -> None:
    run, metrics, database = _fixture(tmp_path)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    output = tmp_path / "compact"
    export_compact_cell(
        cell_id="iast__surface_word", script="iast", representation="surface_word",
        run_dir=run, metrics_dir=metrics, database_path=database, output_dir=output,
    )
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert all(manifest["consistency"].values())
    assert manifest["statistics"]["database"]["final_scorer"]["database_probability_sum"] == 1.0
    with gzip.open(output / "segment_metrics.tsv.gz", "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert [row["segment_id"] for row in rows] == ["s1", "s2"]
    assert rows[0]["expected_lexical_tokens"] == "N/A"
    assert (output / "SHA256SUMS").is_file()


def test_compact_export_interruption_never_publishes_final_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, metrics, database = _fixture(tmp_path)
    output = tmp_path / "compact"
    monkeypatch.setattr(
        compact.os, "replace",
        lambda source, target: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    with pytest.raises(KeyboardInterrupt):
        export_compact_cell(
            cell_id="iast__surface_word", script="iast",
            representation="surface_word", run_dir=run, metrics_dir=metrics,
            database_path=database, output_dir=output,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".compact.*"))
