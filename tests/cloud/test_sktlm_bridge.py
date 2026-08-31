from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

import pytest


BRIDGE_PATH = Path(__file__).parents[2] / "scripts/cloud/sktlm_bridge.py"
SPEC = importlib.util.spec_from_file_location("sktlm_bridge_for_tests", BRIDGE_PATH)
assert SPEC is not None and SPEC.loader is not None
bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)


class FakeRunner:
    def __init__(
        self,
        callback: Callable[[list[str]], subprocess.CompletedProcess[str]],
    ) -> None:
        self.callback = callback
        self.calls: list[list[str]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, input_text, env
        command = list(argv)
        self.calls.append(command)
        return self.callback(command)


def completed(
    argv: Sequence[str],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(list(argv), returncode, stdout, stderr)


def remote_config(**overrides: object) -> object:
    values: dict[str, object] = {
        "host": "research.example.org",
        "user": "ubuntu",
        "port": 22,
        "identity_file": "/keys/research identity",
        "remote_repo": "/home/ubuntu/sktlm",
        "remote_data_mount": "/mnt/sktlm-data",
        "remote_cloud_root": "/mnt/sktlm-data/sktlm",
        "branch": "exp/m0-core-methods",
        "repository_url": "https://github.com/example/sktlm.git",
    }
    values.update(overrides)
    return bridge.validate_config(bridge.BridgeConfig(**values))


def valid_validator_payload() -> dict[str, object]:
    return {
        **bridge.EXPECTED_VALIDATION,
        "representation_manifest_sha256": "abc",
        "external_rules_sha256": "def",
        "failures": [],
    }


def test_config_parsing_and_cli_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "bridge.toml"
    config_path.write_text(
        """
[bridge]
host = "research.example.org"
user = "ubuntu"
port = 2222
remote_repo = "/srv/sktlm repo"
remote_data_mount = "/mnt/sktlm-data"
remote_cloud_root = "/mnt/sktlm-data/sktlm"
branch = "old-branch"
repository_url = "https://github.com/example/sktlm.git"
""".strip(),
        encoding="utf-8",
    )
    config = bridge.load_config(
        config_path,
        {"port": 22, "branch": "exp/m0-core-methods"},
        explicit=True,
    )
    assert config.port == 22
    assert config.branch == "exp/m0-core-methods"
    assert config.remote_repo == "/srv/sktlm repo"


def test_multi_host_profile_selection_and_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "bridge.toml"
    config_path.write_text(
        """
[bridge]
user = "ubuntu"
port = 22
remote_repo = "/home/ubuntu/sktlm"

[host_profiles.core-01]
machine_id = "core-01"
host = "one.example.org"

[host_profiles.core-02]
machine_id = "core-02"
host = "two.example.org"
port = 2222
role = "medium-scaling"
""".strip(),
        encoding="utf-8",
    )
    config = bridge.load_config(
        config_path,
        {"port": 2202},
        explicit=True,
        host_profile="core-02",
    )
    assert config.host == "two.example.org"
    assert config.port == 2202
    assert config.host_profile == "core-02"
    assert config.machine_id == "core-02"
    assert config.host_role == "medium-scaling"
    assert config.available_host_profiles == ("core-01", "core-02")


def test_unknown_host_profile_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "bridge.toml"
    config_path.write_text(
        '[bridge]\nhost = "single.example.org"\n\n'
        '[host_profiles.core-01]\nhost = "one.example.org"\n',
        encoding="utf-8",
    )
    with pytest.raises(bridge.BridgeError, match="unknown host profile"):
        bridge.load_config(config_path, explicit=True, host_profile="core-99")


@pytest.mark.parametrize(
    "key", ["password", "token", "api_key", "access_token", "private_key_contents"]
)
def test_config_rejects_secret_keys(tmp_path: Path, key: str) -> None:
    config_path = tmp_path / "bridge.toml"
    config_path.write_text(
        f'[bridge]\nhost = "example.org"\n{key} = "TOPSECRET"\n',
        encoding="utf-8",
    )
    with pytest.raises(bridge.BridgeError, match="secret-bearing"):
        bridge.load_config(config_path, explicit=True)


def test_host_profile_rejects_secret_bearing_keys(tmp_path: Path) -> None:
    config_path = tmp_path / "bridge.toml"
    config_path.write_text(
        '[bridge]\nhost = "example.org"\n\n'
        '[host_profiles.core-01]\nhost = "one.example.org"\npassword = "TOPSECRET"\n',
        encoding="utf-8",
    )
    with pytest.raises(bridge.BridgeError, match="secret-bearing"):
        bridge.load_config(config_path, explicit=True, host_profile="core-01")


def test_config_rejects_repository_url_credentials() -> None:
    with pytest.raises(bridge.BridgeError, match="embedded credentials"):
        remote_config(repository_url="https://user:TOKEN@example.org/repo.git")


@pytest.mark.parametrize(
    ("field", "value"),
    [("host", "host;command"), ("branch", "branch;command"), ("branch", "bad..branch")],
)
def test_config_rejects_host_and_branch_metacharacters(field: str, value: str) -> None:
    with pytest.raises(bridge.BridgeError):
        remote_config(**{field: value})


def test_destination_path_safety() -> None:
    assert bridge._is_remote_child(
        "/mnt/sktlm-data/sktlm/data/canonical",
        "/mnt/sktlm-data/sktlm",
    )
    assert not bridge._is_remote_child("/mnt/other/data", "/mnt/sktlm-data")
    with pytest.raises(bridge.BridgeError, match="below remote_data_mount"):
        remote_config(remote_cloud_root="/srv/sktlm")
    with pytest.raises(bridge.BridgeError, match="contain '..'"):
        remote_config(remote_repo="/home/ubuntu/../root/repo")
    with pytest.raises(bridge.BridgeError, match="root filesystem"):
        remote_config(remote_repo="/")
    with pytest.raises(bridge.BridgeError, match="may not overlap"):
        remote_config(remote_repo="/mnt/sktlm-data/sktlm/source")


def test_missing_tools_and_windows_transfer_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "find_executable", lambda _name: None)
    with pytest.raises(bridge.BridgeError, match="missing: ssh"):
        bridge.require_tool("ssh")
    monkeypatch.setattr(bridge.platform, "system", lambda: "Windows")
    with pytest.raises(bridge.BridgeError, match="Linux/WSL"):
        bridge.require_transfer_platform()


def test_status_gracefully_reports_missing_config_and_ssh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = FakeRunner(lambda argv: completed(argv))
    assert bridge.remote_status(bridge.BridgeConfig(), runner)["status"] == "MISSING_CONFIG"
    monkeypatch.setattr(bridge, "find_executable", lambda _name: None)
    status = bridge.remote_status(remote_config(), runner)
    assert status == {"configured": True, "reachable": False, "status": "SSH_MISSING"}


def test_status_gracefully_parses_fresh_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "find_executable", lambda name: f"/usr/bin/{name}")
    output = """hostname=cloud-one
git_available=false
git_version=MISSING
python311_available=false
python311_version=MISSING
repo_exists=false
repo_head=MISSING
repo_dirty=MISSING
data_source=/dev/vdb1
data_target=/mnt/sktlm-data
data_fstype=ext4
data_free_bytes=300000000000
canonical_available=false
representations_available=false
input_verification_available=false
input_verification_valid=MISSING
"""
    runner = FakeRunner(lambda argv: completed(argv, stdout=output))
    status = bridge.remote_status(remote_config(), runner)
    assert status["reachable"] is True
    assert status["git_available"] is False
    assert status["python311_available"] is False
    assert status["repo_exists"] is False
    assert status["data_free_bytes"] == 300_000_000_000


