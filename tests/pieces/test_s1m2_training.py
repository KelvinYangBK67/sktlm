from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import sktlm.latent.training as latent_training
from sktlm.latent.store import LexiconStore
from sktlm.latent.phonology import PhonologicalForm, parse_iast_form
from sktlm.latent.training import (
    EXPECTED_FREEZE_ID,
    S1M2_MODEL,
    TrainingConfig,
    run_training,
)
from sktlm.pieces.scorer import (
    BaseMeasurePieceScorer,
    GeometricPhonemeBaseMeasure,
)


def _write_fixture(tmp_path: Path) -> Path:
    manifest = tmp_path / "representations.csv"
    rows = []
    for index, text in enumerate(
        (
            "devo'pi devaḥ ca api dakani batani ramani\n",
            "rāmo'pi rāmaḥ ca api dakatu batatu ramatu\n",
        )
    ):
        corpus = tmp_path / f"surface-{index}.txt"
        corpus.write_text(text, encoding="utf-8")
        rows.append(
            {
                "freeze_id": EXPECTED_FREEZE_ID,
                "relative_path": f"tiny-{index}.txt",
                "script": "iast",
                "condition": "surface_word",
                "representation_path": str(corpus),
            }
        )
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "freeze_id",
                "relative_path",
                "script",
                "condition",
                "representation_path",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)
    return manifest


def _config(tmp_path: Path, manifest: Path, run_id: str, **changes: object) -> TrainingConfig:
    values = {
        "manifest": manifest,
        "output_root": tmp_path / "artifacts",
        "run_id": run_id,
        "model": S1M2_MODEL,
        "passes": 2,
        "analysis_top_k": 4,
        "flush_types": 8,
        "piece_max_length": 3,
    }
    values.update(changes)
    return TrainingConfig(**values)


def test_s1m2_configuration_identity_includes_piece_model_and_cache_bounds(
    tmp_path: Path,
) -> None:
    payload = _config(
        tmp_path,
        tmp_path / "manifest.csv",
        "config-contract",
    ).payload()
    assert payload["model"] == S1M2_MODEL
    assert payload["piece_max_length"] == 3
    assert payload["piece_min_reuse_occurrences"] == 2
    assert payload["piece_score_cache_entries"] == 65_536
    assert payload["piece_form_cache_bytes"] == 256 * 1024 * 1024
    assert payload["piece_shared_token_marginals"] is True
    assert payload["piece_shared_prefix_nodes"] == 262_144
    assert payload["piece_shared_top_k_piece_references"] == 4_194_304


