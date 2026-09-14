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
HISTORICAL_CONTRACT_SHA256 = (
    "f8684597c061f6608569042e69fa8a0fed9badd14a413976abcd12a8d62cd92d"
)
OTHER_HISTORICAL_CONTRACT_SHA256 = "2" * 64


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


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _round3_evidence_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    contract: dict,
) -> tuple[Path, dict, dict]:
    round2_path = tmp_path / "round2.json"
    round2 = _round2_fail(contract)
    real_path = tmp_path / "raw520.json"
    worker_path = tmp_path / "workers.json"
    tail_paths = tuple(
        tmp_path / f"raw{raw}.json" for raw in (1002, 1410, 1841, 2484)
    )
    _write_json(round2_path, round2)
    _write_json(
        real_path,
        {
            "status": "PASS",
            "gate": "REAL_OFFENDER_COMPACT_VS_LEGACY_EXACTNESS",
            "case": {
                "raw_internal_matches": 520,
                "retained_internal_matches": 520,
            },
            "compact": {
                "support_truncation_tokens": 0,
                "shared_batch_fallbacks": 0,
            },
            "scientific_equivalence": {"posterior": "PASS"},
        },
    )
    _write_json(
        worker_path,
        {
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
        },
    )
    for raw, path in zip((1002, 1410, 1841, 2484), tail_paths, strict=True):
        _write_json(
            path,
            {
                "status": "PASS",
                "gate": "COMPACT_PRODUCTION_PASS1_TAIL",
                "case": {"raw": raw, "retained": raw},
                "compact": {
                    "support_truncation_tokens": 0,
                    "shared_batch_fallbacks": 0,
                },
                "posterior_mass": 1.0,
            },
        )

    # Commit ancestry is an external Git boundary already covered by the Round 3
    # closure tests; retain every closure field and artifact check exercised here.
    monkeypatch.setattr(s1m2, "_git_is_ancestor", lambda *args: True)
    closure = s1m2.build_round3_closure(
        contract,
        round2_path,
        real_offender_path=real_path,
        worker_equivalence_path=worker_path,
        tail_paths=tail_paths,
        repo_root=tmp_path,
    )
    return round2_path, round2, closure


def _rebind_historical_contract(
    round2_path: Path,
    round2: dict,
    closure: dict,
    historical_contract_sha256: str,
) -> tuple[dict, dict]:
    rebound_round2 = copy.deepcopy(round2)
    rebound_round2["production_contract_sha256"] = historical_contract_sha256
    _write_json(round2_path, rebound_round2)

    rebound_closure = copy.deepcopy(closure)
    rebound_closure["production_contract_sha256"] = historical_contract_sha256
    rebound_closure["round2_result_sha256"] = s1m2._sha256(round2_path)
    rebound_closure["round2_payload_sha256"] = s1m2._canonical_sha256(
        rebound_round2
    )
    rebound_closure["closure_sha256"] = s1m2._canonical_sha256(
        {
            key: value
            for key, value in rebound_closure.items()
            if key != "closure_sha256"
        }
    )
    return rebound_round2, rebound_closure


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


def test_historical_round2_uses_explicit_exact_contract_identity() -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    round2 = _round2_fail(contract)
    round2["production_contract_sha256"] = HISTORICAL_CONTRACT_SHA256

    s1m2._validate_historical_round2(round2, HISTORICAL_CONTRACT_SHA256)
    with pytest.raises(ValueError, match="expected historical production contract"):
        s1m2._validate_historical_round2(
            round2, OTHER_HISTORICAL_CONTRACT_SHA256
        )


def test_round3_validation_preserves_historical_contract_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current_contract = s1m2.load_contract(
        repo_root=Path("."), verify_files=False
    )
    round2_path, round2, closure = _round3_evidence_fixture(
        monkeypatch, tmp_path, current_contract
    )
    round2, closure = _rebind_historical_contract(
        round2_path,
        round2,
        closure,
        HISTORICAL_CONTRACT_SHA256,
    )

    assert s1m2._canonical_sha256(current_contract) != HISTORICAL_CONTRACT_SHA256
    s1m2.validate_round3_closure(
        closure,
        current_contract,
        round2,
        repo_root=tmp_path,
    )