def test_status_gracefully_reports_unreachable_remote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bridge, "find_executable", lambda name: f"/usr/bin/{name}")
    runner = FakeRunner(lambda argv: completed(argv, 255, stderr="connection refused"))
    status = bridge.remote_status(remote_config(), runner)
    assert status["reachable"] is False
    assert status["ssh_return_code"] == 255


def test_rsync_command_has_no_delete_and_redacts_identity() -> None:
    config = remote_config()
    argv = bridge.build_rsync_argv(
        config,
        source=Path("/tmp/input tree"),
        destination="/mnt/sktlm-data/sktlm/data/canonical/gretil_iast",
        direction="push",
    )
    assert not any(argument == "--delete" or argument.startswith("--delete-") for argument in argv)
    assert "--partial" in argv
    assert "--protect-args" in argv
    rsync_path = argv[argv.index("--rsync-path") + 1]
    assert "findmnt" in rsync_path
    assert "cloud_real" in rsync_path
    assert "path_real" in rsync_path
    assert "rsync path resolves outside cloud data root" in rsync_path
    assert 'exec rsync "$@"' in rsync_path
    assert "mount " not in rsync_path
    assert argv[-1].endswith(":/mnt/sktlm-data/sktlm/data/canonical/gretil_iast/")
    public = bridge.public_argv(argv)
    assert "/keys/research identity" not in json.dumps(public)