def test_s1m2_streaming_training_writes_piece_and_lexical_artifacts(
    tmp_path: Path,
) -> None:
    manifest = _write_fixture(tmp_path)

    result = run_training(
        _config(tmp_path, manifest, "s1m2-tiny"),
        repo_root=Path("."),
    )

    expected = {
        "analyses.jsonl",
        "boundary_posteriors.jsonl",
        "checkpoint.json",
        "config.json",
        "inspection_report.md",
        "iteration_metrics.json",
        "learner.sqlite",
        "lexical_diagnostics.tsv",
        "piece_inventory.tsv",
        "provenance.json",
        "rule_usage.tsv",
        "summary.json",
        "timing_metrics.json",
        "topology",
    }
    assert expected <= {path.name for path in result.run_dir.iterdir()}
    assert len(result.history) == 2
    assert all(item["active_piece_types"] > 0 for item in result.history)
    assert result.runtime["piece_scorers"]
    assert result.runtime["piece_scorers"][0]["score_calls"] > 0
    assert result.runtime["counters"]["training_composed_state_count"] > 0
    assert result.runtime["counters"]["training_composed_transition_count"] > 0
    assert result.runtime["counters"]["training_piece_score_calls"] > 0
    assert result.runtime["counters"]["training_shared_prefix_nodes"] > 0
    assert result.runtime["counters"]["training_shared_form_endpoints"] > 0
    assert result.runtime["counters"].get("training_shared_batch_fallbacks", 0) == 0
    assert result.runtime["counters"]["training_form_cache_hits"] > 0
    assert result.runtime["counters"]["training_store_lookups"] > 0
    assert result.runtime["counters"]["training_topology_compiles"] > 0
    assert result.runtime["counters"]["training_topology_reuses"] > 0
    assert result.runtime["counters"]["inspection_topology_reuses"] > 0
    assert result.runtime["counters"]["topology_archives_compiled"] == 2
    assert result.runtime["counters"]["topology_archives_reused"] == 4
    assert len(tuple((result.run_dir / "topology").glob("*.bin"))) == 2
    assert (
        result.runtime["gauges"]["training_piece_score_cache_entries"]
        <= 65_536
    )
    assert (
        result.runtime["gauges"]["training_piece_score_cache_estimated_bytes"]
        <= 32 * 1024 * 1024
    )
    assert result.runtime["gauges"]["training_form_cache_entries"] <= 8_192
    assert (
        result.runtime["gauges"]["training_form_cache_estimated_bytes"]
        <= 256 * 1024 * 1024
    )
    histograms = result.runtime["histograms"]
    assert histograms["training_segment_phonemes"]["count"] > 0
    assert histograms["training_token_phonemes"]["max"] > 0
    assert histograms["training_raw_internal_matches_per_segment"]["count"] > 0
    assert result.runtime["timings_seconds"]["training_grammar_match_seconds"] >= 0.0
    assert result.runtime["timings_seconds"]["training_window_filter_seconds"] >= 0.0
    assert result.runtime["timings_seconds"]["training_piece_composition_seconds"] > 0.0
    assert (
        result.runtime["timings_seconds"]["training_inner_piece_transition_build_seconds"]
        > 0.0
    )
    assert (
        result.runtime["timings_seconds"]["training_inner_piece_reweight_seconds"]
        > 0.0
    )
    assert result.runtime["timings_seconds"]["training_outer_forward_seconds"] > 0.0
    assert result.runtime["timings_seconds"]["inspection_outer_top_k_seconds"] > 0.0
    assert result.runtime["gauges"]["sqlite_database_bytes"] > 0
    assert result.runtime["gauges"]["sqlite_total_bytes"] > 0
    assert result.runtime["gauges"]["artifact_bytes_before_timing_metrics"] > 0
    assert result.runtime["gauges"]["sqlite_completed_state_bytes_saved"] > 0

    storage = json.loads(
        (result.run_dir / "storage_manifest.json").read_text("utf-8")
    )
    assert storage["status"] == "COMPACT"
    assert storage["retained_tables"] == ["metadata", "piece_lexicon"]
    assert set(storage["dropped_tables"]) == {
        "context_usage",
        "inspection_counts",
        "inspection_piece_counts",
        "surface_usage",
    }
    assert result.runtime["counters"]["sqlite_pass_diagnostic_tables_retired"] == 4
    assert storage["after_bytes"]["total"] < storage["before_bytes"]["total"]
    assert "same transaction" in storage["transient_lifecycle"][
        "training_pass_diagnostics"
    ]
    assert "retired immediately" in storage["transient_lifecycle"][
        "inspection_worker_shards"
    ]
    assert storage["compiled_topology"]["mutable_scores_or_posteriors_stored"] is False
    assert "one segment at a time" in storage["transient_lifecycle"][
        "compiled_topology"
    ]

    summary = json.loads((result.run_dir / "summary.json").read_text("utf-8"))
    assert summary["complexity"]["active_piece_types"] > 0
    assert summary["complexity"]["piece_types"] > 0
    assert summary["lexical_diagnostics"]["active_lexical_types"] > 0
    assert summary["piece_posterior"]["whole_form_memorization_mass"] > 0.0
    assert summary["piece_posterior"]["singleton_atomization_mass"] > 0.0
    assert summary["piece_posterior"]["multi_piece_compositional_mass"] > 0.0

    analysis = json.loads(
        (result.run_dir / "analyses.jsonl").read_text("utf-8").splitlines()[0]
    )
    assert analysis["top_analyses"]
    assert analysis["top_analyses"][0]["piece_segmentations"]

    store = LexiconStore(result.run_dir / "learner.sqlite")
    try:
        active = {
            PhonologicalForm.from_key(str(key)): float(count)
            for key, count in store.connection.execute(
                "SELECT form_key, expected_count FROM piece_lexicon"
            )
        }
        scorer = store.piece_scorer(
            alpha=0.1,
            complexity_weight=0.5,
            complexity_kappa=1.0,
            complexity_beta=0.25,
            complexity_tau=1.0,
            base_stop_probability=0.5,
            cache_size=8,
        )
        reference = BaseMeasurePieceScorer(
            active,
            alpha=0.1,
            lambda_=0.5,
            kappa=1.0,
            beta=0.25,
            tau=1.0,
            base_measure=GeometricPhonemeBaseMeasure(0.5),
        )
        for piece in (next(iter(active)), parse_iast_form("ghū")):
            assert scorer.score(piece) == pytest.approx(reference.score(piece))
    finally:
        store.close()


