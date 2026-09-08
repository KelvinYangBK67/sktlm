from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

from sktlm.cloud.contracts import load_experiment_contract
from sktlm.production import s1m2


OPS_PATH = Path(__file__).parents[2] / "scripts/cloud/s1m2_vm_ops.py"
SPEC = importlib.util.spec_from_file_location("s1m2_vm_ops_for_tests", OPS_PATH)
assert SPEC is not None and SPEC.loader is not None
ops = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ops
SPEC.loader.exec_module(ops)


def remote_config(role: str = "core-01") -> object:
    return ops.bridge.BridgeConfig(
        host=f"{role}.example.org",
        user="ubuntu",
        port=22,
        remote_repo="/home/ubuntu/sktlm",
        remote_data_mount="/mnt/sktlm-data",
        remote_cloud_root="/mnt/sktlm-data/sktlm",
        branch="exp/s1m2-reusable-pieces",
        host_profile=role,
        machine_id=role,
    )


def test_six_host_profiles_are_exact_and_distinct(tmp_path: Path) -> None:
    lines = [
        "[bridge]",
        'user = "ubuntu"',
        'remote_repo = "/home/ubuntu/sktlm"',
        'remote_data_mount = "/mnt/sktlm-data"',
        'remote_cloud_root = "/mnt/sktlm-data/sktlm"',
    ]
    for role in ops.CORE_HOST_ROLES:
        lines.extend(
            [
                f"[host_profiles.{role}]",
                f'machine_id = "{role}"',
                f'role = "{role}"',
                f'host = "{role}.example.org"',
            ]
        )
    config_path = tmp_path / "bridge.toml"
    config_path.write_text("\n".join(lines), encoding="utf-8")
    contract = load_experiment_contract(Path("configs/cloud/s1m2_prevm.yaml"))
    configs = ops.load_host_configs(config_path, contract)
    assert list(configs) == list(ops.CORE_HOST_ROLES)
    assert len({config.host for config in configs.values()}) == 6

    duplicate = config_path.read_text(encoding="utf-8").replace(
        'host = "core-06.example.org"', 'host = "core-05.example.org"'
    )
    config_path.write_text(duplicate, encoding="utf-8")
    with pytest.raises(ops.VmOpsError, match="distinct SSH endpoints"):
        ops.load_host_configs(config_path, contract)


def test_preflight_covers_machine_resources_processes_and_inputs() -> None:
    script = ops.build_preflight_script(remote_config(), "core-01")
    for marker in (
        "machine_identity=",
        "boot_identity=",
        "cpu_count=",
        "ram_bytes=",
        "data_free_bytes=",
        "repo_head=",
        "active_s1m2_process_count=",
        "venv_python=",
        "m0_present=",
        "m0_prime_present=",
    ):
        assert marker in script


def test_environment_is_idempotent_and_ends_with_pip_check() -> None:
    script = ops.build_environment_setup_script(remote_config(), "a" * 40)
    assert "python3.11 -m venv" in script
    assert "SKIPPED_ALREADY_VALID" in script
    assert 'pip install -e "$repo"' in script
    assert script.count("-m pip check") >= 2
    assert 'link_dir "$cloud/data/derived" "$repo/data/derived"' in script


def test_remote_validation_binds_head_host_space_environment_and_contract() -> None:
    script = ops.build_remote_validate_script(
        remote_config(), "core-01", "a" * 40, 20 * 1024**3
    )
    assert "HEAD mismatch" in script
    assert "dirty worktree" in script
    assert "free-space gate failed" in script
    assert "sys.version_info[:2] == (3, 11)" in script
    assert "sktlm.production.s1m2 validate-contract" in script
    assert "host_role=%s" in script


def test_round1_detached_launch_uses_generated_command_and_strong_identity() -> None:
    contract = s1m2.load_contract(repo_root=Path("."), verify_files=False)
    plan = s1m2.build_round1_plan(
        contract,
        identity={
            "git_sha": "a" * 40,
            "branch": "exp/s1m2-reusable-pieces",
            "dirty_worktree": False,
        },
    )
    s1m2._write_plan_commands(plan, Path("artifacts/s1m2_production/round1.json"))
    job = copy.deepcopy(plan["jobs"][0])
    script = ops.build_round1_launch_script(
        remote_config(),
        job,
        "a" * 40,
        "artifacts/s1m2_production/round1.json",
        "b" * 64,
    )
    assert job["launch_command_shell"] in script
    assert "nohup sh" in script
    assert '"process_start_ticks"' in script
    assert '"machine_identity"' in script
    assert '"boot_identity"' in script
    assert '"completion_marker"' in script
    assert '"exit_status":null' in script
    assert "run or control path already exists" in script


def test_input_probe_checks_before_transfer_with_venv_path() -> None:
    contract = load_experiment_contract(Path("configs/cloud/s1m2_prevm.yaml"))
    script = ops.build_input_probe_script(remote_config(), contract, "a" * 40)
    assert 'export PATH="$repo/.venv/bin:$PATH"' in script
    assert "inputs_valid=true" in script
    assert "inputs_valid=false" in script
    assert "sktlm.production.s1m2 validate-contract" in script