def test_input_directory_preparation_checks_resolved_paths() -> None:
    script = bridge.build_prepare_input_dirs_script(remote_config())
    assert "data_real=$(readlink -f" in script
    assert "path_real=$(readlink -f" in script
    assert "input destination resolves outside cloud data root" in script


def test_result_profiles_are_selective() -> None:
    report_run, report_metrics = bridge.profile_files("report")
    scientific_run, scientific_metrics = bridge.profile_files("scientific")
    full_run, full_metrics = bridge.profile_files("full")
    assert report_run is not None and "learner.sqlite" not in report_run
    assert report_metrics is not None and "process_tree_summary.json" in report_metrics
    assert scientific_run is not None and "analyses.jsonl" in scientific_run
    assert "learner.sqlite" not in scientific_run
    assert scientific_metrics == report_metrics
    assert full_run is None and full_metrics is None


def test_existing_local_collection_is_refused(tmp_path: Path) -> None:
    destination = tmp_path / "artifacts/cloud_collected/run-one"
    destination.mkdir(parents=True)
    with pytest.raises(bridge.BridgeError, match="refusing overwrite"):
        bridge._local_collection_root(tmp_path, None, "run-one")


def test_run_id_rejects_path_traversal() -> None:
    for value in ("../run", "/absolute", "run/name", ".."):
        with pytest.raises(bridge.BridgeError):
            bridge.validate_run_id(value)


def test_validator_valid_and_invalid_parsing() -> None:
    payload = valid_validator_payload()
    assert bridge.interpret_input_validation(payload) == []
    invalid = dict(payload)
    invalid["representation_files"] = 1_439
    failures = bridge.interpret_input_validation(invalid)
    assert any("representation_files" in failure for failure in failures)


def test_remote_validator_accepts_authoritative_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bridge, "find_executable", lambda name: f"/usr/bin/{name}")
    payload = valid_validator_payload()
    runner = FakeRunner(lambda argv: completed(argv, stdout=json.dumps(payload)))
    assert bridge.verify_remote_inputs(remote_config(), runner)["valid"] is True


def test_remote_validator_rejects_invalid_json_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bridge, "find_executable", lambda name: f"/usr/bin/{name}")
    payload = valid_validator_payload()
    payload["valid"] = False
    payload["failures"] = ["freeze mismatch"]
    runner = FakeRunner(lambda argv: completed(argv, 1, json.dumps(payload)))
    with pytest.raises(bridge.BridgeError, match="remote frozen-input validation failed"):
        bridge.verify_remote_inputs(remote_config(), runner)


def test_receipt_writing_redacts_sensitive_values(tmp_path: Path) -> None:
    payload = {
        "schema": bridge.SCHEMA_VERSION,
        "operation": "push-inputs",
        "finished_at": "2026-08-31T12:34:56.123456Z",
        "command": ["ssh", "-i", "/keys/TOPSECRET", "host"],
        "valid": True,
    }
    path = bridge.write_receipt(tmp_path, payload, sensitive_values=("/keys/TOPSECRET",))
    text = path.read_text(encoding="utf-8")
    assert "TOPSECRET" not in text
    assert "<redacted>" in text
    assert json.loads(text)["schema"] == bridge.SCHEMA_VERSION


