from __future__ import annotations

import copy
import csv
import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

from sktlm.latent.execution_bundles import load_execution_bundle_plan
from sktlm.latent.store import LexiconStore
from sktlm.latent.training import (
    EXPECTED_FREEZE_ID,
    S1M2_MODEL,
    TrainingConfig,
    load_documents,
    run_training,
)
from sktlm.production import s1m2


def _fixture(tmp_path: Path) -> tuple[Path, Path, tuple]:
    text = tmp_path / "surface.txt"
    text.write_text("devo'pi gacchati\ntattvamasi\n", encoding="utf-8", newline="")
    manifest = tmp_path / "representations.csv"
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
        writer.writerow(
            {
                "freeze_id": EXPECTED_FREEZE_ID,
                "relative_path": "tiny.txt",
                "script": "iast",
                "condition": "surface_word",
                "representation_path": str(text),
            }
        )
    config = tmp_path / "configs" / "planner.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"purpose":"tiny"}\n', encoding="utf-8", newline="")
    documents = load_documents(
        manifest,
        repo_root=Path("."),
        max_documents=None,
        script="iast",
        condition="surface_word",
    )
    return manifest, config, documents


def _plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, tuple]:
    manifest, config, documents = _fixture(tmp_path)
    output = tmp_path / "plan"
    planner = runpy.run_path("scripts/analysis/plan_s1m2_execution_bundles.py")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plan_s1m2_execution_bundles.py",
            "--repo-root",
            str(tmp_path),
            "--config",
            str(config),
            "--output-dir",
            str(output),
            "--cell-id",
            "tiny_iast_surface_word",
            "--manifest",
            str(manifest),
            "--script",
            "iast",
            "--condition",
            "surface_word",
            "--target-pressure",
            "16",
            "--max-segments-per-bundle",
            "1",
        ],
    )
    assert planner["main"]() == 0
    return output, config, documents


def _training_config(tmp_path: Path, manifest: Path, run_id: str, plan: Path | None) -> TrainingConfig:
    return TrainingConfig(
        manifest=manifest,
        output_root=tmp_path / "runs",
        run_id=run_id,
        model=S1M2_MODEL,
        script="iast",
        condition="surface_word",
        passes=1,
        workers=2,
        analysis_top_k=2,
        flush_types=2,
        piece_max_length=3,
        execution_bundle_plan=plan,
    )


def _piece_state(path: Path) -> tuple:
    store = LexiconStore(path / "learner.sqlite")
    try:
        return tuple(
            store.connection.execute(
                "SELECT form_key, expected_count, occurrence_support "
                "FROM piece_lexicon ORDER BY form_key"
            )
        )
    finally:
        store.close()


