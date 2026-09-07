"""Generic cloud bridge contract, safety, audit, and resume tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.cloud import sktlm_bridge as bridge
from sktlm.cloud.contracts import ContractError, load_experiment_contract


CONTRACT_PATH = Path("configs/cloud/full_m0_baselines.yaml")


def test_tracked_contract_declares_all_input_sets_and_profiles() -> None:
    contract = load_experiment_contract(CONTRACT_PATH)
    assert contract.contract_id == "full-m0-baselines-v1"
    assert {item.input_id for item in contract.input_sets} == {
        "frozen_m0_canonical", "frozen_m0_representations", "derived_m0_prime"
    }
    assert contract.profile_files("full") is None
    assert contract.audit_inventory_key == "artifacts"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda p: p.__setitem__("remote_run_root", "/absolute"), "relative path"),
        (lambda p: p.__setitem__("remote_run_root", "artifacts/../escape"), "relative path"),
        (lambda p: p.__setitem__("access_token", "x"), "secret-bearing"),
        (lambda p: p["collection_profiles"].__setitem__("debug", ["x"]), "profiles must declare"),
    ],
)
def test_contract_rejects_absolute_traversal_secret_and_unknown_profile(
    tmp_path: Path, mutation, message: str
) -> None:
    payload = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    mutation(payload)
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ContractError, match=message):
        load_experiment_contract(path)


def test_unknown_profile_and_unsafe_rsync_are_rejected() -> None:
    contract = load_experiment_contract(CONTRACT_PATH)
    with pytest.raises(ContractError, match="unknown collection profile"):
        contract.profile_files("debug")
    config = bridge.validate_config(
        bridge.BridgeConfig(host="example.org", remote_repo="/mnt/sktlm-data/repo")
    )
    with pytest.raises(bridge.BridgeError, match="unsafe rsync include"):
        bridge.build_rsync_argv(
            config,
            source="/remote/",
            destination="local/",
            direction="pull",
            include_files=("../escape",),
        )
    argv = bridge.build_rsync_argv(
        config,
        source="/remote/",
        destination="local/",
        direction="pull",
        include_files=("metrics.json",),
    )
    assert "--delete" not in argv
    assert "--append-verify" in argv


def test_collection_resume_requires_exact_identity_and_completed_collection_is_immutable(tmp_path: Path) -> None:
    identity = {"condition": "c", "audit": "a"}
    destination = bridge._local_collection_root(tmp_path, "condition", resume_identity=identity)
    assert bridge._local_collection_root(tmp_path, "condition", resume_identity=identity) == destination
    with pytest.raises(bridge.BridgeError, match="identity differs"):
        bridge._local_collection_root(tmp_path, "condition", resume_identity={"condition": "other"})
    bridge._complete_collection(destination)
    with pytest.raises(FileExistsError, match="completed collection"):
        bridge._local_collection_root(tmp_path, "condition", resume_identity=identity)


def test_downloaded_files_are_checked_against_remote_audit(tmp_path: Path) -> None:
    contract = load_experiment_contract(CONTRACT_PATH)
    inventory = {}
    for relative in contract.required_audited_files:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
        inventory[relative] = {
            "bytes": path.stat().st_size,
            "sha256": bridge.file_sha256(path),
        }
    audit = {"valid": True, "artifacts": inventory}
    assert bridge.validate_downloaded_audit_hashes(tmp_path, audit, contract, "report") == []
    (tmp_path / "metrics.json").write_text("tampered", encoding="utf-8")
    failures = bridge.validate_downloaded_audit_hashes(tmp_path, audit, contract, "report")
    assert any("mismatch" in failure for failure in failures)


def test_host_assignment_requires_exact_profile(tmp_path: Path) -> None:
    registry = tmp_path / "registry.toml"
    registry.write_text(
        '[[assignments]]\ncondition_id = "cell"\nhost_profile = "host-a"\n',
        encoding="utf-8",
    )
    wrong = bridge.BridgeConfig(host_profile="host-b")
    with pytest.raises(bridge.BridgeError, match="assigned to host-a"):
        bridge.registry_assignment(registry, condition_id="cell", config=wrong)
    match = bridge.registry_assignment(
        registry, condition_id="cell", config=bridge.BridgeConfig(host_profile="host-a")
    )
    assert match["host_profile"] == "host-a"


def test_bridge_source_is_experiment_neutral_and_mount_guarded() -> None:
    source = Path(bridge.__file__).read_text(encoding="utf-8")
    forbidden = (
        "exp/m0-" + "core-methods",
        "artifacts/" + "latent_benchmarks",
        "audit_" + "latent_run.py",
        "latent_" + "lexicon.tsv",
        "boundary_" + "posteriors.jsonl",
        "learner" + ".sqlite",
    )
    assert not any(value in source for value in forbidden)
    config = bridge.validate_config(
        bridge.BridgeConfig(host="example.org", remote_repo="/mnt/sktlm-data/repo")
    )
    assert "realpath" in bridge._remote_mount_guard(config, "/mnt/sktlm-data/results")
    with pytest.raises(bridge.BridgeError, match="escapes"):
        bridge._remote_mount_guard(config, "/tmp/results")


def test_remote_audit_uses_contract_entrypoint_and_receipts_redact_identity(tmp_path: Path) -> None:
    contract = load_experiment_contract(CONTRACT_PATH)
    config = bridge.validate_config(
        bridge.BridgeConfig(
            host="private.example.org",
            user="researcher",
            identity_file="/private/key",
            remote_repo="/mnt/sktlm-data/repo",
        )
    )

    class Runner:
        def __init__(self) -> None:
            self.argv = None

        def run(self, argv, **kwargs):
            self.argv = argv
            return subprocess.CompletedProcess(argv, 0, '{"valid": true, "artifacts": {}}\n', "")

    runner = Runner()
    payload = bridge.remote_audit(
        config,
        contract,
        "bpe__iast_m0_prime__continuous",
        "/mnt/sktlm-data/repo/artifacts/bundle",
        runner,
    )
    assert payload["valid"] is True
    assert "audit_baseline_run.py" in runner.argv[-1]
    receipt = bridge._redact(
        {"target": config.target, "identity": config.identity_file},
        [config.host, config.user, config.identity_file],
    )
    path = bridge.write_receipt(tmp_path, "fixture", receipt)
    text = path.read_text(encoding="utf-8")
    assert "private.example.org" not in text
    assert "/private/key" not in text
