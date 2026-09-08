from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts.cloud import sktlm_bridge as bridge
from sktlm.cloud.contracts import ContractError, load_experiment_contract


def contract_payload() -> dict[str, object]:
    return {
        "schema_version": "sktlm-cloud-experiment-contract/v1",
        "contract_id": "fixture-v1",
        "branch": "exp/fixture",
        "deployment": {
            "mode": "git_bundle",
            "require_published_head": True,
        },
        "input_sets": [
            {
                "input_id": "frozen-input",
                "paths": ["data/input", "artifacts/input/manifest.json"],
                "validator_argv": ["python", "scripts/verify.py"],
            }
        ],
        "remote_run_root": "artifacts/runs",
        "optional_metrics_root": "artifacts/metrics",
        "audit": {
            "entrypoint_argv": [
                "python",
                "scripts/audit.py",
                "--artifact-dir",
                "{artifact_dir}",
            ],
            "inventory_key": "artifacts",
        },
        "collection_profiles": {
            "report": ["summary.json"],
            "scientific": ["summary.json", "result.tsv"],
            "full": None,
        },
        "required_audited_files": ["summary.json"],
        "local_collection_root": "artifacts/collected",
        "completion": {"schema_version": "fixture-completion-v1"},
        "host_registry": "configs/cloud/registry.toml",
        "host_assignments": [
            {"workload_id": "job-01", "host_role": "core-01"}
        ],
    }


def write_contract(path: Path, payload: dict[str, object] | None = None) -> Path:
    path.write_text(
        yaml.safe_dump(payload or contract_payload(), sort_keys=False),
        encoding="utf-8",
    )
    return path


def remote_config(**overrides: object) -> bridge.BridgeConfig:
    values: dict[str, object] = {
        "host": "core.example.org",
        "user": "researcher",
        "remote_repo": "/home/researcher/sktlm",
        "remote_data_mount": "/mnt/sktlm-data",
        "remote_cloud_root": "/mnt/sktlm-data/sktlm",
        "repository_url": "https://github.com/example/sktlm.git",
        "host_profile": "core-01",
        "machine_id": "core-01",
        "host_role": "core-01",
    }
    values.update(overrides)
    return bridge.validate_config(bridge.BridgeConfig(**values))


def test_contract_drives_branch_roots_profiles_hosts_and_deployment(tmp_path: Path) -> None:
    contract = load_experiment_contract(write_contract(tmp_path / "contract.yaml"))
    assert contract.branch == "exp/fixture"
    assert contract.deployment.mode == "git_bundle"
    assert contract.remote_run_root == "artifacts/runs"
    assert contract.optional_metrics_root == "artifacts/metrics"
    assert contract.profile_files("scientific") == ("summary.json", "result.tsv")
    assert contract.host_role_for("job-01") == "core-01"
    assert contract.deployment_identity == {
        "contract_id": "fixture-v1",
        "branch": "exp/fixture",
        "mode": "git_bundle",
        "require_published_head": True,
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.__setitem__("remote_run_root", "/escape"), "relative path"),
        (lambda value: value.__setitem__("access_token", "secret"), "secret-bearing"),
        (
            lambda value: value["deployment"].__setitem__("mode", "copied_tree"),
            "unsupported deployment mode",
        ),
        (
            lambda value: value["host_assignments"].append(
                {"workload_id": "job-01", "host_role": "core-02"}
            ),
            "workload IDs must be unique",
        ),
    ],
)
def test_contract_fails_closed(tmp_path: Path, mutation, message: str) -> None:
    payload = contract_payload()
    mutation(payload)
    with pytest.raises(ContractError, match=message):
        load_experiment_contract(write_contract(tmp_path / "bad.yaml", payload))


def test_bridge_has_no_experiment_branch_default_and_binds_exact_contract(
    tmp_path: Path,
) -> None:
    contract = load_experiment_contract(write_contract(tmp_path / "contract.yaml"))
    config = bridge.bind_experiment_contract(remote_config(), contract)
    assert config.branch == "exp/fixture"
    source = Path(bridge.__file__).read_text(encoding="utf-8")
    assert "DEFAULT_BRANCH" not in source
    assert "exp/m0-" + "core-methods" not in source
    with pytest.raises(bridge.BridgeError, match="conflicts"):
        bridge.bind_experiment_contract(
            remote_config(branch="exp/other"), contract
        )


def test_bundle_transport_is_hash_bound_verified_and_fast_forward_only(
    tmp_path: Path,
) -> None:
    contract = load_experiment_contract(write_contract(tmp_path / "contract.yaml"))
    config = bridge.bind_experiment_contract(remote_config(), contract)
    script = bridge.build_bundle_deploy_script(
        config,
        expected_head="a" * 40,
        remote_bundle="/mnt/sktlm-data/sktlm/deployment_bundles/fixture-v1/repo.bundle",
        bundle_sha256="b" * 64,
    )
    assert "bundle verify" in script
    assert "sha256sum" in script
    assert "merge --ff-only" in script
    assert "status --porcelain" in script
    assert "git reset" not in script
    assert "git pull" not in script


def test_contract_download_hashes_use_declared_inventory(tmp_path: Path) -> None:
    contract = load_experiment_contract(write_contract(tmp_path / "contract.yaml"))
    summary = tmp_path / "summary.json"
    result = tmp_path / "result.tsv"
    summary.write_text(json.dumps({"valid": True}), encoding="utf-8")
    result.write_text("key\tvalue\n", encoding="utf-8")
    inventory = {}
    for path in (summary, result):
        inventory[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    audit = {"valid": True, "artifacts": inventory}
    assert (
        bridge.validate_contract_downloaded_hashes(
            tmp_path, audit, contract, "scientific"
        )
        == []
    )
    result.write_text("tampered\n", encoding="utf-8")
    failures = bridge.validate_contract_downloaded_hashes(
        tmp_path, audit, contract, "scientific"
    )
    assert any("mismatch" in failure for failure in failures)


def test_direct_contract_host_assignment_requires_selected_role(tmp_path: Path) -> None:
    contract = load_experiment_contract(write_contract(tmp_path / "contract.yaml"))
    assignment = bridge.contract_host_assignment(
        tmp_path, remote_config(), contract, "job-01"
    )
    assert assignment == {
        "source": "experiment_contract",
        "workload_id": "job-01",
        "host_role": "core-01",
    }
    with pytest.raises(bridge.BridgeError, match="assigned to host role"):
        bridge.contract_host_assignment(
            tmp_path,
            remote_config(
                host_profile="core-02", machine_id="core-02", host_role="core-02"
            ),
            contract,
            "job-01",
        )
