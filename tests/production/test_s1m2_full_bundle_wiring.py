from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sktlm.production import s1m2


IDENTITY = {
    "git_sha": "a" * 40,
    "branch": "exp/s1m2-reusable-pieces",
    "dirty_worktree": False,
}

FOUR_CELL_SCOPE = (
    "s1m2_m0_prime_iast_continuous",
    "s1m2_m0_devanagari_continuous",
    "s1m2_m0_devanagari_surface_word",
    "s1m2_m0_devanagari_legacy_joined",
)


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


def _install_bundle_loader(
    monkeypatch: pytest.MonkeyPatch,
    contract: dict,
    *,
    calls: list[str] | None = None,
    rejected_paths: set[str] | None = None,
) -> None:
    rejected = rejected_paths or set()

    def load(
        _repo_root: Path,
        declaration: dict,
        *_args: object,
        **_kwargs: object,
    ) -> dict[str, str]:
        path = declaration["execution_bundle_plan"]
        if calls is not None:
            calls.append(path)
        if path in rejected:
            raise ValueError(f"invalid authoritative bundle: {path}")
        return {
            "path": path,
            "plan_sha256": declaration["execution_bundle_plan_sha256"],
            "materialization_sha256": "d" * 64,
        }

    monkeypatch.setattr(s1m2, "_bundle_plan_details", load)
    monkeypatch.setattr(
        s1m2, "validate_round3_closure", lambda *args, **kwargs: None
    )