def test_surface_word_planner_load_and_generic_full_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_root, _config, documents = _plan(tmp_path, monkeypatch)
    manifest = tmp_path / "representations.csv"
    loaded = load_execution_bundle_plan(
        plan_root,
        repo_root=tmp_path,
        manifest=manifest,
        documents=documents,
        script="iast",
        condition="surface_word",
        max_segment_tokens=128,
        max_lines_per_document=None,
    )
    assert loaded.bundles
    assert all(bundle.segment_count == 1 for bundle in loaded.bundles)

    contract = copy.deepcopy(s1m2.load_contract(repo_root=Path("."), verify_files=False))
    surface = contract["cells"][0]
    contract["full_execution_bundle_plans"] = {
        surface["cell_id"]: {
            "execution_bundle_plan": "synthetic/surface",
            "execution_bundle_plan_sha256": "a" * 64,
            "script": surface["script"],
            "condition": surface["condition"],
        }
    }
    monkeypatch.setattr(s1m2, "validate_round3_closure", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        s1m2,
        "_bundle_plan_details",
        lambda _repo_root, declaration, *_args, **_kwargs: {
            "path": declaration["execution_bundle_plan"],
            "plan_sha256": declaration["execution_bundle_plan_sha256"],
            "materialization_sha256": "b" * 64,
        },
    )
    round2 = {
        "schema_version": s1m2.ROUND2_SCHEMA,
        "production_contract_sha256": s1m2._canonical_sha256(contract),
    }
    closure = {
        "retained_workers": 12,
        "round2_result_sha256": "c" * 64,
        "closure_sha256": "d" * 64,
    }
    final = s1m2.build_final_plan(
        contract,
        round2,
        closure,
        identity={"git_sha": "e" * 40, "branch": "test", "dirty_worktree": False},
        repo_root=tmp_path,
    )
    s1m2._validate_plan(final, contract)
    job = next(
        item for item in final["jobs"]
        if item["cell_id"] == surface["cell_id"]
    )
    assert job["execution_bundle_plan"] == "synthetic/surface"

    for cell_id, spec in s1m2.FULL_EXECUTION_BUNDLE_SPECS.items():
        if cell_id == surface["cell_id"]:
            continue
        default_job = next(
            item for item in final["jobs"]
            if item["cell_id"] == cell_id
        )
        assert (
            default_job["execution_bundle_plan"]
            == spec["execution_bundle_plan"]
        )
        assert (
            default_job["execution_bundle_plan_sha256"]
            == spec["execution_bundle_plan_sha256"]
        )


def test_surface_word_bundled_training_is_scientifically_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_root, _config, _documents = _plan(tmp_path, monkeypatch)
    manifest = tmp_path / "representations.csv"
    reference = run_training(
        _training_config(tmp_path, manifest, "reference", None), repo_root=Path(".")
    )
    bundled = run_training(
        _training_config(tmp_path, manifest, "bundled", plan_root), repo_root=Path(".")
    )
    assert reference.history == bundled.history
    assert _piece_state(reference.run_dir) == _piece_state(bundled.run_dir)
    for name in (
        "iteration_metrics.json",
        "piece_inventory.tsv",
        "lexical_diagnostics.tsv",
        "analyses.jsonl",
        "boundary_posteriors.jsonl",
        "rule_usage.tsv",
        "summary.json",
    ):
        assert (reference.run_dir / name).read_bytes() == (bundled.run_dir / name).read_bytes()


def test_planner_config_hash_accepts_eol_checkout_but_rejects_content_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_root, config, documents = _plan(tmp_path, monkeypatch)
    manifest = tmp_path / "representations.csv"
    config.write_bytes(config.read_bytes().replace(b"\n", b"\r\n"))
    load_execution_bundle_plan(
        plan_root,
        repo_root=tmp_path,
        manifest=manifest,
        documents=documents,
        script="iast",
        condition="surface_word",
        max_segment_tokens=128,
        max_lines_per_document=None,
    )
    config.write_text('{"purpose":"changed"}\n', encoding="utf-8", newline="")
    with pytest.raises(ValueError, match="planner config mismatch"):
        load_execution_bundle_plan(
            plan_root,
            repo_root=tmp_path,
            manifest=manifest,
            documents=documents,
            script="iast",
            condition="surface_word",
            max_segment_tokens=128,
            max_lines_per_document=None,
        )

def test_planner_metadata_paths_are_posix_and_backslashes_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_root, _config, documents = _plan(tmp_path, monkeypatch)
    manifest = tmp_path / "representations.csv"
    scan_path = plan_root / "scan_summary.json"
    scan = json.loads(scan_path.read_text(encoding="utf-8"))

    assert scan["config"] == "configs/planner.json"
    assert "\\" not in scan["config"]
    assert "\\" not in scan["manifest"]

    scan["config"] = r"configs\planner.json"
    scan_path.write_text(
        json.dumps(scan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )

    with pytest.raises(ValueError, match="planner config path"):
        load_execution_bundle_plan(
            plan_root,
            repo_root=tmp_path,
            manifest=manifest,
            documents=documents,
            script="iast",
            condition="surface_word",
            max_segment_tokens=128,
            max_lines_per_document=None,
        )
