from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import pytest


BOOTSTRAP_PATH = (
    Path(__file__).parents[2] / "scripts/cloud/bootstrap_cloud_host.py"
)
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_cloud_host_for_tests", BOOTSTRAP_PATH
)
assert SPEC is not None and SPEC.loader is not None
bootstrap = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bootstrap
SPEC.loader.exec_module(bootstrap)


class NoRemoteRunner:
    def run(
        self,
        argv: Sequence[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"unexpected operation: {list(argv)}")


def remote_config(profile: str = "core-09") -> object:
    return bootstrap.bridge.validate_config(
        bootstrap.bridge.BridgeConfig(
            host=f"{profile}.example.org",
            user="root",
            port=22,
            remote_repo="/root/sktlm",
            remote_data_mount="/mnt/sktlm-data",
            remote_cloud_root="/mnt/sktlm-data/sktlm",
            branch="exp/s1m2-reusable-pieces",
            host_profile=profile,
            machine_id=f"machine-{profile}",
            host_role="generic-bootstrap",
        )
    )


def release() -> object:
    return bootstrap.LocalRelease(
        branch="exp/s1m2-reusable-pieces",
        head="a" * 40,
    )


def test_bootstrap_stage_order_is_generic_and_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(
        bootstrap, "validate_local_release", lambda *_args: release()
    )
    monkeypatch.setattr(bootstrap.bridge, "require_transfer_platform", lambda: None)
    monkeypatch.setattr(bootstrap.bridge, "require_tool", lambda name: name)

    def remote_stage(
        receipt: dict[str, object],
        _config: object,
        _runner: object,
        name: str,
        _script: str,
    ) -> dict[str, str]:
        events.append(name)
        receipt["stages"].append({"name": name, "status": "PASS"})  # type: ignore[index,union-attr]
        return {"status": "READY"} if name == "final_validation" else {}

    def deploy(
        receipt: dict[str, object], *_args: object, **_kwargs: object
    ) -> None:
        events.extend(("repo_probe", "deploy"))
        receipt["stages"].extend(  # type: ignore[index,union-attr]
            (
                {"name": "repo_probe", "status": "PASS"},
                {"name": "deploy", "status": "PASS"},
            )
        )

    def inputs(
        receipt: dict[str, object], *_args: object, **_kwargs: object
    ) -> None:
        events.extend(("inputs", "input_receipt"))
        receipt["stages"].extend(  # type: ignore[index,union-attr]
            (
                {"name": "inputs", "status": "PASS"},
                {"name": "input_receipt", "status": "PASS"},
            )
        )

    monkeypatch.setattr(bootstrap, "_run_remote_stage", remote_stage)
    monkeypatch.setattr(bootstrap, "_deploy_exact_head", deploy)
    monkeypatch.setattr(bootstrap, "_push_inputs", inputs)

    result = bootstrap.bootstrap_host(
        repo_root=tmp_path,
        config=remote_config(),
        data_device="/dev/vdb",
        dry_run=False,
        runner=object(),
    )

    assert result["status"] == "READY"
    assert events == [
        "ssh",
        "prerequisites",
        "data_disk",
        "python",
        "repo_probe",
        "deploy",
        "layout",
        "dependencies",
        "inputs",
        "input_receipt",
        "final_validation",
    ]


def test_dry_run_plans_without_remote_or_mutating_operations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bootstrap, "validate_local_release", lambda *_args: release()
    )
    result = bootstrap.bootstrap_host(
        repo_root=tmp_path,
        config=remote_config("core-10"),
        data_device="/dev/vdb",
        dry_run=True,
        runner=NoRemoteRunner(),
    )
    assert result["status"] == "PLANNED"
    assert all(stage["status"] == "PLANNED" for stage in result["stages"])


def test_disk_script_accepts_only_blank_or_owned_reentry_state() -> None:
    script = bootstrap.build_disk_script(remote_config(), "/dev/vdb")
    assert 'if [ "$partition_count" -eq 0 ]' in script
    assert "mklabel gpt" in script
    assert "sktlm-data-bootstrap" in script
    assert 'part_label" = "sktlm-data' in script
    assert "unexpected existing partitions on data device" in script
    assert "unexpected filesystem signature exists" in script
    assert "refusing root/system backing device" in script
    assert "findmnt -rn -M" in script


def test_data_device_validation_fails_closed() -> None:
    for value in ("vdb", "/tmp/vdb", "/dev/../root", "/dev/vdb;reboot"):
        with pytest.raises(bootstrap.BootstrapError, match="/dev path"):
            bootstrap.build_disk_script(remote_config(), value)


def test_ready_python_dependencies_and_links_are_reused() -> None:
    python_script = bootstrap.build_python_script()
    assert python_script.index('if [ -x "$python_bin" ]') < python_script.index(
        "wget -q"
    )
    assert "import _posixsubprocess, subprocess" in python_script

    prerequisite_script = bootstrap.build_prerequisites_script()
    assert "prerequisites=REUSED" in prerequisite_script
    assert prerequisite_script.index("prerequisites=REUSED") < prerequisite_script.index(
        "apt-get update"
    )

    layout_script = bootstrap.build_layout_script(remote_config())
    assert "existing symlink points elsewhere" in layout_script
    assert "refusing to replace conflicting path" in layout_script
    assert "ln -sfn" not in layout_script

    dependency_script = bootstrap.build_dependencies_script(
        remote_config(), "a" * 40
    )
    assert "dependencies=REUSED" in dependency_script
    assert bootstrap.CPU_TORCH_INDEX in dependency_script
    assert "/opt/python-3.11.9/bin/python3.11" in dependency_script


def test_exact_remote_head_reuses_repository_without_deployment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt: dict[str, object] = {"stages": []}

    def probe(*_args: object, **_kwargs: object) -> dict[str, str]:
        return {"repo_state": "CLEAN", "repo_head": "a" * 40}

    monkeypatch.setattr(bootstrap, "_run_remote_stage", probe)
    monkeypatch.setattr(
        bootstrap.bridge,
        "execute_receipted",
        lambda *_args, **_kwargs: pytest.fail("deployment should be skipped"),
    )
    bootstrap._deploy_exact_head(
        receipt,
        tmp_path,
        remote_config(),
        object(),
        release(),
    )
    assert receipt["stages"] == [
        {"name": "deploy", "status": "REUSED", "head": "a" * 40}
    ]


def test_arbitrary_host_profile_is_loaded_without_six_host_assumption(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "bridge.toml"
    config_path.write_text(
        """
[bridge]
user = "root"
remote_repo = "/root/sktlm"
remote_data_mount = "/mnt/sktlm-data"
remote_cloud_root = "/mnt/sktlm-data/sktlm"
branch = "exp/s1m2-reusable-pieces"

[host_profiles.core-09]
machine_id = "new-machine"
role = "new-role"
host = "core-09.example.org"
""".strip(),
        encoding="utf-8",
    )
    config = bootstrap.bridge.load_config(
        config_path, explicit=True, host_profile="core-09"
    )
    assert config.host_profile == "core-09"
    assert config.machine_id == "new-machine"
    assert config.host == "core-09.example.org"