def test_failed_sync_operation_still_writes_redacted_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bridge, "find_executable", lambda _name: None)
    config = remote_config(
        identity_file="/keys/TOPSECRET",
        host_profile="core-02",
        machine_id="core-02",
        host_role="medium-scaling",
        available_host_profiles=("core-01", "core-02"),
    )
    runner = FakeRunner(lambda argv: completed(argv))

    def fail(_receipt: dict[str, object]) -> dict[str, object]:
        raise bridge.BridgeError("could not load /keys/TOPSECRET")

    receipt, path, error = bridge.execute_receipted(
        "push-inputs",
        "local_to_remote",
        tmp_path,
        config,
        runner,
        fail,
    )
    assert error is not None
    assert receipt["valid"] is False
    assert receipt["host_profile"] == "core-02"
    assert receipt["machine_id"] == "core-02"
    text = path.read_text(encoding="utf-8")
    assert "TOPSECRET" not in text
    assert "<redacted>" in text


def test_downloaded_files_are_compared_with_remote_audit(tmp_path: Path) -> None:
    benchmark = tmp_path / "benchmark"
    benchmark.mkdir()
    summary = benchmark / "summary.json"
    summary.write_text('{"valid": true}\n', encoding="utf-8")
    audit = {
        "scientific_artifacts": {
            "summary.json": {
                "bytes": summary.stat().st_size,
                "sha256": bridge.file_sha256(summary),
            }
        }
    }
    comparisons, failures = bridge.validate_downloaded_audit_hashes(tmp_path, audit)
    assert failures == []
    assert comparisons[0]["remote_audit_equal"] is True
    summary.write_text('{"valid": false}\n', encoding="utf-8")
    _comparisons, failures = bridge.validate_downloaded_audit_hashes(tmp_path, audit)
    assert failures == ["downloaded artifact differs from remote audit: summary.json"]


def test_collection_registry_requires_exact_profile_assignment(tmp_path: Path) -> None:
    registry = tmp_path / bridge.REGISTRY_RELATIVE_PATH
    registry.parent.mkdir(parents=True)
    registry.write_text(
        """
[[runs]]
machine_id = "core-02"
host_profile = "core-02"
run_id = "cloud_medium_p10_w8_p3"
metrics_id = "medium_p10_w8_p3"
state = "RUNNING"
""".strip(),
        encoding="utf-8",
    )
    config = remote_config(
        host_profile="core-02",
        machine_id="core-02",
        available_host_profiles=("core-01", "core-02"),
    )
    assignment = bridge.collection_registry_assignment(
        tmp_path,
        config,
        "cloud_medium_p10_w8_p3",
        "medium_p10_w8_p3",
    )
    assert assignment is not None
    assert assignment["machine_id"] == "core-02"
    wrong = remote_config(
        host_profile="core-01",
        machine_id="core-01",
        available_host_profiles=("core-01", "core-02"),
    )
    with pytest.raises(bridge.BridgeError, match="assigned to host profile"):
        bridge.collection_registry_assignment(
            tmp_path,
            wrong,
            "cloud_medium_p10_w8_p3",
            "medium_p10_w8_p3",
        )
    unselected = remote_config(available_host_profiles=("core-01", "core-02"))
    with pytest.raises(bridge.BridgeError, match="requires --host-profile"):
        bridge.collection_registry_assignment(
            tmp_path,
            unselected,
            "cloud_medium_p10_w8_p3",
            "medium_p10_w8_p3",
        )


def test_tracked_registry_has_unique_logical_assignments() -> None:
    registry_path = BRIDGE_PATH.parents[2] / bridge.REGISTRY_RELATIVE_PATH
    assert bridge.tomllib is not None
    registry = bridge.tomllib.loads(registry_path.read_text(encoding="utf-8"))
    runs = registry["runs"]
    assert len({row["run_id"] for row in runs}) == len(runs)
    states = {row["state"] for row in runs}
    assert states <= {"PREPARED", "RUNNING", "DONE"}
    assert not any("host" in row or "identity_file" in row for row in runs)


