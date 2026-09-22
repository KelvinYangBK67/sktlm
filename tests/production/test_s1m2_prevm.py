from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from types import SimpleNamespace
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

import pytest

from sktlm.production import s1m2


IDENTITY = {
    "git_sha": "a" * 40,
    "branch": "exp/s1m2-reusable-pieces",
    "dirty_worktree": False,
}


def _contract() -> dict[str, object]:
    return s1m2.load_contract(repo_root=Path("."), verify_files=False)


def _round1_result(workers: int = 16) -> dict[str, object]:
    contract = _contract()
    return {
        "schema_version": s1m2.ROUND1_SCHEMA,
        "plan_sha256": "b" * 64,
        "production_contract_sha256": s1m2._canonical_sha256(contract),
        "ROUND1_STATUS": "PASS",
        "WINNER_WORKERS": workers,
        "WORKER_RANKING": [
            {"workers": value} for value in s1m2.ROUND1_WORKERS
        ],
        "jobs": [
            {"workers": value, "valid": True} for value in s1m2.ROUND1_WORKERS
        ],
    }


def _round2_result() -> dict[str, object]:
    contract = _contract()
    return {
        "schema_version": s1m2.ROUND2_SCHEMA,
        "plan_sha256": "c" * 64,
        "production_contract_sha256": s1m2._canonical_sha256(contract),
        "ROUND2_STATUS": "FAIL",
        "WINNER_WORKERS": None,
        "jobs": [{"valid": False, "candidate_overflow": 1} for _ in range(6)],
    }


def _round3_closure() -> dict[str, object]:
    return {
        "closure_sha256": "e" * 64,
        "round2_result_sha256": "f" * 64,
        "retained_workers": 12,
    }


def _mock_bundle_details(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        s1m2,
        "_bundle_plan_details",
        lambda _root, declaration, *_args, **_kwargs: {
            "path": declaration["execution_bundle_plan"],
            "plan_sha256": declaration.get("execution_bundle_plan_sha256")
            or "a" * 64,
            "materialization_sha256": "b" * 64,
        },
    )


def _valid_round2_attestations(
    plan: dict[str, object], contract: dict[str, object]
) -> list[dict[str, object]]:
    attestations = []
    for job in plan["jobs"]:
        workers = int(job["workers"])
        attestations.append(
            {
                "schema_version": s1m2.ROUND2_ATTESTATION_SCHEMA,
                "job_id": job["job_id"],
                "host_role": job["host_role"],
                "workload": job["workload_id"],
                "workers": workers,
                "valid": True,
                "failures": [],
                "wall_seconds": 100.0 + workers,
                "peak_process_tree_rss_bytes": 1024 * workers,
                "peak_watched_run_bytes": 2048 * workers,
                "sampled_process_tree_cpu_seconds": 50.0 * workers,
                "canonical_reducer_stall_seconds": float(workers),
                "bundle_true_inflight": workers,
                "bundle_ready_shard": 1,
                "completed_passes": contract["passes"],
                "candidate_overflow": 0,
                "host_memory_bytes": 1024**4,
                "filesystem_free_bytes_end": 30 * 1024**3,
                "git_sha": plan["git_sha"],
                "execution_bundle_plan": job["execution_bundle_plan"],
                "execution_bundle_plan_sha256": job[
                    "execution_bundle_plan_sha256"
                ],
                "execution_bundle_materialization_sha256": job[
                    "execution_bundle_materialization_sha256"
                ],
                "plan_identity": {
                    "schema_version": plan["schema_version"],
                    "plan_type": plan["plan_type"],
                    "plan_sha256": plan["plan_sha256"],
                    "git_sha": plan["git_sha"],
                    "branch": plan["branch"],
                },
                "production_contract_identity": {
                    "path": plan["contract_path"],
                    "sha256": plan["production_contract_sha256"],
                },
            }
        )
    return attestations