def test_round3_validation_rejects_historical_round2_closure_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current_contract = s1m2.load_contract(
        repo_root=Path("."), verify_files=False
    )
    round2_path, round2, closure = _round3_evidence_fixture(
        monkeypatch, tmp_path, current_contract
    )
    round2, closure = _rebind_historical_contract(
        round2_path,
        round2,
        closure,
        HISTORICAL_CONTRACT_SHA256,
    )
    closure["production_contract_sha256"] = OTHER_HISTORICAL_CONTRACT_SHA256
    closure["closure_sha256"] = s1m2._canonical_sha256(
        {key: value for key, value in closure.items() if key != "closure_sha256"}
    )

    with pytest.raises(ValueError, match="expected historical production contract"):
        s1m2.validate_round3_closure(
            closure,
            current_contract,
            round2,
            repo_root=tmp_path,
        )


def test_round3_validation_rejects_noncanonical_historical_contract_sha(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current_contract = s1m2.load_contract(
        repo_root=Path("."), verify_files=False
    )
    _, round2, closure = _round3_evidence_fixture(
        monkeypatch, tmp_path, current_contract
    )
    closure["production_contract_sha256"] = "A" * 64
    closure["closure_sha256"] = s1m2._canonical_sha256(
        {key: value for key, value in closure.items() if key != "closure_sha256"}
    )

    with pytest.raises(ValueError, match="must be a lowercase SHA-256"):
        s1m2.validate_round3_closure(
            closure,
            current_contract,
            round2,
            repo_root=tmp_path,
        )


def test_round3_builder_requires_round2_to_bind_current_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current_contract = s1m2.load_contract(
        repo_root=Path("."), verify_files=False
    )
    round2_path, round2, closure = _round3_evidence_fixture(
        monkeypatch, tmp_path, current_contract
    )
    round2, _ = _rebind_historical_contract(
        round2_path,
        round2,
        closure,
        HISTORICAL_CONTRACT_SHA256,
    )

    evidence = closure["evidence"]
    with pytest.raises(ValueError, match="expected historical production contract"):
        s1m2.build_round3_closure(
            current_contract,
            round2_path,
            real_offender_path=Path(evidence["real_offender_exactness"]["path"]),
            worker_equivalence_path=Path(
                evidence["local_worker_equivalence"]["path"]
            ),
            tail_paths=tuple(
                Path(entry["path"]) for entry in evidence["pressure_tail"]
            ),
            repo_root=tmp_path,
        )


def test_final_plan_binds_current_not_historical_contract_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current_contract = s1m2.load_contract(
        repo_root=Path("."), verify_files=False
    )
    round2_path, round2, closure = _round3_evidence_fixture(
        monkeypatch, tmp_path, current_contract
    )
    round2, closure = _rebind_historical_contract(
        round2_path,
        round2,
        closure,
        HISTORICAL_CONTRACT_SHA256,
    )
    monkeypatch.setattr(
        s1m2,
        "_bundle_plan_details",
        lambda _root, declaration, *_args, **_kwargs: {
            "path": declaration["execution_bundle_plan"],
            "plan_sha256": declaration["execution_bundle_plan_sha256"],
            "materialization_sha256": "d" * 64,
        },
    )

    plan = s1m2.build_final_plan(
        current_contract,
        round2,
        closure,
        identity=IDENTITY,
        repo_root=tmp_path,
        selected_cell_ids=["s1m2_m0_devanagari_continuous"],
    )

    current_contract_sha256 = s1m2._canonical_sha256(current_contract)
    assert plan["production_contract_sha256"] == current_contract_sha256
    assert plan["production_contract_sha256"] != HISTORICAL_CONTRACT_SHA256
    assert closure["production_contract_sha256"] == HISTORICAL_CONTRACT_SHA256


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
