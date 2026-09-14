from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sktlm.production import s1m2


IDENTITY = {
    "git_sha": "a" * 40,
    "branch": "exp/s1m2-reusable-pieces",
    "dirty_worktree": False,
}


def _round1_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict, dict, dict, Path]:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    plan = s1m2.build_round1_plan(contract, identity=IDENTITY)
    job = plan["jobs"][0]
    manifest = tmp_path / "input.csv"
    manifest.write_text("fixture\n", encoding="utf-8")
    job["manifest"] = str(manifest)
    job["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    job["output_root"] = str(tmp_path / "runs")
    job["run_dir"] = str(tmp_path / "runs" / job["run_id"])
    job["metrics_root"] = str(tmp_path / "metrics")
    job["control_dir"] = str(tmp_path / "metrics" / job["metrics_id"])
    job["execution_bundle_plan"] = None
    job["execution_bundle_plan_sha256"] = None
    job["execution_bundle_materialization_sha256"] = None
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(s1m2, "load_contract", lambda *args, **kwargs: contract)
    monkeypatch.setattr(s1m2, "_validate_plan", lambda *args, **kwargs: None)
    monkeypatch.setattr(s1m2, "git_identity", lambda _root: IDENTITY)
    return contract, plan, job, plan_path


def test_production_commands_bind_current_interpreter() -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    plan = s1m2.build_round1_plan(contract, identity=IDENTITY)
    s1m2._write_plan_commands(plan, Path("round1.json"))
    assert all(job["training_command"][0] == "python" for job in plan["jobs"])
    assert all(
        s1m2._phase_command(job, phase="pass_001", resume=False)[0]
        == sys.executable
        for job in plan["jobs"]
    )
    assert all(
        job["launch_command"][0] == "./.venv/bin/python"
        for job in plan["jobs"]
    )
    assert all(
        job["audit_command"][0] == "./.venv/bin/python"
        for job in plan["jobs"]
    )


def test_production_bundle_validation_delegates_to_trainer_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "summary.json").write_text(
        json.dumps({"target_pressure": 17, "max_segments_per_bundle": 2}),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("fixture\n", encoding="utf-8")
    calls: list[dict] = []
    monkeypatch.setattr(s1m2, "load_documents", lambda *args, **kwargs: ("doc",))

    def load(path: Path, **kwargs: object) -> SimpleNamespace:
        calls.append({"path": path, **kwargs})
        return SimpleNamespace(
            root=root,
            plan_sha256="a" * 64,
            materialization_sha256="b" * 64,
        )

    monkeypatch.setattr(s1m2, "load_execution_bundle_plan", load)
    details = s1m2._bundle_plan_details(
        tmp_path,
        {
            "execution_bundle_plan": "bundle",
            "execution_bundle_plan_sha256": "a" * 64,
            "script": "iast",
            "condition": "surface_word",
            "target_pressure": 17,
            "max_segments_per_bundle": 2,
        },
        {"document_list": None, "max_lines_per_document": None},
        {"max_segment_tokens": 128},
        manifest="manifest.csv",
    )
    assert details["materialization_sha256"] == "b" * 64
    assert len(calls) == 1


def test_full_authorization_is_exact_plan_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    plan = {"plan_type": "full", "plan_sha256": "b" * 64, "git_sha": IDENTITY["git_sha"],
            "branch": IDENTITY["branch"], "production_contract_sha256": s1m2._canonical_sha256(contract),
            "jobs": [{"job_id": "j", "cell_id": "c"}]}
    monkeypatch.setattr(s1m2, "_validate_plan", lambda *args: None)
    authorization = s1m2.build_full_authorization(plan, contract, identity=IDENTITY)
    s1m2._validate_full_authorization(authorization, plan, contract)
    changed = {**plan, "plan_sha256": "c" * 64}
    with pytest.raises(ValueError, match="plan_sha256"):
        s1m2._validate_full_authorization(authorization, changed, contract)
    forged = {**authorization, "git_sha": "0" * 40}
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        s1m2._validate_full_authorization(forged, plan, contract)
    for changed_field, changed_value in (
        ("git_sha", "0" * 40),
        ("production_contract_sha256", "0" * 64),
        ("job_ids", ["other-job"]),
    ):
        other = {**authorization, changed_field: changed_value}
        other["authorization_sha256"] = s1m2._canonical_sha256(
            {
                key: value
                for key, value in other.items()
                if key != "authorization_sha256"
            }
        )
        with pytest.raises(ValueError, match=changed_field):
            s1m2._validate_full_authorization(other, plan, contract)


def test_full_run_without_authorization_fails_before_state_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract, plan, job, plan_path = _round1_job(tmp_path, monkeypatch)
    plan["plan_type"] = "full"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(RuntimeError, match="explicit authorization"):
        s1m2.run_job(
            plan_path=plan_path,
            job_id=job["job_id"],
            contract_path=Path("unused"),
            repo_root=Path("."),
            host_id=job["host_role"],
            resume=False,
        )
    assert not Path(job["control_dir"]).exists()


def test_full_launch_preflight_rejects_low_free_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    job = {
        "output_root": str(tmp_path / "runs"),
        "metrics_root": str(tmp_path / "metrics"),
    }
    monkeypatch.setattr(
        s1m2.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100, used=99, free=1),
    )
    monkeypatch.setattr(s1m2, "_host_memory_bytes", lambda: 64 * 1024**3)
    with pytest.raises(RuntimeError, match="free-space gate"):
        s1m2._full_launch_preflight(job, contract, repo_root=Path("."))


