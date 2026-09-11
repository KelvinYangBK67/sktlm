from __future__ import annotations

import copy
from pathlib import Path

import pytest

from sktlm.production import s1m2


IDENTITY = {
    "git_sha": "a" * 40,
    "branch": "exp/s1m2-reusable-pieces",
    "dirty_worktree": False,
}


def _round2_fail(contract: dict) -> dict:
    return {
        "schema_version": s1m2.ROUND2_SCHEMA,
        "plan_sha256": "c" * 64,
        "production_contract_sha256": s1m2._canonical_sha256(contract),
        "ROUND2_STATUS": "FAIL",
        "WINNER_WORKERS": None,
        "jobs": [{"candidate_overflow": 1} for _ in range(6)],
    }


def _closure() -> dict:
    return {
        "closure_sha256": "e" * 64,
        "round2_result_sha256": "f" * 64,
        "retained_workers": 12,
    }


def test_full_plan_binds_bundle_only_to_devanagari_continuous(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = s1m2.load_contract(
        repo_root=Path("."),
        verify_files=False,
    )

    def fake_bundle_details(
        repo_root: Path,
        declaration: dict,
        workload: dict,
        scientific_config: dict,
    ) -> dict[str, str]:
        assert repo_root == tmp_path.resolve()
        assert declaration["execution_bundle_plan"] == (
            s1m2.FULL_EXECUTION_BUNDLE_PLAN
        )
        assert declaration["execution_bundle_plan_sha256"] == (
            s1m2.FULL_EXECUTION_BUNDLE_PLAN_SHA256
        )
        assert workload == contract["workloads"]["full"]
        assert scientific_config == contract["scientific_config"]
        return {
            "path": s1m2.FULL_EXECUTION_BUNDLE_PLAN,
            "plan_sha256": s1m2.FULL_EXECUTION_BUNDLE_PLAN_SHA256,
            "materialization_sha256": "d" * 64,
        }

    monkeypatch.setattr(s1m2, "_bundle_plan_details", fake_bundle_details)
    monkeypatch.setattr(s1m2, "validate_round3_closure", lambda *args, **kwargs: None)

    plan = s1m2.build_final_plan(
        contract,
        _round2_fail(contract),
        _closure(),
        identity=IDENTITY,
        repo_root=tmp_path,
    )
    s1m2._validate_plan(plan, contract)

    bundle_jobs = [
        job
        for job in plan["jobs"]
        if job.get("execution_bundle_plan") is not None
    ]

    assert len(bundle_jobs) == 1
    job = bundle_jobs[0]

    assert job["cell_id"] == s1m2.FULL_EXECUTION_BUNDLE_CELL_ID
    assert job["execution_bundle_plan"] == s1m2.FULL_EXECUTION_BUNDLE_PLAN
    assert (
        job["execution_bundle_plan_sha256"]
        == s1m2.FULL_EXECUTION_BUNDLE_PLAN_SHA256
    )
    assert job["execution_bundle_materialization_sha256"] == "d" * 64

    command = job["training_command"]
    index = command.index("--execution-bundle-plan")
    assert command[index + 1] == s1m2.FULL_EXECUTION_BUNDLE_PLAN

    for other in plan["jobs"]:
        if other["cell_id"] != s1m2.FULL_EXECUTION_BUNDLE_CELL_ID:
            assert other.get("execution_bundle_plan") is None
            assert "--execution-bundle-plan" not in other["training_command"]


def test_full_plan_rejects_missing_required_bundle_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = s1m2.load_contract(
        repo_root=Path("."),
        verify_files=False,
    )

    monkeypatch.setattr(
        s1m2,
        "_bundle_plan_details",
        lambda *args, **kwargs: {
            "path": s1m2.FULL_EXECUTION_BUNDLE_PLAN,
            "plan_sha256": s1m2.FULL_EXECUTION_BUNDLE_PLAN_SHA256,
            "materialization_sha256": "d" * 64,
        },
    )
    monkeypatch.setattr(s1m2, "validate_round3_closure", lambda *args, **kwargs: None)

    plan = s1m2.build_final_plan(
        contract,
        _round2_fail(contract),
        _closure(),
        identity=IDENTITY,
        repo_root=tmp_path,
    )

    target = next(
        job
        for job in plan["jobs"]
        if job["cell_id"] == s1m2.FULL_EXECUTION_BUNDLE_CELL_ID
    )
    target.pop("execution_bundle_plan")
    target.pop("execution_bundle_plan_sha256")
    target.pop("execution_bundle_materialization_sha256")
    target["training_command"] = s1m2._training_command(target)

    plan["plan_sha256"] = s1m2._canonical_sha256(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )

    with pytest.raises(ValueError, match="invalid execution bundle plan"):
        s1m2._validate_plan(plan, contract)