_SCIENTIFIC_OUTPUTS = (
    "iteration_metrics.json",
    "piece_inventory.tsv",
    "lexical_diagnostics.tsv",
    "analyses.jsonl",
    "boundary_posteriors.jsonl",
    "rule_usage.tsv",
    "summary.json",
)


def _assert_same_science(reference: Path, candidate: Path) -> None:
    for name in _SCIENTIFIC_OUTPUTS:
        assert (candidate / name).read_bytes() == (reference / name).read_bytes()


def test_s1m2_interrupted_document_resume_matches_uninterrupted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_fixture(tmp_path)
    reference = run_training(
        _config(tmp_path, manifest, "reference"),
        repo_root=Path("."),
    ).run_dir
    original_commit = LexiconStore.commit_document
    crashed = False

    def crash_after_commit(
        self: LexiconStore,
        checkpoint: dict[str, object],
    ) -> None:
        nonlocal crashed
        original_commit(self, checkpoint)
        if (
            not crashed
            and checkpoint.get("active_pass") == 1
            and checkpoint.get("next_document_index") == 1
        ):
            crashed = True
            raise RuntimeError("simulated interruption after durable document")

    monkeypatch.setattr(LexiconStore, "commit_document", crash_after_commit)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_training(
            _config(tmp_path, manifest, "resumed"),
            repo_root=Path("."),
        )
    monkeypatch.setattr(LexiconStore, "commit_document", original_commit)

    resumed = run_training(
        _config(tmp_path, manifest, "resumed", resume=True),
        repo_root=Path("."),
    ).run_dir
    _assert_same_science(reference, resumed)


def test_s1m2_resume_after_durable_pass_diagnostics_retired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_fixture(tmp_path)
    reference = run_training(
        _config(tmp_path, manifest, "pass-retirement-reference"),
        repo_root=Path("."),
    ).run_dir
    original_inspection = latent_training._inspection_pass

    def crash_before_inspection(**_: object) -> dict[str, object]:
        raise RuntimeError("simulated interruption before inspection")

    monkeypatch.setattr(latent_training, "_inspection_pass", crash_before_inspection)
    with pytest.raises(RuntimeError, match="before inspection"):
        run_training(
            _config(tmp_path, manifest, "pass-retirement-crashed"),
            repo_root=Path("."),
        )
    crashed = tmp_path / "artifacts" / "pass-retirement-crashed"
    assert len(tuple((crashed / "topology").glob("*.bin"))) == 2
    store = LexiconStore(crashed / "learner.sqlite")
    try:
        assert store.has_table("piece_lexicon")
        assert not store.has_table("piece_inventory")
        assert not store.has_table("lexical_diagnostics")
        assert store.load_training_checkpoint()["completed_passes"] == 2
    finally:
        store.close()

    monkeypatch.setattr(latent_training, "_inspection_pass", original_inspection)
    resumed = run_training(
        _config(
            tmp_path,
            manifest,
            "pass-retirement-crashed",
            resume=True,
        ),
        repo_root=Path("."),
    ).run_dir
    _assert_same_science(reference, resumed)


def test_s1m2_resume_regenerates_missing_topology_before_later_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_fixture(tmp_path)
    reference = run_training(
        _config(tmp_path, manifest, "missing-topology-reference"),
        repo_root=Path("."),
    ).run_dir
    original_training_pass = latent_training._training_pass
    interrupted = False

    def stop_after_pass_one(**kwargs: object) -> dict[str, object]:
        nonlocal interrupted
        result = original_training_pass(**kwargs)  # type: ignore[arg-type]
        if not interrupted and kwargs["pass_index"] == 1:
            interrupted = True
            raise RuntimeError("simulated interruption after pass one")
        return result

    monkeypatch.setattr(latent_training, "_training_pass", stop_after_pass_one)
    with pytest.raises(RuntimeError, match="after pass one"):
        run_training(
            _config(tmp_path, manifest, "missing-topology-resumed"),
            repo_root=Path("."),
        )
    run_dir = tmp_path / "artifacts" / "missing-topology-resumed"
    (run_dir / "topology" / "document_00000000.bin").unlink()

    monkeypatch.setattr(latent_training, "_training_pass", original_training_pass)
    result = run_training(
        _config(
            tmp_path,
            manifest,
            "missing-topology-resumed",
            resume=True,
        ),
        repo_root=Path("."),
    )
    _assert_same_science(reference, result.run_dir)
    assert result.runtime["counters"]["topology_archive_cache_misses"] == 1
    assert result.runtime["counters"]["topology_archives_regenerated"] == 1