@pytest.mark.skipif(
    os.name == "posix",
    reason="success fixture does not provide a dedicated non-root data mount",
)
def test_full_launch_preflight_records_exact_local_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    job = {
        "output_root": str(tmp_path / "runs"),
        "metrics_root": str(tmp_path / "metrics"),
    }
    free = int(contract["gates"]["storage_min_free_bytes_end"]) + 1
    monkeypatch.setattr(
        s1m2.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=free * 2, used=free - 1, free=free),
    )
    monkeypatch.setattr(s1m2, "_host_memory_bytes", lambda: 64 * 1024**3)
    receipt = s1m2._full_launch_preflight(job, contract, repo_root=Path("."))
    assert receipt["status"] == "PASS"
    assert receipt["python_executable"] == sys.executable
    assert receipt["run_filesystem_free_bytes"] == free
    assert receipt["host_memory_bytes"] == 64 * 1024**3


def test_plan_final_rejects_authoritative_bundle_loader_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    round2 = {
        "schema_version": s1m2.ROUND2_SCHEMA,
        "plan_sha256": "c" * 64,
        "production_contract_sha256": s1m2._canonical_sha256(contract),
        "ROUND2_STATUS": "FAIL",
        "WINNER_WORKERS": None,
        "jobs": [{"candidate_overflow": 1} for _ in range(6)],
    }
    monkeypatch.setattr(
        s1m2, "validate_round3_closure", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        s1m2,
        "_bundle_plan_details",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("malformed authoritative bundle")
        ),
    )
    with pytest.raises(ValueError, match="malformed authoritative bundle"):
        s1m2.build_final_plan(
            contract,
            round2,
            {"retained_workers": 12},
            identity=IDENTITY,
            repo_root=tmp_path,
        )


