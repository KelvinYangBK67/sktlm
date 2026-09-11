from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from sktlm.production import s1m2


IDENTITY = {
    "git_sha": "a" * 40,
    "branch": "exp/s1m2-reusable-pieces",
    "dirty_worktree": False,
}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _evidence_fixture(tmp_path: Path, contract: dict) -> tuple[Path, Path, Path, tuple[Path, ...]]:
    round2_path = tmp_path / "round2.json"
    round2 = {
        "schema_version": s1m2.ROUND2_SCHEMA,
        "plan_sha256": "c" * 64,
        "production_contract_sha256": s1m2._canonical_sha256(contract),
        "ROUND2_STATUS": "FAIL",
        "WINNER_WORKERS": None,
        "jobs": [{"candidate_overflow": 1} for _ in range(6)],
    }
    real_path = tmp_path / "raw520.json"
    real = {
        "status": "PASS",
        "gate": "REAL_OFFENDER_COMPACT_VS_LEGACY_EXACTNESS",
        "case": {"raw_internal_matches": 520, "retained_internal_matches": 520},
        "compact": {"support_truncation_tokens": 0, "shared_batch_fallbacks": 0},
        "scientific_equivalence": {"posterior": "PASS"},
    }
    worker_path = tmp_path / "workers.json"
    worker = {
        "status": "PASS",
        "gate": "COMPACT_LOCAL_WORKER_SCIENTIFIC_EQUIVALENCE",
        "workers": [2, 4],
        "same_bundle_plan": True,
        "training_history": "EXACT",
        "piece_lexicon_state": "EXACT",
        "scientific_artifacts_all_byte_identical": True,
        "worker_selection_reopened": False,
        "round2_engineering_preference_retained": 12,
        "scientific_artifacts": {"summary.json": {"equal": True}},
    }
    tail_paths = tuple(tmp_path / f"raw{raw}.json" for raw in (1002, 1410, 1841, 2484))
    for raw, path in zip((1002, 1410, 1841, 2484), tail_paths, strict=True):
        _write_json(
            path,
            {
                "status": "PASS",
                "gate": "COMPACT_PRODUCTION_PASS1_TAIL",
                "case": {"raw": raw, "retained": raw},
                "compact": {"support_truncation_tokens": 0, "shared_batch_fallbacks": 0},
                "posterior_mass": 1.0,
            },
        )
    _write_json(round2_path, round2)
    _write_json(real_path, real)
    _write_json(worker_path, worker)
    return round2_path, real_path, worker_path, tail_paths


def _build_closure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, contract: dict) -> tuple[dict, dict]:
    paths = _evidence_fixture(tmp_path, contract)
    monkeypatch.setattr(s1m2, "_git_is_ancestor", lambda *args: True)
    closure = s1m2.build_round3_closure(
        contract,
        paths[0],
        real_offender_path=paths[1],
        worker_equivalence_path=paths[2],
        tail_paths=paths[3],
        repo_root=tmp_path,
    )
    return json.loads(paths[0].read_text(encoding="utf-8")), closure


def test_round3_closure_binds_evidence_and_builds_w12_full_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    round2, closure = _build_closure(monkeypatch, tmp_path, contract)
    s1m2.validate_round3_closure(closure, contract, round2, repo_root=tmp_path)
    monkeypatch.setattr(
        s1m2,
        "_bundle_plan_details",
        lambda *args, **kwargs: {
            "path": s1m2.FULL_EXECUTION_BUNDLE_PLAN,
            "plan_sha256": s1m2.FULL_EXECUTION_BUNDLE_PLAN_SHA256,
            "materialization_sha256": "d" * 64,
        },
    )
    plan = s1m2.build_final_plan(
        contract, round2, closure, identity=IDENTITY, repo_root=tmp_path
    )
    s1m2._validate_plan(plan, contract)
    assert len(plan["jobs"]) == 6
    assert {job["workers"] for job in plan["jobs"]} == {12}
    assert plan["ROUND2_FORMAL_RESULT"] == "PRESERVED_FAIL"
    assert plan["ROUND2_FORMAL_WINNER"] is None
    assert plan["FULL_ELIGIBILITY"] == "PASS"