def test_s1m2_resume_regenerates_corrupt_topology_before_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_fixture(tmp_path)
    reference = run_training(
        _config(tmp_path, manifest, "corrupt-topology-reference"),
        repo_root=Path("."),
    ).run_dir
    original_inspection = latent_training._inspection_pass

    def crash_before_inspection(**_: object) -> dict[str, object]:
        raise RuntimeError("simulated interruption before corrupt inspection")

    monkeypatch.setattr(latent_training, "_inspection_pass", crash_before_inspection)
    with pytest.raises(RuntimeError, match="before corrupt inspection"):
        run_training(
            _config(tmp_path, manifest, "corrupt-topology-resumed"),
            repo_root=Path("."),
        )
    run_dir = tmp_path / "artifacts" / "corrupt-topology-resumed"
    archive = run_dir / "topology" / "document_00000000.bin"
    archive.write_bytes(archive.read_bytes()[:-7])

    monkeypatch.setattr(latent_training, "_inspection_pass", original_inspection)
    result = run_training(
        _config(
            tmp_path,
            manifest,
            "corrupt-topology-resumed",
            resume=True,
        ),
        repo_root=Path("."),
    )
    _assert_same_science(reference, result.run_dir)
    assert result.runtime["counters"]["topology_archive_cache_invalid"] == 1
    assert result.runtime["counters"]["topology_archives_regenerated"] == 1


def test_s1m2_resume_regenerates_retired_inspection_shard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_fixture(tmp_path)
    reference = run_training(
        _config(
            tmp_path,
            manifest,
            "shard-retirement-reference",
            workers=2,
        ),
        repo_root=Path("."),
    ).run_dir
    original_retire = latent_training._retire_inspection_shard
    crashed = False

    def crash_after_retirement(
        run_dir: Path,
        document_index: int,
        telemetry: object,
    ) -> None:
        nonlocal crashed
        original_retire(run_dir, document_index, telemetry)  # type: ignore[arg-type]
        if not crashed:
            crashed = True
            raise RuntimeError("simulated interruption after shard retirement")

    monkeypatch.setattr(
        latent_training,
        "_retire_inspection_shard",
        crash_after_retirement,
    )
    with pytest.raises(RuntimeError, match="after shard retirement"):
        run_training(
            _config(
                tmp_path,
                manifest,
                "shard-retirement-crashed",
                workers=2,
            ),
            repo_root=Path("."),
        )
    run_dir = tmp_path / "artifacts" / "shard-retirement-crashed"
    assert not latent_training._inspection_shard_paths(run_dir, 0)["marker"].exists()

    monkeypatch.setattr(
        latent_training,
        "_retire_inspection_shard",
        original_retire,
    )
    resumed = run_training(
        _config(
            tmp_path,
            manifest,
            "shard-retirement-crashed",
            workers=2,
            resume=True,
        ),
        repo_root=Path("."),
    ).run_dir
    _assert_same_science(reference, resumed)


def test_s1m2_parallel_and_serial_scientific_outputs_match(tmp_path: Path) -> None:
    manifest = _write_fixture(tmp_path)
    serial = run_training(
        _config(tmp_path, manifest, "serial", workers=1),
        repo_root=Path("."),
    ).run_dir
    parallel_result = run_training(
        _config(tmp_path, manifest, "parallel", workers=2),
        repo_root=Path("."),
    )
    parallel = parallel_result.run_dir

    _assert_same_science(serial, parallel)
    runtime = parallel_result.runtime
    assert runtime["gauges"]["training_pending_shard_limit"] == 4
    assert runtime["gauges"]["training_pending_shards"] <= 4
    assert runtime["gauges"]["inspection_pending_shard_limit"] == 4
    assert runtime["gauges"]["inspection_pending_shards"] <= 4
    assert runtime["gauges"]["training_pending_shard_bytes"] > 0
    assert runtime["gauges"]["inspection_pending_shard_bytes"] > 0
    assert runtime["counters"]["inspection_shard_files_retired"] > 0
    assert runtime["counters"]["inspection_shard_bytes_retired"] > 0
    assert runtime["counters"]["topology_archives_compiled"] == 2
    assert runtime["counters"]["topology_archives_reused"] == 4
    assert not tuple((parallel / "shards" / "inspection").glob("*"))
    assert runtime["timings_seconds"]["training_reducer_stall"] >= 0.0
    assert runtime["timings_seconds"]["inspection_reducer_stall"] >= 0.0
