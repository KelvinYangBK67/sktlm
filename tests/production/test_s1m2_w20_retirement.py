from __future__ import annotations

from pathlib import Path

import pytest

from sktlm.production import s1m2


IDENTITY = {
    "git_sha": "a" * 40,
    "branch": "exp/s1m2-reusable-pieces",
    "dirty_worktree": False,
}


def _contract() -> dict:
    return s1m2.load_contract(
        repo_root=Path("."),
        verify_files=False,
    )


def test_full_rejects_retired_w20_winner() -> None:
    contract = _contract()
    round2 = {
        "schema_version": s1m2.ROUND2_SCHEMA,
        "plan_sha256": "c" * 64,
        "production_contract_sha256": s1m2._canonical_sha256(contract),
        "ROUND2_STATUS": "PASS",
        "WINNER_WORKERS": 20,
        "jobs": [{} for _ in range(6)],
        "candidate_ranking": [
            {"workers": 20, "eligible": True},
        ],
    }

    with pytest.raises(ValueError, match="primary worker candidate"):
        s1m2.build_final_plan(
            contract,
            round2,
            identity=IDENTITY,
            repo_root=Path("."),
        )


def _synthetic_round2_plan(contract: dict) -> dict:
    jobs = []
    host_index = 1

    for workload in ("representative", "stress"):
        for workers in s1m2.ROUND2_PRIMARY_WORKERS:
            job_id = f"synthetic_{workload}_w{workers}"
            jobs.append(
                {
                    "job_id": job_id,
                    "host_role": f"core-{host_index:02d}",
                    "workload_id": workload,
                    "workers": workers,
                    "execution_bundle_plan": f"synthetic/{workload}",
                    "execution_bundle_plan_sha256": "b" * 64,
                    "execution_bundle_materialization_sha256": "d" * 64,
                }
            )
            host_index += 1

    return {
        "schema_version": s1m2.PLAN_SCHEMA,
        "plan_type": "round2",
        "plan_sha256": "e" * 64,
        "production_contract_sha256": s1m2._canonical_sha256(contract),
        "contract_path": s1m2.CONTRACT_PATH.as_posix(),
        "git_sha": "a" * 40,
        "branch": "exp/s1m2-reusable-pieces",
        "jobs": jobs,
    }


def _synthetic_attestations(plan: dict, contract: dict) -> list[dict]:
    attestations = []

    for job in plan["jobs"]:
        attestations.append(
            {
                "schema_version": s1m2.ROUND2_ATTESTATION_SCHEMA,
                "job_id": job["job_id"],
                "host_role": job["host_role"],
                "workload": job["workload_id"],
                "workers": job["workers"],
                "git_sha": plan["git_sha"],
                "execution_bundle_plan": job["execution_bundle_plan"],
                "execution_bundle_plan_sha256": (
                    job["execution_bundle_plan_sha256"]
                ),
                "execution_bundle_materialization_sha256": (
                    job["execution_bundle_materialization_sha256"]
                ),
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
                "valid": True,
                "failures": [],
                "wall_seconds": 100.0,
                "peak_process_tree_rss_bytes": 1_000_000,
                "peak_watched_run_bytes": 1_000_000,
                "sampled_process_tree_cpu_seconds": 10.0,
                "canonical_reducer_stall_seconds": 1.0,
                "bundle_true_inflight": 1,
                "bundle_ready_shard": 1,
                "completed_passes": contract["passes"],
                "candidate_overflow": 0,
                "host_memory_bytes": 100_000_000_000,
                "filesystem_free_bytes_end": 100_000_000_000,
            }
        )

    return attestations


def test_round2_worker_disagreement_fails_closed_without_w20(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _contract()
    plan = _synthetic_round2_plan(contract)
    attestations = _synthetic_attestations(plan, contract)

    monkeypatch.setattr(
        s1m2,
        "_validate_plan",
        lambda plan, contract: None,
    )

    def forced_preference(
        rows: list[dict],
        practical: float,
    ) -> tuple[int, str, list]:
        workload = rows[0]["workload"]
        selected = 12 if workload == "representative" else 16
        return selected, "forced_test_preference", []

    monkeypatch.setattr(
        s1m2,
        "_round2_workload_preference",
        forced_preference,
    )

    result = s1m2.aggregate_round2_attestations(
        plan,
        contract,
        attestations,
    )

    assert result["ROUND2_STATUS"] == "FAIL"
    assert result["WINNER_WORKERS"] is None
    assert (
        result["WINNER_REASON"]
        == "representative_and_stress_prefer_different_workers"
    )
    assert result["W20_REQUIRED"] == "no"
    assert "w20_followup_jobs" not in result