def test_six_cell_contract_is_exact_and_iast_continuous_is_m0_prime(
    tmp_path: Path,
) -> None:
    contract = _contract()
    cells = contract["cells"]
    assert len(cells) == 6
    continuous = [
        cell
        for cell in cells
        if cell["condition"] == "continuous" and cell["script"].startswith("iast")
    ]
    assert continuous == [
        {
            "cell_id": "s1m2_m0_prime_iast_continuous",
            "substrate": "M0-prime",
            "script": "iast_m0_prime",
            "condition": "continuous",
            "manifest_key": "m0_prime_manifest",
        }
    ]

    invalid = copy.deepcopy(contract)
    invalid["cells"][2] = dict(continuous[0], script="iast", substrate="M0")
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError):
        s1m2.load_contract(invalid_path, repo_root=Path("."), verify_files=False)


def test_default_production_contract_is_qualified_v3_and_history_is_unchanged(
    tmp_path: Path,
) -> None:
    contract = _contract()
    assert s1m2.CONTRACT_PATH == Path("configs/production/s1m2_six_cell_v3.json")
    assert contract["contract_id"] == "s1m2-six-cell-v3-prefreeze-v1"
    assert contract["status"] == "V3_QUALIFIED_PENDING_RESEARCHER_FREEZE"
    assert contract["model"] == "reusable_pieces_v3"
    assert contract["passes"] == 3
    assert contract["scientific_config"]["sandhi_transformation_penalty"] == 1.0
    assert contract["scientific_config"]["piece_boundary_probability"] == 0.4

    historical = json.loads(
        Path("configs/production/s1m2_six_cell.json").read_text(encoding="utf-8")
    )
    assert historical["contract_id"] == "s1m2-six-cell-v2-repair-v1"
    assert historical["model"] == "reusable_pieces_v1"
    assert "sandhi_transformation_penalty" not in historical["scientific_config"]
    assert historical["scientific_config"]["piece_boundary_probability"] == 0.5

    plan = s1m2.build_bounded_plan(contract, identity=IDENTITY)
    for job in plan["jobs"]:
        command = job["training_command"]
        assert job["model"] == "reusable_pieces_v3"
        assert command[command.index("--model") + 1] == "reusable_pieces_v3"
        assert command[command.index("--sandhi-transformation-penalty") + 1] == "1.0"
        assert command[command.index("--piece-boundary-probability") + 1] == "0.4"
        config = s1m2._config_for_job(job, resume=True)
        assert config.model == "reusable_pieces_v3"
        assert config.sandhi_transformation_penalty == 1.0
        assert config.piece_boundary_probability == 0.4
        assert config.resume is True

    for field, value in (
        ("model", "reusable_pieces_v2"),
        ("sandhi_transformation_penalty", 0.0),
        ("piece_boundary_probability", 0.5),
    ):
        invalid = copy.deepcopy(contract)
        if field == "model":
            invalid[field] = value
        else:
            invalid["scientific_config"][field] = value
        invalid_path = tmp_path / f"invalid-{field}.json"
        invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
        with pytest.raises(ValueError):
            s1m2.load_contract(
                invalid_path,
                repo_root=Path("."),
                verify_files=False,
            )


def test_s1m2_deployment_contract_is_bundle_bound_and_branch_explicit() -> None:
    contract = _contract()
    assert contract["deployment"] == {
        "cloud_contract": "configs/cloud/s1m2_prevm.yaml",
        "branch": "exp/s1m2-reusable-pieces",
        "mode": "git_bundle",
    }
    cloud_contract = s1m2.load_experiment_contract(
        Path(contract["deployment"]["cloud_contract"])
    )
    assert cloud_contract.branch == IDENTITY["branch"]
    assert cloud_contract.deployment.mode == "git_bundle"


def test_production_identity_files_have_platform_independent_checkout_bytes() -> None:
    attributes = Path(".gitattributes").read_text(encoding="utf-8")
    assert "data/rules/external_sandhi.tsv text eol=crlf" in attributes
    assert "configs/benchmarks/latent_smoke_documents.txt text eol=crlf" in attributes
    for name in (
        "s1m2_prevm_bounded_documents.txt",
        "s1m2_continuous_representative_documents.txt",
        "s1m2_continuous_stress_documents.txt",
    ):
        assert f"configs/benchmarks/{name} text eol=lf" in attributes