@pytest.mark.parametrize("error", (FileNotFoundError("missing"), PermissionError("denied")))
def test_subprocess_launch_error_is_durably_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: OSError,
) -> None:
    _contract, _plan, job, plan_path = _round1_job(tmp_path, monkeypatch)
    monkeypatch.setattr(s1m2.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    with pytest.raises(RuntimeError, match="could not be launched"):
        s1m2.run_job(
            plan_path=plan_path,
            job_id=job["job_id"],
            contract_path=Path("unused"),
            repo_root=Path("."),
            host_id=job["host_role"],
            resume=False,
        )
    manifest = json.loads(
        (Path(job["control_dir"]) / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["result_status"] == "FAILED"
    phase = manifest["resume_history"][-1]["phases"][-1]
    assert phase["launch_error"]["type"] == type(error).__name__


def test_job_status_prefers_sqlite_over_stale_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract, plan, job, _plan_path = _round1_job(tmp_path, monkeypatch)
    run_dir = Path(job["run_dir"])
    run_dir.mkdir(parents=True)
    checkpoint = {
        "completed_passes": 2,
        "active_pass": 3,
        "next_document_index": 7,
    }
    connection = sqlite3.connect(run_dir / "learner.sqlite")
    connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute(
        "INSERT INTO metadata VALUES ('training_checkpoint', ?)",
        (json.dumps(checkpoint),),
    )
    connection.commit()
    connection.close()
    (run_dir / "checkpoint.json").write_text(
        json.dumps({"completed_passes": 1, "next_document_index": 99}),
        encoding="utf-8",
    )
    status = s1m2.job_status(plan, job, contract, repo_root=Path("."))
    assert status["completed_passes"] == 2
    assert status["active_pass"] == 3
    assert status["next_document_index"] == 7
    assert status["checkpoint_source"] == "learner.sqlite"
    assert status["checkpoint_mirror_matches"] is False


def test_reset_failed_is_exact_and_preserves_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract, plan, job, _plan_path = _round1_job(tmp_path, monkeypatch)
    run_dir = Path(job["run_dir"])
    control_dir = Path(job["control_dir"])
    run_dir.mkdir(parents=True)
    control_dir.mkdir(parents=True)
    manifest = {
        "result_status": "FAILED",
        "plan_sha256": "old-plan",
        "git_sha": "0" * 40,
        "cell_id": job["cell_id"],
        "workload_id": job["workload_id"],
        "run_id": job["run_id"],
        "metrics_id": job["metrics_id"],
        "host_id": job["host_role"],
        "final_audit": None,
    }
    (control_dir / "run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (run_dir / "production_run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    receipt = tmp_path / "reset.json"
    result = s1m2.reset_failed_job(
        plan,
        job,
        contract,
        repo_root=Path("."),
        host_id=job["host_role"],
        confirmed_job_id=job["job_id"],
        receipt_path=receipt,
    )
    assert result["status"] == "RESET"
    assert result["old_result_status"] == "FAILED"
    assert result["old_run_id"] == job["run_id"]
    assert result["reason"] == (
        "explicit_discard_of_exact_failed_run_before_clean_restart"
    )
    assert receipt.is_file()
    assert not run_dir.exists()
    assert not control_dir.exists()


@pytest.mark.parametrize("status", ("RUNNING", "PASS", "AUDITING"))
def test_reset_failed_refuses_nonfailed_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    contract, plan, job, _plan_path = _round1_job(tmp_path, monkeypatch)
    run_dir = Path(job["run_dir"])
    control_dir = Path(job["control_dir"])
    run_dir.mkdir(parents=True)
    control_dir.mkdir(parents=True)
    manifest = {
        "result_status": status,
        "cell_id": job["cell_id"],
        "workload_id": job["workload_id"],
        "run_id": job["run_id"],
        "metrics_id": job["metrics_id"],
        "host_id": job["host_role"],
    }
    (control_dir / "run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    receipt = tmp_path / "refused-reset.json"
    with pytest.raises(RuntimeError, match="Only a FAILED"):
        s1m2.reset_failed_job(
            plan,
            job,
            contract,
            repo_root=Path("."),
            host_id=job["host_role"],
            confirmed_job_id=job["job_id"],
            receipt_path=receipt,
        )
    assert run_dir.is_dir()
    assert control_dir.is_dir()
    assert not receipt.exists()