def test_rsync_itemized_output_is_parsed_into_receipt_records() -> None:
    output = "SKTLM\t>f+++++++++\t12\tdataset/file with spaces.txt\n"
    assert bridge.parse_rsync_records(output) == [
        {
            "itemized": ">f+++++++++",
            "bytes": 12,
            "path": "dataset/file with spaces.txt",
        }
    ]


def _git_callback(head: str, *, dirty: bool = False, deployed: str | None = None):
    def callback(argv: list[str]) -> subprocess.CompletedProcess[str]:
        if argv[:3] == ["git", "rev-parse", "HEAD"]:
            return completed(argv, stdout=head + "\n")
        if argv[:3] == ["git", "branch", "--show-current"]:
            return completed(argv, stdout="exp/m0-core-methods\n")
        if argv[:3] == ["git", "status", "--porcelain"]:
            return completed(argv, stdout=" M changed\n" if dirty else "")
        if argv[:3] == ["git", "ls-remote", "--heads"]:
            return completed(argv, stdout=f"{head}\trefs/heads/exp/m0-core-methods\n")
        if argv and argv[0] == "ssh":
            remote = deployed if deployed is not None else head
            return completed(argv, stdout=f"deployed_head={remote}\n")
        raise AssertionError(f"unexpected command: {argv}")

    return callback


def test_dirty_local_repo_refuses_deploy_before_remote_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = "a" * 40
    runner = FakeRunner(_git_callback(head, dirty=True))
    monkeypatch.setattr(bridge, "find_executable", lambda name: f"/usr/bin/{name}")
    receipt = {"warnings": []}
    with pytest.raises(bridge.BridgeError, match="local repository is dirty"):
        bridge.deploy_code_action(
            receipt,
            remote_config(),
            tmp_path,
            runner,
            allow_dirty=False,
            allow_unpushed=False,
        )
    assert not any(call and call[0] == "ssh" for call in runner.calls)


def test_exact_head_deploy_and_safe_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = "b" * 40
    runner = FakeRunner(_git_callback(head))
    monkeypatch.setattr(bridge, "find_executable", lambda name: f"/usr/bin/{name}")
    result = bridge.deploy_code_action(
        {"warnings": []},
        remote_config(),
        tmp_path,
        runner,
        allow_dirty=False,
        allow_unpushed=False,
    )
    assert result["deployed_head"] == head
    script = bridge.build_deploy_script(remote_config(), head)
    assert "merge --ff-only" in script
    assert 'if [ "$actual" != "$expected" ]' in script
    assert "git reset" not in script
    assert "git push" not in script


def test_deploy_rejects_remote_head_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = "c" * 40
    runner = FakeRunner(_git_callback(head, deployed="d" * 40))
    monkeypatch.setattr(bridge, "find_executable", lambda name: f"/usr/bin/{name}")
    with pytest.raises(bridge.BridgeError, match="did not verify exact HEAD"):
        bridge.deploy_code_action(
            {"warnings": []},
            remote_config(),
            tmp_path,
            runner,
            allow_dirty=False,
            allow_unpushed=False,
        )


def test_remote_invalid_audit_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "find_executable", lambda name: f"/usr/bin/{name}")
    payload = {"valid": False, "failures": ["missing files"]}
    runner = FakeRunner(lambda argv: completed(argv, 1, json.dumps(payload)))
    result = bridge.remote_audit_result(remote_config(), runner, "run-one")
    assert result["valid"] is False
    assert result["ssh_return_code"] == 1
    assert "missing files" in result["failures"]


def test_help_and_unknown_argument_rejection() -> None:
    parser = bridge.build_parser()
    with pytest.raises(SystemExit) as help_exit:
        parser.parse_args(["--help"])
    assert help_exit.value.code == 0
    with pytest.raises(SystemExit) as unknown_exit:
        parser.parse_args(["unknown-command"])
    assert unknown_exit.value.code == 2
    selected = parser.parse_args(
        [
            "collect",
            "cloud_medium_p10_w8_p3",
            "--metrics-id",
            "medium_p10_w8_p3",
            "--host-profile",
            "core-02",
        ]
    )
    assert selected.host_profile == "core-02"