def test_round3_closure_rejects_forged_round2_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    round2_path, real, worker, tails = _evidence_fixture(tmp_path, contract)
    payload = json.loads(round2_path.read_text(encoding="utf-8"))
    payload["ROUND2_STATUS"] = "PASS"
    _write_json(round2_path, payload)
    with pytest.raises(ValueError, match="immutable Round 2 FAIL"):
        s1m2.build_round3_closure(
            contract,
            round2_path,
            real_offender_path=real,
            worker_equivalence_path=worker,
            tail_paths=tails,
            repo_root=tmp_path,
        )


@pytest.mark.parametrize("tamper", ["raw2484_missing", "truncation", "reopened", "exactness"])
def test_round3_closure_fails_closed_on_gate_tampering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tamper: str
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    round2, real, worker, tails = _evidence_fixture(tmp_path, contract)
    if tamper == "raw2484_missing":
        tails = tails[:-1]
    elif tamper == "truncation":
        payload = json.loads(tails[0].read_text(encoding="utf-8"))
        payload["compact"]["support_truncation_tokens"] = 1
        _write_json(tails[0], payload)
    elif tamper == "reopened":
        payload = json.loads(worker.read_text(encoding="utf-8"))
        payload["worker_selection_reopened"] = True
        _write_json(worker, payload)
    else:
        payload = json.loads(real.read_text(encoding="utf-8"))
        payload["status"] = "FAIL"
        _write_json(real, payload)
    with pytest.raises(ValueError):
        s1m2.build_round3_closure(
            contract,
            round2,
            real_offender_path=real,
            worker_equivalence_path=worker,
            tail_paths=tails,
            repo_root=tmp_path,
        )


def test_compact_completed_run_allows_zero_topology_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    job = {
        "run_dir": str(run_dir),
        "passes": 3,
        "script": "iast",
        "condition": "continuous",
        "document_list_sha256": "d" * 64,
    }
    monkeypatch.setattr(
        s1m2, "_config_for_job", lambda *args, **kwargs: SimpleNamespace(payload=lambda: {})
    )
    for name in contract["artifact_contract"]["scientific"]:
        (run_dir / name).write_text("{}", encoding="utf-8")
    for name in contract["artifact_contract"]["operational"]:
        if name != "learner.sqlite":
            (run_dir / name).write_text("{}", encoding="utf-8")
    _write_json(run_dir / "checkpoint.json", {"completed_passes": 3, "inspection_complete": True})
    _write_json(run_dir / "summary.json", {"overflowed_tokens": 0})
    _write_json(
        run_dir / "provenance.json",
        {
            "git_commit": "a" * 40,
            "freeze_id": contract["corpus"]["freeze_id"],
            "rules_sha256": contract["grammar"]["sha256"],
            "external_rule_count": contract["grammar"]["rule_count"],
            "document_list_sha256": "d" * 64,
            "script": "iast",
            "condition": "continuous",
        },
    )
    _write_json(
        run_dir / "storage_manifest.json",
        {"status": "COMPACT", "compiled_topology": {"mutable_scores_or_posteriors_stored": False}},
    )
    with sqlite3.connect(run_dir / "learner.sqlite") as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
        connection.execute("CREATE TABLE piece_lexicon (piece TEXT PRIMARY KEY, count REAL)")
    audit = s1m2._audit_artifacts(job, contract, repo_root=tmp_path, metrics_summary=None)
    assert audit["valid"] is True
    assert audit["legacy_topology_required"] is False
    storage = json.loads((run_dir / "storage_manifest.json").read_text(encoding="utf-8"))
    storage["compiled_topology"]["mutable_scores_or_posteriors_stored"] = True
    _write_json(run_dir / "storage_manifest.json", storage)
    assert s1m2._audit_artifacts(
        job, contract, repo_root=tmp_path, metrics_summary=None
    )["valid"] is False