def test_full_plan_binds_bundles_to_both_continuous_cells(
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
        *,
        manifest: str,
    ) -> dict[str, str]:
        assert repo_root == tmp_path.resolve()
        path = declaration["execution_bundle_plan"]
        expected_by_path = {
            spec["execution_bundle_plan"]: spec
            for spec in contract["full_execution_bundle_plans"].values()
        }
        assert path in expected_by_path
        spec = expected_by_path[path]
        assert declaration["execution_bundle_plan_sha256"] == (
            spec["execution_bundle_plan_sha256"]
        )
        assert declaration["script"] == spec["script"]
        assert declaration["condition"] == spec["condition"]
        assert workload == contract["workloads"]["full"]
        assert scientific_config == contract["scientific_config"]
        assert manifest in {
            contract["corpus"]["m0_manifest"],
            contract["corpus"]["m0_prime_manifest"],
        }
        return {
            "path": path,
            "plan_sha256": spec["execution_bundle_plan_sha256"],
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
    assert plan["execution_cell_ids"] == [
        cell["cell_id"] for cell in contract["cells"]
    ]
    assert plan["FULL_EXECUTION_SCOPE"] == "ALL_SIX"
    assert plan["FULL_M0_SIX_CELL_CONFIG"] == "FROZEN"

    expected_host_roles = tuple(
        contract["full_host_role_by_cell"][cell["cell_id"]]
        for cell in contract["cells"]
    )
    assert tuple(job["host_role"] for job in plan["jobs"]) == expected_host_roles

    wrong_host_plan = copy.deepcopy(plan)
    wrong_host_plan["jobs"][2]["host_role"] = "core-03"
    wrong_host_plan["plan_sha256"] = s1m2._canonical_sha256(
        {
            key: value
            for key, value in wrong_host_plan.items()
            if key != "plan_sha256"
        }
    )
    with pytest.raises(ValueError, match="deployed host mapping"):
        s1m2._validate_plan(wrong_host_plan, contract)

    bundle_jobs = [
        job
        for job in plan["jobs"]
        if job.get("execution_bundle_plan") is not None
    ]

    assert len(bundle_jobs) == len(contract["full_execution_bundle_plans"])
    expected = contract["full_execution_bundle_plans"]
    assert {job["cell_id"] for job in bundle_jobs} == set(expected)

    for job in bundle_jobs:
        spec = expected[job["cell_id"]]
        assert job["execution_bundle_plan"] == spec["execution_bundle_plan"]
        assert (
            job["execution_bundle_plan_sha256"]
            == spec["execution_bundle_plan_sha256"]
        )
        assert job["execution_bundle_materialization_sha256"] == "d" * 64
        command = job["training_command"]
        index = command.index("--execution-bundle-plan")
        assert command[index + 1] == spec["execution_bundle_plan"]

    for other in plan["jobs"]:
        if other["cell_id"] not in expected:
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
        lambda _repo_root, declaration, *_args, **_kwargs: {
            "path": declaration["execution_bundle_plan"],
            "plan_sha256": declaration["execution_bundle_plan_sha256"],
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
        if job["cell_id"] == "s1m2_m0_devanagari_continuous"
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


def test_explicit_four_cell_scope_is_canonical_and_skips_unselected_bundles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = copy.deepcopy(
        s1m2.load_contract(repo_root=Path("."), verify_files=False)
    )
    unselected = {
        "s1m2_m0_iast_surface_word",
        "s1m2_m0_iast_legacy_joined",
    }
    rejected_paths = set()
    for cell_id in unselected:
        path = f"missing/legacy-v1/{cell_id}"
        contract["full_execution_bundle_plans"][cell_id][
            "execution_bundle_plan"
        ] = path
        rejected_paths.add(path)
    calls: list[str] = []
    _install_bundle_loader(
        monkeypatch,
        contract,
        calls=calls,
        rejected_paths=rejected_paths,
    )

    plan = s1m2.build_final_plan(
        contract,
        _round2_fail(contract),
        _closure(),
        identity=IDENTITY,
        repo_root=tmp_path,
        selected_cell_ids=FOUR_CELL_SCOPE,
    )
    s1m2._validate_plan(plan, contract)

    expected = [
        cell["cell_id"]
        for cell in contract["cells"]
        if cell["cell_id"] in FOUR_CELL_SCOPE
    ]
    assert plan["execution_cell_ids"] == expected
    assert [job["cell_id"] for job in plan["jobs"]] == expected
    assert [job["host_role"] for job in plan["jobs"]] == [
        contract["full_host_role_by_cell"][cell_id] for cell_id in expected
    ]
    assert plan["FULL_EXECUTION_SCOPE"] == "EXPLICIT_SUBSET"
    assert plan["FULL_M0_SIX_CELL_CONFIG"] == "FROZEN"
    assert len(plan["jobs"]) == len(calls) == 4
    assert not rejected_paths.intersection(calls)


def test_selected_invalid_bundle_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = copy.deepcopy(
        s1m2.load_contract(repo_root=Path("."), verify_files=False)
    )
    selected = "s1m2_m0_devanagari_continuous"
    invalid_path = "missing/legacy-v1/selected-deva-continuous"
    contract["full_execution_bundle_plans"][selected][
        "execution_bundle_plan"
    ] = invalid_path
    _install_bundle_loader(
        monkeypatch,
        contract,
        rejected_paths={invalid_path},
    )

    with pytest.raises(ValueError, match="invalid authoritative bundle"):
        s1m2.build_final_plan(
            contract,
            _round2_fail(contract),
            _closure(),
            identity=IDENTITY,
            repo_root=tmp_path,
            selected_cell_ids=[selected],
        )


@pytest.mark.parametrize(
    ("selected", "message"),
    (
        ([], "must not be empty"),
        (["unknown-cell"], "Unknown Full execution cell IDs"),
        (
            [
                "s1m2_m0_devanagari_continuous",
                "s1m2_m0_devanagari_continuous",
            ],
            "contains duplicates",
        ),
    ),
)
def test_explicit_scope_rejects_empty_unknown_and_duplicate_cells(
    monkeypatch: pytest.MonkeyPatch,
    selected: list[str],
    message: str,
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    _install_bundle_loader(monkeypatch, contract)
    with pytest.raises(ValueError, match=message):
        s1m2.build_final_plan(
            contract,
            _round2_fail(contract),
            _closure(),
            identity=IDENTITY,
            selected_cell_ids=selected,
        )


def test_plan_final_cli_canonicalizes_repeated_cell_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    _install_bundle_loader(monkeypatch, contract)
    monkeypatch.setattr(s1m2, "load_contract", lambda *args, **kwargs: contract)
    monkeypatch.setattr(s1m2, "git_identity", lambda _root: IDENTITY)
    round2_path = tmp_path / "round2.json"
    closure_path = tmp_path / "closure.json"
    output_path = tmp_path / "final.json"
    round2_path.write_text(json.dumps(_round2_fail(contract)), encoding="utf-8")
    closure_path.write_text(json.dumps(_closure()), encoding="utf-8")

    argv = [
        "--repo-root",
        str(tmp_path),
        "plan-final",
        "--round2-result",
        round2_path.name,
        "--round3-closure",
        closure_path.name,
        "--output",
        output_path.name,
    ]
    for cell_id in reversed(FOUR_CELL_SCOPE):
        argv.extend(("--cell-id", cell_id))
    s1m2.main(argv)

    plan = json.loads(output_path.read_text(encoding="utf-8"))
    expected = [
        cell["cell_id"]
        for cell in contract["cells"]
        if cell["cell_id"] in FOUR_CELL_SCOPE
    ]
    assert plan["execution_cell_ids"] == expected
    assert [job["cell_id"] for job in plan["jobs"]] == expected


def test_four_cell_authorization_is_exactly_scope_bound(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    _install_bundle_loader(monkeypatch, contract)
    four = s1m2.build_final_plan(
        contract,
        _round2_fail(contract),
        _closure(),
        identity=IDENTITY,
        repo_root=tmp_path,
        selected_cell_ids=FOUR_CELL_SCOPE,
    )
    six = s1m2.build_final_plan(
        contract,
        _round2_fail(contract),
        _closure(),
        identity=IDENTITY,
        repo_root=tmp_path,
    )
    authorization = s1m2.build_full_authorization(
        four, contract, identity=IDENTITY
    )
    s1m2._validate_full_authorization(authorization, four, contract)
    assert authorization["cell_ids"] == four["execution_cell_ids"]

    six_authorization = s1m2.build_full_authorization(
        six, contract, identity=IDENTITY
    )
    with pytest.raises(ValueError, match="plan_sha256"):
        s1m2._validate_full_authorization(six_authorization, four, contract)

    for cell_ids in (
        authorization["cell_ids"][:-1],
        [*authorization["cell_ids"], "s1m2_m0_iast_surface_word"],
    ):
        changed = {**authorization, "cell_ids": cell_ids}
        changed["authorization_sha256"] = s1m2._canonical_sha256(
            {
                key: value
                for key, value in changed.items()
                if key != "authorization_sha256"
            }
        )
        with pytest.raises(ValueError, match="cell_ids"):
            s1m2._validate_full_authorization(changed, four, contract)

    wrong_plan = {**authorization, "plan_sha256": "0" * 64}
    wrong_plan["authorization_sha256"] = s1m2._canonical_sha256(
        {
            key: value
            for key, value in wrong_plan.items()
            if key != "authorization_sha256"
        }
    )
    with pytest.raises(ValueError, match="plan_sha256"):
        s1m2._validate_full_authorization(wrong_plan, four, contract)


def test_plan_validation_rejects_job_outside_execution_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    _install_bundle_loader(monkeypatch, contract)
    four = s1m2.build_final_plan(
        contract,
        _round2_fail(contract),
        _closure(),
        identity=IDENTITY,
        repo_root=tmp_path,
        selected_cell_ids=FOUR_CELL_SCOPE,
    )
    six = s1m2.build_final_plan(
        contract,
        _round2_fail(contract),
        _closure(),
        identity=IDENTITY,
        repo_root=tmp_path,
    )
    tampered = copy.deepcopy(four)
    tampered["jobs"].append(copy.deepcopy(six["jobs"][0]))
    tampered["plan_sha256"] = s1m2._canonical_sha256(
        {key: value for key, value in tampered.items() if key != "plan_sha256"}
    )
    with pytest.raises(ValueError, match="jobs differ from its execution scope"):
        s1m2._validate_plan(tampered, contract)