def test_round1_plan_has_six_jobs_and_only_workers_vary() -> None:
    contract = _contract()
    plan = s1m2.build_round1_plan(contract, identity=IDENTITY)
    s1m2._validate_plan(plan, contract)
    assert [job["workers"] for job in plan["jobs"]] == [4, 8, 12, 16, 20, 24]
    assert [job["host_role"] for job in plan["jobs"]] == list(
        s1m2.CORE_HOST_ROLES
    )
    assert len({job["host_role"] for job in plan["jobs"]}) == 6
    assert plan["launch_mode"] == "six_way_parallel"
    assert {job["cell_id"] for job in plan["jobs"]} == {
        "s1m2_m0_devanagari_continuous"
    }
    assert {job["workload_id"] for job in plan["jobs"]} == {"worker_calibration"}
    assert {job["passes"] for job in plan["jobs"]} == {3}
    assert {job["max_lines_per_document"] for job in plan["jobs"]} == {256}
    assert {job["document_list"] for job in plan["jobs"]} == {
        "configs/benchmarks/s1m2_worker_calibration_documents.txt"
    }
    assert len({str(job["resolved_config"]) for job in plan["jobs"]}) == 1
    assert all("--model" in job["training_command"] for job in plan["jobs"])
    assert all("--resume" not in job["training_command"] for job in plan["jobs"])

    tampered = copy.deepcopy(plan)
    tampered["jobs"][0]["condition"] = "surface_word"
    tampered["plan_sha256"] = s1m2._canonical_sha256(
        {key: value for key, value in tampered.items() if key != "plan_sha256"}
    )
    with pytest.raises(ValueError, match="invalid condition"):
        s1m2._validate_plan(tampered, contract)

    wrong_host = copy.deepcopy(plan)
    wrong_host["jobs"][0]["host_role"] = "core-02"
    wrong_host["plan_sha256"] = s1m2._canonical_sha256(
        {key: value for key, value in wrong_host.items() if key != "plan_sha256"}
    )
    with pytest.raises(ValueError, match="frozen host mapping"):
        s1m2._validate_plan(wrong_host, contract)


def test_worker_calibration_selector_is_frozen_distinct_and_nonstress() -> None:
    def document(path: str, pressure: int) -> dict[str, object]:
        return {
            "relative_path": path,
            "span_squared_phonemes": pressure,
            "continuous_spans": {"max": pressure + 1},
            "phonemes": pressure + 2,
        }

    stress = ["synthetic/stress_a.txt", "synthetic/stress_b.txt"]
    candidates = [
        document(f"synthetic/document_{index:03d}.txt", index)
        for index in range(144)
    ]
    structure = {
        "cells": {
            "m0_devanagari_continuous": {
                "script": "devanagari",
                "documents": [
                    document(stress[0], 1000),
                    *reversed(candidates),
                    document(stress[1], 1001),
                ],
            }
        },
        "selection": {"stress": stress},
    }
    selected = s1m2.select_worker_calibration_documents(structure)
    assert selected == [
        f"synthetic/document_{index:03d}.txt" for index in range(0, 144, 2)
    ]
    assert selected == s1m2.select_worker_calibration_documents(structure)
    assert len(selected) == len(set(selected)) == 72
    assert not set(selected).intersection(stress)

    tracked_path = Path(
        "configs/benchmarks/s1m2_worker_calibration_documents.txt"
    )
    tracked = tracked_path.read_text(encoding="utf-8").splitlines()
    tracked_stress = {
        line
        for line in Path(
            "configs/benchmarks/s1m2_continuous_stress_documents.txt"
        ).read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    workload = _contract()["workloads"]["worker_calibration"]
    assert workload["structure_sha256"] == (
        s1m2.WORKER_CALIBRATION_STRUCTURE_SHA256
    )
    assert workload["document_list"] == tracked_path.as_posix()
    assert workload["document_list_sha256"] == hashlib.sha256(
        tracked_path.read_bytes()
    ).hexdigest()
    assert workload["documents"] == len(tracked) == len(set(tracked)) == 72
    assert not set(tracked).intersection(tracked_stress)


def test_plan_commands_bind_exact_plan_path() -> None:
    contract = _contract()
    plan = s1m2.build_round1_plan(contract, identity=IDENTITY)
    plan_path = Path("artifacts/s1m2_production/round1_plan.json")
    s1m2._write_plan_commands(plan, plan_path)
    s1m2._validate_plan(plan, contract)
    for job in plan["jobs"]:
        assert job["launch_command"][4:6] == ["--plan", plan_path.as_posix()]
        assert job["resume_command"] == [*job["launch_command"], "--resume"]
        assert job["audit_command"][4:6] == ["--plan", plan_path.as_posix()]


def test_production_run_isolates_passes_and_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _contract()
    plan = s1m2.build_round1_plan(contract, identity=IDENTITY)
    job = plan["jobs"][0]
    source_manifest = tmp_path / "input.csv"
    source_manifest.write_text("fixture\n", encoding="utf-8")
    job["manifest"] = source_manifest.as_posix()
    job["manifest_sha256"] = hashlib.sha256(
        source_manifest.read_bytes()
    ).hexdigest()
    job["output_root"] = (tmp_path / "runs").as_posix()
    job["run_dir"] = (tmp_path / "runs" / job["run_id"]).as_posix()
    job["control_dir"] = (tmp_path / "control").as_posix()
    job["passes"] = 3
    job["execution_bundle_plan"] = None
    job["execution_bundle_plan_sha256"] = None
    job["execution_bundle_materialization_sha256"] = None
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    monkeypatch.setattr(s1m2, "load_contract", lambda *args, **kwargs: contract)
    monkeypatch.setattr(s1m2, "_validate_plan", lambda *args: None)
    monkeypatch.setattr(s1m2, "git_identity", lambda root: IDENTITY)
    monkeypatch.setattr(
        s1m2,
        "_audit_artifacts",
        lambda *args, **kwargs: {"valid": True, "failures": []},
    )
    launched: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        if "--output-dir" not in command:
            return SimpleNamespace(returncode=0, stdout="")
        launched.append(command)
        output_dir = Path(command[command.index("--output-dir") + 1])
        output_dir.mkdir(parents=True)
        (output_dir / "process_tree_samples.csv").write_text(
            "wall_seconds,peak_rss_bytes\n1,1024\n", encoding="utf-8"
        )
        (output_dir / "process_tree_summary.json").write_text(
            json.dumps(
                {
                    "command": command,
                    "return_code": 0,
                    "wall_seconds": 1.0,
                    "peak_process_tree_rss_bytes": 1024,
                    "sampled_process_tree_cpu_seconds": 0.5,
                    "sampled_process_tree_read_bytes": 1,
                    "sampled_process_tree_write_bytes": 2,
                    "sampled_process_tree_io_wait_seconds": 0.0,
                    "peak_watched_run_bytes": 2048,
                    "host_memory_bytes": 4096,
                    "filesystem_free_bytes_min": 8192,
                    "filesystem_free_bytes_end": 8192,
                }
            ),
            encoding="utf-8",
        )
        run_dir = Path(job["run_dir"])
        run_dir.mkdir(parents=True, exist_ok=True)
        database = run_dir / "learner.sqlite"
        connection = sqlite3.connect(database)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'training_checkpoint'"
        ).fetchone()
        checkpoint = (
            json.loads(row[0])
            if row is not None
            else {
                "completed_passes": 0,
                "active_pass": None,
                "next_document_index": 0,
                "history": [],
            }
        )
        if "--next-pass-only" in command:
            checkpoint["completed_passes"] += 1
            checkpoint["history"].append({"pass": checkpoint["completed_passes"]})
        else:
            assert "--inspection-only" in command
            checkpoint["inspection_complete"] = True
        checkpoint["active_pass"] = None
        checkpoint["next_document_index"] = 0
        connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            ("training_checkpoint", json.dumps(checkpoint, sort_keys=True)),
        )
        connection.commit()
        connection.close()
        (run_dir / "checkpoint.json").write_text(
            json.dumps(checkpoint), encoding="utf-8"
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(s1m2.subprocess, "run", fake_run)
    assert s1m2.run_job(
        plan_path=plan_path,
        job_id=job["job_id"],
        contract_path=Path("unused.json"),
        repo_root=Path("."),
        host_id=job["host_role"],
        resume=False,
    ) == 0
    assert len(launched) == 4
    assert all("--next-pass-only" in command for command in launched[:3])
    assert "--resume" not in launched[0]
    assert all("--resume" in command for command in launched[1:])
    assert "--inspection-only" in launched[-1]
    run_manifest = json.loads(
        (tmp_path / "control" / "run_manifest.json").read_text(encoding="utf-8")
    )
    phases = run_manifest["resume_history"][0]["phases"]
    assert [phase["phase"] for phase in phases] == [
        "pass_001",
        "pass_002",
        "pass_003",
        "inspection",
    ]
    assert run_manifest["result_status"] == "PASS"


def test_round1_winner_rule_uses_resources_for_practical_tie() -> None:
    contract = _contract()
    rows = []
    for workers, wall, rss in (
        (4, 108.0, 2.0),
        (8, 100.0, 4.0),
        (12, 101.0, 3.0),
        (16, 120.0, 2.5),
        (20, 130.0, 2.5),
        (24, 140.0, 2.5),
    ):
        rows.append(
            {
                "workers": workers,
                "wall_seconds": wall,
                "peak_process_tree_rss_bytes": rss,
                "peak_watched_run_bytes": 1.0,
                "sampled_process_tree_cpu_seconds": wall,
                "canonical_reducer_stall_seconds": 0.0,
            }
        )
    winner, reason, ranking = s1m2.select_round1_winner(
        rows, contract["round1"]["winner_rule"]
    )
    assert ranking[0]["workers"] == 8
    assert winner == 4
    assert reason == "practical_tie_resource_rule"


def test_compact_round1_attestations_select_winner_without_run_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _contract()
    plan = s1m2.build_round1_plan(contract, identity=IDENTITY)

    def fake_audit(
        _plan: object,
        job: dict[str, object],
        _contract_value: object,
        *,
        repo_root: Path,
    ) -> dict[str, object]:
        del repo_root
        workers = int(job["workers"])
        return {
            "valid": True,
            "failures": [],
            "artifact_audit": {
                "run_dir": "remote-only-not-downloaded",
                "metrics": {
                    "wall_seconds": 80.0 if workers == 8 else 100.0 + workers,
                    "peak_process_tree_rss_bytes": 1024 * workers,
                    "peak_watched_run_bytes": 2048 * workers,
                    "sampled_process_tree_cpu_seconds": 50.0 * workers,
                    "host_memory_bytes": 1024**4,
                    "filesystem_free_bytes_end": 30 * 1024**3,
                },
            },
        }

    monkeypatch.setattr(s1m2, "audit_job", fake_audit)
    attestations = [
        s1m2.build_round1_attestation(
            plan, job, contract, repo_root=Path(".")
        )
        for job in plan["jobs"]
    ]
    assert all(item["valid"] for item in attestations)
    assert all(item["plan_identity"]["plan_sha256"] == plan["plan_sha256"] for item in attestations)
    assert all(
        item["production_contract_identity"]["sha256"]
        == plan["production_contract_sha256"]
        for item in attestations
    )
    result = s1m2.aggregate_round1_attestations(plan, contract, attestations)
    assert result["ROUND1_STATUS"] == "PASS"
    assert result["WINNER_WORKERS"] == 8
    assert result["WINNER_REASON"] == "direct_wall_winner"

    tampered = copy.deepcopy(attestations)
    tampered[0]["plan_identity"]["plan_sha256"] = "0" * 64
    assert s1m2.aggregate_round1_attestations(
        plan, contract, tampered
    )["ROUND1_STATUS"] == "FAIL"


def test_round1_aggregator_fails_closed_on_filesystem_headroom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _contract()
    plan = s1m2.build_round1_plan(contract, identity=IDENTITY)

    def fake_audit(
        _plan: object,
        job: dict[str, object],
        _contract_value: object,
        *,
        repo_root: Path,
    ) -> dict[str, object]:
        workers = int(job["workers"])
        return {
            "valid": True,
            "failures": [],
            "artifact_audit": {
                "run_dir": str(repo_root / "missing-test-run-dir"),
                "metrics": {
                    "wall_seconds": 100.0 + workers,
                    "peak_process_tree_rss_bytes": 1024,
                    "peak_watched_run_bytes": 1024,
                    "sampled_process_tree_cpu_seconds": 50.0,
                    "sampled_process_tree_read_bytes": 10,
                    "sampled_process_tree_write_bytes": 20,
                    "host_memory_bytes": 32768,
                    "filesystem_free_bytes_end": 1,
                },
            },
        }

    monkeypatch.setattr(s1m2, "audit_job", fake_audit)
    result = s1m2.aggregate_round1(plan, contract, repo_root=Path("."))
    assert result["ROUND1_STATUS"] == "FAIL"
    assert all(
        "filesystem free-space safety gate failed" in row["failures"]
        for row in result["jobs"]
    )


def test_round2_and_final_plans_use_round3_retained_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _contract()
    _mock_bundle_details(monkeypatch)
    round2 = s1m2.build_round2_plan(contract, identity=IDENTITY)
    s1m2._validate_plan(round2, contract)
    assert len(round2["jobs"]) == 6
    assert {job["workers"] for job in round2["jobs"]} == {12, 16, 24}
    assert [job["host_role"] for job in round2["jobs"]] == list(
        s1m2.CORE_HOST_ROLES
    )
    assert len({job["host_role"] for job in round2["jobs"]}) == 6
    assert round2["launch_mode"] == "six_way_parallel"
    assert [
        (job["cell_id"], job["workload_id"]) for job in round2["jobs"]
    ] == [
        (item["cell_id"], item["workload"])
        for item in contract["round2"]["jobs"]
    ]

    monkeypatch.setattr(s1m2, "validate_round3_closure", lambda *args, **kwargs: None)
    final = s1m2.build_final_plan(
        contract, _round2_result(), _round3_closure(), identity=IDENTITY
    )
    s1m2._validate_plan(final, contract)
    assert len(final["jobs"]) == 6
    assert {job["workload_id"] for job in final["jobs"]} == {"full"}
    assert {job["workers"] for job in final["jobs"]} == {12}
    assert final["FULL_M0_PROCESS_RUNNING"] == "NO"
    assert [job["host_role"] for job in final["jobs"]] == [
        contract["full_host_role_by_cell"][cell["cell_id"]]
        for cell in contract["cells"]
    ]


def test_round2_result_is_machine_readable(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _contract()
    _mock_bundle_details(monkeypatch)
    plan = s1m2.build_round2_plan(contract, identity=IDENTITY)
    result = s1m2.aggregate_round2_attestations(
        plan, contract, _valid_round2_attestations(plan, contract)
    )
    assert result["ROUND2_STATUS"] == "PASS"
    assert result["WINNER_WORKERS"] == 12
    assert result["W20_REQUIRED"] == "no"
    assert len(result["jobs"]) == 6
    assert all(row["valid"] for row in result["jobs"])


@pytest.mark.parametrize("target_workload", ["representative", "stress"])
def test_round2_storage_gate_fails_closed_on_actual_peak_for_all_job_classes(
    monkeypatch: pytest.MonkeyPatch,
    target_workload: str,
) -> None:
    contract = _contract()
    _mock_bundle_details(monkeypatch)
    plan = s1m2.build_round2_plan(contract, identity=IDENTITY)
    storage_max = int(contract["gates"]["storage_max_bytes"])
    attestations = _valid_round2_attestations(plan, contract)
    targets = [
        item for item in attestations if item["workload"] == target_workload
    ]
    for target in targets:
        target["peak_watched_run_bytes"] = storage_max + 1
    result = s1m2.aggregate_round2_attestations(plan, contract, attestations)
    assert result["ROUND2_STATUS"] == "FAIL"
    failed = [
        row for row in result["jobs"] if row["workload"] == target_workload
    ]
    assert len(failed) == 3
    assert all("storage safety gate failed" in row["failures"] for row in failed)


def test_bounded_script_neutral_gate_covers_all_three_conditions() -> None:
    contract = _contract()
    rows = []
    for cell in contract["cells"]:
        rows.append(
            {
                "cell_id": cell["cell_id"],
                "scientific_artifacts": {
                    name: {"bytes": 1, "sha256": f"same-{name}"}
                    for name in s1m2.SCRIPT_NEUTRAL_ARTIFACTS
                },
            }
        )
    gate = s1m2._script_neutral_bounded_gate(rows)
    assert gate["status"] == "PASS"
    assert [row["condition"] for row in gate["comparisons"]] == [
        "surface_word", "legacy_joined", "continuous"
    ]

    rows[0]["scientific_artifacts"]["piece_inventory.tsv"] = {
        "bytes": 2,
        "sha256": "different",
    }
    assert s1m2._script_neutral_bounded_gate(rows)["status"] == "FAIL"


def test_final_plan_fails_closed_without_round3_closure() -> None:
    contract = _contract()
    with pytest.raises(ValueError, match="Unsupported Round 3 closure"):
        s1m2.build_final_plan(contract, _round2_result(), {}, identity=IDENTITY)


def test_cloud_registry_contains_all_prevm_planned_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _contract()
    _mock_bundle_details(monkeypatch)
    round1 = s1m2.build_round1_plan(contract, identity=IDENTITY)
    round2 = s1m2.build_round2_plan(contract, identity=IDENTITY)
    monkeypatch.setattr(s1m2, "validate_round3_closure", lambda *args, **kwargs: None)
    final = s1m2.build_final_plan(
        contract, _round2_result(), _round3_closure(), identity=IDENTITY
    )
    registry = tomllib.loads(
        Path("configs/cloud/experiment_registry.toml").read_text(encoding="utf-8")
    )
    assert registry["s1m2_prevm"]["production_contract"] == (
        s1m2.CONTRACT_PATH.as_posix()
    )
    planned = registry["s1m2_prevm"]["planned_runs"]
    registry_ids = {row["run_id"] for row in planned}
    generated_ids = {
        job["run_id"]
        for plan in (round1, round2, final)
        for job in plan["jobs"]
    }
    assert len(planned) == 18
    assert registry_ids == generated_ids
    assert registry["s1m2_prevm"]["round1_status"] == (
        "MANUALLY_TERMINATED_AFTER_DIAGNOSTIC_CONVERGENCE"
    )
    assert registry["s1m2_prevm"]["full_m0_process_running"] is False
    assert registry["s1m2_prevm"]["launch_mode"] == "SIX_WAY_PARALLEL"
    assert registry["s1m2_prevm"]["host_roles"] == list(s1m2.CORE_HOST_ROLES)
    expected_hosts = {
        "round1": list(s1m2.CORE_HOST_ROLES),
        "round2": list(s1m2.CORE_HOST_ROLES),
        "full": [
            contract["full_host_role_by_cell"][cell["cell_id"]]
            for cell in contract["cells"]
        ],
    }
    for phase in ("round1", "round2", "full"):
        rows = [row for row in planned if row["phase"] == phase]
        assert [row["host_role"] for row in rows] == expected_hosts[phase]
