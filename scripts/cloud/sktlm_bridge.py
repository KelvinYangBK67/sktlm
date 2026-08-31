#!/usr/bin/env python3
"""Deterministic Git/SSH/rsync control plane for sktlm cloud research."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - the bridge targets Python 3.11
    tomllib = None  # type: ignore[assignment]


SCHEMA_VERSION = "sktlm-cloud-transfer-receipt/v1"
DEFAULT_BRANCH = "exp/m0-core-methods"
DEFAULT_REPOSITORY_URL = "https://github.com/KelvinYangBK67/sktlm.git"
DEFAULT_DATA_MOUNT = "/mnt/sktlm-data"
DEFAULT_CLOUD_ROOT = "/mnt/sktlm-data/sktlm"
EXPECTED_VALIDATION = {
    "canonical_documents": 240,
    "canonical_characters": 57_588_079,
    "canonical_bytes": 69_864_279,
    "freeze_id": "9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40",
    "representation_files": 1_440,
    "external_rule_count": 1_218,
    "valid": True,
}
REPORT_RUN_FILES = (
    "benchmark_metrics.json",
    "timing_metrics.json",
    "checkpoint.json",
    "config.json",
    "provenance.json",
    "summary.json",
    "audit.json",
    "inspection_report.md",
)
REPORT_METRICS_FILES = (
    "audit.json",
    "process_tree_summary.json",
    "process_tree_samples.csv",
)
SCIENTIFIC_FILES = (
    "iteration_metrics.json",
    "analyses.jsonl",
    "boundary_posteriors.jsonl",
    "latent_lexicon.tsv",
    "rule_usage.tsv",
)
CONFIG_FIELDS = {
    "host",
    "user",
    "port",
    "identity_file",
    "remote_repo",
    "remote_data_mount",
    "remote_cloud_root",
    "branch",
    "repository_url",
}
HOST_PROFILE_METADATA_FIELDS = {"machine_id", "role", "notes"}
REGISTRY_RELATIVE_PATH = Path("configs/cloud/experiment_registry.toml")
SECRET_KEY_RE = re.compile(
    r"(?:password|passwd|passphrase|private[_-]?key(?:_contents)?|"
    r"(?:access[_-]?)?token|api[_-]?key|secret|credential)",
    re.IGNORECASE,
)
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class BridgeError(RuntimeError):
    """A controlled bridge failure safe to report to the user."""


class SystemRunner:
    """List-argv subprocess runner; never interpolates through a local shell."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        process_env = os.environ.copy()
        if env is not None:
            process_env.update(env)
        return subprocess.run(
            list(argv),
            cwd=cwd,
            input=input_text,
            env=process_env,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
        )


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    host: str | None = None
    user: str | None = None
    port: int = 22
    identity_file: str | None = None
    remote_repo: str | None = None
    remote_data_mount: str = DEFAULT_DATA_MOUNT
    remote_cloud_root: str = DEFAULT_CLOUD_ROOT
    branch: str = DEFAULT_BRANCH
    repository_url: str = DEFAULT_REPOSITORY_URL
    host_profile: str | None = None
    machine_id: str | None = None
    host_role: str | None = None
    available_host_profiles: tuple[str, ...] = ()

    @property
    def target(self) -> str:
        if not self.host:
            raise BridgeError("remote host is not configured")
        return f"{self.user}@{self.host}" if self.user else self.host

    @property
    def remote_ready(self) -> bool:
        return bool(self.host and self.remote_repo)


def find_executable(name: str) -> str | None:
    return shutil.which(name)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_secret_keys(value: Any, path: str = "") -> None:
    if not isinstance(value, dict):
        return
    for key, nested in value.items():
        key_text = str(key)
        current = f"{path}.{key_text}" if path else key_text
        if SECRET_KEY_RE.search(key_text):
            raise BridgeError(f"secret-bearing configuration key is forbidden: {current}")
        _reject_secret_keys(nested, current)


def _normalize_remote_path(value: str, field: str) -> str:
    if not value or not value.startswith("/"):
        raise BridgeError(f"{field} must be an absolute POSIX path")
    if any(character in value for character in ("\0", "\n", "\r")):
        raise BridgeError(f"{field} contains a forbidden control character")
    if ".." in PurePosixPath(value).parts:
        raise BridgeError(f"{field} may not contain '..'")
    normalized = posixpath.normpath(value)
    if normalized == "/" and field in {"remote_data_mount", "remote_cloud_root"}:
        raise BridgeError(f"{field} may not be the root filesystem")
    return normalized


def _is_remote_child(child: str, parent: str) -> bool:
    child_path = PurePosixPath(posixpath.normpath(child))
    parent_path = PurePosixPath(posixpath.normpath(parent))
    return child_path != parent_path and parent_path in child_path.parents


def validate_config(config: BridgeConfig) -> BridgeConfig:
    if config.host is not None:
        if not re.fullmatch(r"[A-Za-z0-9._:\-\[\]]+", config.host):
            raise BridgeError("host contains unsupported characters")
    if config.user is not None and not re.fullmatch(r"[A-Za-z0-9._-]+", config.user):
        raise BridgeError("SSH user contains unsupported characters")
    if not 1 <= config.port <= 65_535:
        raise BridgeError("SSH port must be between 1 and 65535")
    if (
        not re.fullmatch(r"[A-Za-z0-9._/-]+", config.branch)
        or config.branch.startswith(("-", "/"))
        or config.branch.endswith((".", "/"))
        or ".." in config.branch
        or "@{" in config.branch
    ):
        raise BridgeError("branch is not a supported Git branch name")
    parsed_url = urlsplit(config.repository_url)
    if parsed_url.scheme and (parsed_url.username or parsed_url.password):
        raise BridgeError("repository_url may not contain embedded credentials")
    data_mount = _normalize_remote_path(config.remote_data_mount, "remote_data_mount")
    cloud_root = _normalize_remote_path(config.remote_cloud_root, "remote_cloud_root")
    if not _is_remote_child(cloud_root, data_mount):
        raise BridgeError("remote_cloud_root must be below remote_data_mount")
    remote_repo = None
    if config.remote_repo is not None:
        remote_repo = _normalize_remote_path(config.remote_repo, "remote_repo")
        if remote_repo == "/":
            raise BridgeError("remote_repo may not be the root filesystem")
        if (
            remote_repo == cloud_root
            or _is_remote_child(remote_repo, cloud_root)
            or _is_remote_child(cloud_root, remote_repo)
        ):
            raise BridgeError("remote_repo and remote_cloud_root may not overlap")
    identity = None
    if config.identity_file:
        identity = os.path.expanduser(config.identity_file)
    return BridgeConfig(
        host=config.host,
        user=config.user,
        port=config.port,
        identity_file=identity,
        remote_repo=remote_repo,
        remote_data_mount=data_mount,
        remote_cloud_root=cloud_root,
        branch=config.branch,
        repository_url=config.repository_url,
        host_profile=config.host_profile,
        machine_id=config.machine_id,
        host_role=config.host_role,
        available_host_profiles=config.available_host_profiles,
    )


def load_config(
    path: Path | None,
    overrides: Mapping[str, Any] | None = None,
    *,
    explicit: bool = False,
    host_profile: str | None = None,
) -> BridgeConfig:
    values: dict[str, Any] = {}
    profiles: dict[str, Any] = {}
    machine_id: str | None = None
    host_role: str | None = None
    if path is not None and path.is_file():
        if tomllib is None:
            raise BridgeError("TOML configuration requires Python 3.11 or newer")
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        _reject_secret_keys(raw)
        unknown_top = set(raw) - {"bridge", "host_profiles"}
        if unknown_top:
            raise BridgeError(f"unknown top-level configuration keys: {sorted(unknown_top)}")
        table = raw.get("bridge", {})
        if not isinstance(table, dict):
            raise BridgeError("[bridge] must be a TOML table")
        unknown = set(table) - CONFIG_FIELDS
        if unknown:
            raise BridgeError(f"unknown bridge configuration keys: {sorted(unknown)}")
        values.update(table)
        profiles = raw.get("host_profiles", {})
        if not isinstance(profiles, dict):
            raise BridgeError("[host_profiles] must be a TOML table")
        for name, profile in profiles.items():
            if not RUN_ID_RE.fullmatch(str(name)):
                raise BridgeError(f"host profile name is invalid: {name!r}")
            if not isinstance(profile, dict):
                raise BridgeError(f"host profile {name!r} must be a TOML table")
            unknown_profile = set(profile) - CONFIG_FIELDS - HOST_PROFILE_METADATA_FIELDS
            if unknown_profile:
                raise BridgeError(
                    f"unknown keys in host profile {name!r}: {sorted(unknown_profile)}"
                )
    elif explicit:
        raise BridgeError(f"configuration file does not exist: {path}")
    if host_profile is not None:
        if host_profile not in profiles:
            raise BridgeError(
                f"unknown host profile {host_profile!r}; available: {sorted(profiles)}"
            )
        selected = profiles[host_profile]
        values.update({key: value for key, value in selected.items() if key in CONFIG_FIELDS})
        machine_id = str(selected.get("machine_id", host_profile))
        if not RUN_ID_RE.fullmatch(machine_id):
            raise BridgeError(f"machine_id is invalid in host profile {host_profile!r}")
        role = selected.get("role")
        notes = selected.get("notes")
        if role is not None and not isinstance(role, str):
            raise BridgeError(f"role must be a string in host profile {host_profile!r}")
        if notes is not None and not isinstance(notes, str):
            raise BridgeError(f"notes must be a string in host profile {host_profile!r}")
        host_role = role
    if overrides:
        values.update({key: value for key, value in overrides.items() if value is not None})
    try:
        return validate_config(
            BridgeConfig(
                **values,
                host_profile=host_profile,
                machine_id=machine_id,
                host_role=host_role,
                available_host_profiles=tuple(sorted(profiles)),
            )
        )
    except (TypeError, ValueError) as exc:
        raise BridgeError(f"invalid bridge configuration: {exc}") from exc


def discover_repo_root(runner: SystemRunner) -> Path:
    if find_executable("git"):
        result = runner.run(["git", "rev-parse", "--show-toplevel"])
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    fallback = Path(__file__).resolve().parents[2]
    if (fallback / ".git").exists():
        return fallback
    raise BridgeError("could not locate the sktlm repository root")


def local_git_status(repo_root: Path, runner: SystemRunner) -> dict[str, Any]:
    if not find_executable("git"):
        return {"available": False, "status": "MISSING"}
    commands = {
        "head": ["git", "rev-parse", "HEAD"],
        "branch": ["git", "branch", "--show-current"],
        "porcelain": ["git", "status", "--porcelain"],
    }
    results = {name: runner.run(argv, cwd=repo_root) for name, argv in commands.items()}
    if any(result.returncode != 0 for result in results.values()):
        return {"available": False, "status": "ERROR"}
    porcelain = results["porcelain"].stdout
    return {
        "available": True,
        "repository_root": str(repo_root),
        "branch": results["branch"].stdout.strip(),
        "head": results["head"].stdout.strip(),
        "dirty": bool(porcelain.strip()),
        "status_entries": len(porcelain.splitlines()),
    }


def _tree_availability(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {"available": False, "files": 0, "path": str(path)}
    try:
        file_count = sum(1 for item in path.rglob("*") if item.is_file())
    except OSError as exc:
        return {"available": False, "files": None, "path": str(path), "error": str(exc)}
    return {"available": True, "files": file_count, "path": str(path)}


def local_status(repo_root: Path, runner: SystemRunner) -> dict[str, Any]:
    result = local_git_status(repo_root, runner)
    result["canonical"] = _tree_availability(repo_root / "data/canonical/gretil_iast")
    result["representations"] = _tree_availability(repo_root / "data/representations")
    result["canonical_manifest_available"] = (
        repo_root / "data/manifests/canonical_corpus.csv"
    ).is_file()
    result["representation_manifest_available"] = (
        repo_root / "data/manifests/representations.csv"
    ).is_file()
    try:
        usage = shutil.disk_usage(repo_root)
        result["filesystem"] = {"total_bytes": usage.total, "free_bytes": usage.free}
    except OSError as exc:
        result["filesystem"] = {"error": str(exc)}
    return result


def require_remote_config(config: BridgeConfig) -> None:
    if not config.remote_ready:
        raise BridgeError("host and remote_repo must be configured for this command")


def ssh_argv(config: BridgeConfig, script: str) -> list[str]:
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-p",
        str(config.port),
    ]
    if config.identity_file:
        argv.extend(["-i", config.identity_file])
    argv.extend(["--", config.target, "sh -c " + shlex.quote(script)])
    return argv


def run_ssh(
    config: BridgeConfig,
    script: str,
    runner: SystemRunner,
) -> subprocess.CompletedProcess[str]:
    return runner.run(ssh_argv(config, script))


def _parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def build_remote_status_script(config: BridgeConfig) -> str:
    require_remote_config(config)
    return f"""
repo={shlex.quote(config.remote_repo or '')}
mount={shlex.quote(config.remote_data_mount)}
cloud={shlex.quote(config.remote_cloud_root)}
printf 'hostname=%s\\n' "$(hostname 2>/dev/null || printf MISSING)"
if command -v git >/dev/null 2>&1; then
  printf 'git_available=true\\n'
  printf 'git_version=%s\\n' "$(git --version 2>/dev/null || printf ERROR)"
else
  printf 'git_available=false\\n'
  printf 'git_version=MISSING\\n'
fi
if command -v python3.11 >/dev/null 2>&1; then
  printf 'python311_available=true\\n'
  printf 'python311_version=%s\\n' "$(python3.11 --version 2>&1 || printf ERROR)"
else
  printf 'python311_available=false\\n'
  printf 'python311_version=MISSING\\n'
fi
if [ -d "$repo/.git" ]; then
  printf 'repo_exists=true\\n'
  if command -v git >/dev/null 2>&1; then
    printf 'repo_head=%s\\n' "$(git -C "$repo" rev-parse HEAD 2>/dev/null || printf ERROR)"
    printf 'repo_branch=%s\\n' "$(git -C "$repo" branch --show-current 2>/dev/null || printf ERROR)"
    if [ -n "$(git -C "$repo" status --porcelain 2>/dev/null)" ]; then
      printf 'repo_dirty=true\\n'
    else
      printf 'repo_dirty=false\\n'
    fi
  fi
else
  printf 'repo_exists=false\\n'
  printf 'repo_head=MISSING\\n'
  printf 'repo_branch=MISSING\\n'
  printf 'repo_dirty=MISSING\\n'
fi
if command -v findmnt >/dev/null 2>&1; then
  printf 'data_source=%s\\n' "$(findmnt -n -o SOURCE -T "$mount" 2>/dev/null || printf MISSING)"
  printf 'data_target=%s\\n' "$(findmnt -n -o TARGET -T "$mount" 2>/dev/null || printf MISSING)"
  printf 'data_fstype=%s\\n' "$(findmnt -n -o FSTYPE -T "$mount" 2>/dev/null || printf MISSING)"
else
  printf 'data_source=MISSING\\n'
  printf 'data_target=MISSING\\n'
  printf 'data_fstype=MISSING\\n'
fi
if disk_free=$(df -B1 --output=avail "$mount" 2>/dev/null); then
  printf 'data_free_bytes=%s\\n' "$(printf '%s\\n' "$disk_free" | tail -n 1 | tr -d ' ')"
else
  printf 'data_free_bytes=MISSING\\n'
fi
if [ -d "$cloud/data/canonical/gretil_iast" ]; then printf 'canonical_available=true\\n'; else printf 'canonical_available=false\\n'; fi
if [ -d "$cloud/data/representations" ]; then printf 'representations_available=true\\n'; else printf 'representations_available=false\\n'; fi
verification="$cloud/artifacts/cloud_input_verification.json"
if [ -f "$verification" ]; then
  printf 'input_verification_available=true\\n'
  if grep -Eq '"valid"[[:space:]]*:[[:space:]]*true' "$verification"; then printf 'input_verification_valid=true\\n'; else printf 'input_verification_valid=false\\n'; fi
else
  printf 'input_verification_available=false\\n'
  printf 'input_verification_valid=MISSING\\n'
fi
""".strip()


def remote_status(config: BridgeConfig, runner: SystemRunner) -> dict[str, Any]:
    if not config.remote_ready:
        return {"configured": False, "reachable": False, "status": "MISSING_CONFIG"}
    if not find_executable("ssh"):
        return {"configured": True, "reachable": False, "status": "SSH_MISSING"}
    result = run_ssh(config, build_remote_status_script(config), runner)
    if result.returncode != 0:
        return {
            "configured": True,
            "reachable": False,
            "status": "UNREACHABLE",
            "ssh_return_code": result.returncode,
        }
    values = _parse_key_values(result.stdout)
    converted: dict[str, Any] = {"configured": True, "reachable": True}
    for key, value in values.items():
        if value in {"true", "false"}:
            converted[key] = value == "true"
        elif key in {"data_free_bytes"} and value.isdigit():
            converted[key] = int(value)
        else:
            converted[key] = value
    return converted


def status_snapshot(
    repo_root: Path,
    config: BridgeConfig,
    runner: SystemRunner,
) -> dict[str, Any]:
    return {
        "schema": "sktlm-cloud-status/v1",
        "host_selection": {
            "host_profile": config.host_profile,
            "machine_id": config.machine_id,
            "role": config.host_role,
            "available_profiles": list(config.available_host_profiles),
        },
        "local": local_status(repo_root, runner),
        "remote": remote_status(config, runner),
    }


def require_tool(name: str) -> str:
    executable = find_executable(name)
    if executable is None:
        raise BridgeError(f"required system tool is missing: {name}")
    return executable


def require_transfer_platform() -> None:
    if platform.system() == "Windows":
        raise BridgeError(
            "rsync transfer commands require Linux/WSL; run sktlm_bridge.py inside WSL"
        )


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id) or run_id in {".", ".."}:
        raise BridgeError(
            "run ID must use only letters, digits, '.', '_', or '-' and may not traverse paths"
        )
    return run_id


def collection_registry_assignment(
    repo_root: Path,
    config: BridgeConfig,
    run_id: str,
    metrics_id: str,
) -> dict[str, Any] | None:
    """Require an exact logical host/run match when multi-host profiles exist."""
    if not config.available_host_profiles:
        return None
    if config.host_profile is None:
        raise BridgeError(
            "multiple host profiles are configured; collection requires --host-profile"
        )
    if tomllib is None:
        raise BridgeError("experiment registry validation requires Python 3.11 or newer")
    registry_path = repo_root / REGISTRY_RELATIVE_PATH
    if not registry_path.is_file():
        raise BridgeError(f"experiment registry is missing: {registry_path}")
    raw = tomllib.loads(registry_path.read_text(encoding="utf-8"))
    runs = raw.get("runs")
    if not isinstance(runs, list):
        raise BridgeError("experiment registry must contain [[runs]] entries")
    matches = [row for row in runs if isinstance(row, dict) and row.get("run_id") == run_id]
    if len(matches) != 1:
        raise BridgeError(f"run ID must have exactly one registry assignment: {run_id}")
    assignment = matches[0]
    expected_profile = assignment.get("host_profile")
    expected_machine = assignment.get("machine_id")
    expected_metrics = assignment.get("metrics_id")
    if expected_profile != config.host_profile:
        raise BridgeError(
            f"run {run_id!r} is assigned to host profile {expected_profile!r}, "
            f"not {config.host_profile!r}"
        )
    if config.machine_id is not None and expected_machine != config.machine_id:
        raise BridgeError(
            f"run {run_id!r} is assigned to machine {expected_machine!r}, "
            f"not {config.machine_id!r}"
        )
    if expected_metrics != metrics_id:
        raise BridgeError(
            f"run {run_id!r} uses metrics ID {expected_metrics!r}, not {metrics_id!r}"
        )
    return {
        "registry": REGISTRY_RELATIVE_PATH.as_posix(),
        "machine_id": expected_machine,
        "host_profile": expected_profile,
        "run_id": run_id,
        "metrics_id": metrics_id,
        "state_at_collection": assignment.get("state"),
    }


def _controlled_failure(result: subprocess.CompletedProcess[str], label: str) -> BridgeError:
    detail = (result.stderr or result.stdout).strip().splitlines()
    suffix = f": {detail[-1]}" if detail else ""
    return BridgeError(f"{label} failed with exit code {result.returncode}{suffix}")


def parse_json_output(text: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BridgeError(f"{label} did not emit one JSON document: {exc}") from exc
    if not isinstance(payload, dict):
        raise BridgeError(f"{label} JSON must be an object")
    return payload


def interpret_input_validation(payload: Mapping[str, Any]) -> list[str]:
    failures = [
        f"{key}: found {payload.get(key)!r}, expected {expected!r}"
        for key, expected in EXPECTED_VALIDATION.items()
        if payload.get(key) != expected
    ]
    reported = payload.get("failures")
    if isinstance(reported, list):
        failures.extend(str(item) for item in reported if str(item) not in failures)
    return failures


def run_local_input_validation(
    repo_root: Path,
    runner: SystemRunner,
) -> dict[str, Any]:
    command = [sys.executable, "scripts/cloud/verify_inputs.py"]
    result = runner.run(command, cwd=repo_root)
    payload = parse_json_output(result.stdout, "local input validator")
    failures = interpret_input_validation(payload)
    if result.returncode != 0 or failures:
        raise BridgeError("local frozen-input validation failed: " + "; ".join(failures))
    return payload


def build_remote_verify_script(config: BridgeConfig) -> str:
    require_remote_config(config)
    return f"""
set -eu
repo={shlex.quote(config.remote_repo or '')}
if [ ! -d "$repo/.git" ]; then printf 'remote repository: MISSING\\n' >&2; exit 4; fi
if [ ! -x "$repo/.venv/bin/python" ]; then printf 'remote Python venv: MISSING\\n' >&2; exit 5; fi
cd "$repo"
exec ./.venv/bin/python scripts/cloud/verify_inputs.py
""".strip()


def verify_remote_inputs(
    config: BridgeConfig,
    runner: SystemRunner,
) -> dict[str, Any]:
    require_tool("ssh")
    result = run_ssh(config, build_remote_verify_script(config), runner)
    if not result.stdout.strip():
        raise _controlled_failure(result, "remote input validator")
    payload = parse_json_output(result.stdout, "remote input validator")
    failures = interpret_input_validation(payload)
    if result.returncode != 0 or failures:
        raise BridgeError("remote frozen-input validation failed: " + "; ".join(failures))
    return payload


def build_remote_head_script(config: BridgeConfig) -> str:
    require_remote_config(config)
    return f"""
repo={shlex.quote(config.remote_repo or '')}
if ! command -v git >/dev/null 2>&1; then printf 'git: MISSING\\n' >&2; exit 127; fi
if [ ! -d "$repo/.git" ]; then printf 'repository: MISSING\\n' >&2; exit 4; fi
git -C "$repo" rev-parse HEAD
""".strip()


def remote_repo_head(config: BridgeConfig, runner: SystemRunner) -> str:
    result = run_ssh(config, build_remote_head_script(config), runner)
    if result.returncode != 0:
        raise _controlled_failure(result, "remote HEAD query")
    head = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise BridgeError(f"remote HEAD query returned an invalid SHA: {head!r}")
    return head


def build_remote_mount_check_script(config: BridgeConfig) -> str:
    require_remote_config(config)
    return f"""
set -eu
mount={shlex.quote(config.remote_data_mount)}
cloud={shlex.quote(config.remote_cloud_root)}
if ! command -v findmnt >/dev/null 2>&1; then printf 'findmnt: MISSING\\n' >&2; exit 6; fi
if [ ! -d "$mount" ]; then printf 'data mount: MISSING\\n' >&2; exit 7; fi
mount_real=$(readlink -f "$mount")
target=$(findmnt -n -o TARGET -T "$mount")
target_real=$(readlink -f "$target")
source=$(findmnt -n -o SOURCE -T "$mount")
fstype=$(findmnt -n -o FSTYPE -T "$mount")
if [ "$target_real" = "/" ] || [ "$target_real" != "$mount_real" ]; then
  printf 'configured data path is not its own non-root mount: %s\\n' "$target" >&2
  exit 8
fi
if [ ! -d "$cloud" ]; then printf 'cloud root: MISSING (run bootstrap first)\\n' >&2; exit 10; fi
cloud_real=$(readlink -f "$cloud")
case "$cloud_real" in "$mount_real"/*) ;; *) printf 'cloud root resolves outside data mount\\n' >&2; exit 9;; esac
printf 'data_source=%s\\n' "$source"
printf 'data_target=%s\\n' "$target"
printf 'data_fstype=%s\\n' "$fstype"
printf 'data_free_bytes=%s\\n' "$(df -B1 --output=avail "$mount" | tail -n 1 | tr -d ' ')"
""".strip()


def check_remote_data_mount(
    config: BridgeConfig,
    runner: SystemRunner,
) -> dict[str, Any]:
    result = run_ssh(config, build_remote_mount_check_script(config), runner)
    if result.returncode != 0:
        raise _controlled_failure(result, "remote data-mount check")
    values = _parse_key_values(result.stdout)
    if values.get("data_target") != config.remote_data_mount:
        raise BridgeError("remote data-mount check returned an unexpected target")
    if values.get("data_free_bytes", "").isdigit():
        values["data_free_bytes"] = int(values["data_free_bytes"])  # type: ignore[assignment]
    return values


def _remote_endpoint(config: BridgeConfig) -> str:
    host = config.host or ""
    if ":" in host and not (host.startswith("[") and host.endswith("]")):
        host = f"[{host}]"
    return f"{config.user}@{host}" if config.user else host


def _rsync_ssh_transport(config: BridgeConfig) -> str:
    argv = ["ssh", "-o", "BatchMode=yes", "-p", str(config.port)]
    if config.identity_file:
        argv.extend(["-i", config.identity_file])
    return shlex.join(argv)


def _remote_mount_guard(
    config: BridgeConfig,
    guarded_path: str | None = None,
) -> str:
    path_check = ""
    if guarded_path is not None:
        path_check = f"""
path={shlex.quote(guarded_path)}
if [ ! -e "$path" ]; then printf 'guarded rsync path: MISSING\\n' >&2; exit 11; fi
path_real=$(readlink -f "$path")
case "$path_real" in "$cloud_real"|"$cloud_real"/*) ;; *) printf 'rsync path resolves outside cloud data root\\n' >&2; exit 12;; esac
""".strip()
    return f"""
mount={shlex.quote(config.remote_data_mount)}
cloud={shlex.quote(config.remote_cloud_root)}
if ! command -v findmnt >/dev/null 2>&1; then printf 'findmnt: MISSING\\n' >&2; exit 6; fi
mount_real=$(readlink -f "$mount")
target=$(findmnt -n -o TARGET -T "$mount")
target_real=$(readlink -f "$target")
if [ "$target_real" = "/" ] || [ "$target_real" != "$mount_real" ]; then
  printf 'configured data path is not its own non-root mount: %s\\n' "$target" >&2
  exit 8
fi
if [ ! -d "$cloud" ]; then printf 'cloud root: MISSING (run bootstrap first)\\n' >&2; exit 10; fi
cloud_real=$(readlink -f "$cloud")
case "$cloud_real" in "$mount_real"/*) ;; *) printf 'cloud root resolves outside data mount\\n' >&2; exit 9;; esac
{path_check}
""".strip()


def _remote_rsync_path(config: BridgeConfig, guarded_path: str) -> str:
    guarded = _remote_mount_guard(config, guarded_path) + '\nexec rsync "$@"'
    return "sh -c " + shlex.quote(guarded) + " sh"


def build_rsync_argv(
    config: BridgeConfig,
    *,
    source: Path | str,
    destination: Path | str,
    direction: str,
    includes: Sequence[str] | None = None,
) -> list[str]:
    if direction not in {"push", "pull"}:
        raise BridgeError(f"unsupported rsync direction: {direction}")
    remote_path = destination if direction == "push" else source
    normalized_remote_path = _normalize_remote_path(str(remote_path), "remote rsync path")
    base = [
        "rsync",
        "-a",
        "--partial",
        "--protect-args",
        "--itemize-changes",
        "--out-format=SKTLM\t%i\t%l\t%n%L",
        "--rsync-path",
        _remote_rsync_path(config, normalized_remote_path),
        "-e",
        _rsync_ssh_transport(config),
    ]
    if includes is not None:
        base.append("--prune-empty-dirs")
        base.extend(f"--include=/{name}" for name in includes)
        base.append("--exclude=*")
    endpoint = _remote_endpoint(config)
    if direction == "push":
        local_source = str(Path(source).resolve()).replace(os.sep, "/").rstrip("/") + "/"
        remote_destination = normalized_remote_path.rstrip("/") + "/"
        operands = [local_source, f"{endpoint}:{remote_destination}"]
    else:
        remote_source = normalized_remote_path.rstrip("/") + "/"
        local_destination = str(Path(destination).resolve()).replace(os.sep, "/").rstrip("/") + "/"
        operands = [f"{endpoint}:{remote_source}", local_destination]
    return [*base, "--", *operands]


def public_argv(argv: Sequence[str]) -> list[str]:
    public: list[str] = []
    hide_next = False
    for item in argv:
        if hide_next:
            public.append("<redacted-transport>")
            hide_next = False
        elif item in {"-i", "-e"}:
            public.append(item)
            hide_next = True
        else:
            public.append(item)
    return public


def parse_rsync_records(output: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.startswith("SKTLM\t"):
            continue
        parts = line.split("\t", 3)
        if len(parts) != 4:
            continue
        try:
            length = int(parts[2])
        except ValueError:
            length = None  # type: ignore[assignment]
        records.append({"itemized": parts[1], "bytes": length, "path": parts[3]})
    return records


def _tree_summary(path: Path) -> dict[str, int]:
    files = 0
    total_bytes = 0
    for item in path.rglob("*"):
        if item.is_file():
            files += 1
            total_bytes += item.stat().st_size
    return {"files": files, "bytes": total_bytes}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _redact_payload(value: Any, sensitive_values: Sequence[str]) -> Any:
    if isinstance(value, dict):
        return {key: _redact_payload(nested, sensitive_values) for key, nested in value.items()}
    if isinstance(value, list):
        return [_redact_payload(nested, sensitive_values) for nested in value]
    if isinstance(value, tuple):
        return [_redact_payload(nested, sensitive_values) for nested in value]
    if isinstance(value, str):
        redacted = value
        for sensitive in sensitive_values:
            if sensitive:
                redacted = redacted.replace(sensitive, "<redacted>")
        return redacted
    return value


def config_sensitive_values(config: BridgeConfig) -> tuple[str, ...]:
    if not config.identity_file:
        return ()
    identity = config.identity_file
    backslash = chr(92)
    return tuple(
        dict.fromkeys(
            (identity, identity.replace(backslash, "/"), identity.replace("/", backslash))
        )
    )


def write_receipt(
    repo_root: Path,
    payload: Mapping[str, Any],
    *,
    sensitive_values: Sequence[str] = (),
) -> Path:
    receipt_dir = repo_root / "artifacts/cloud_transfers"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    timestamp = str(payload.get("finished_at") or utc_now())
    stamp = re.sub(r"[^0-9TZ]", "", timestamp)
    operation = re.sub(r"[^a-z0-9_-]", "-", str(payload.get("operation", "operation")))
    base = receipt_dir / f"{stamp}_{operation}.json"
    path = base
    counter = 1
    while path.exists():
        path = receipt_dir / f"{base.stem}_{counter}.json"
        counter += 1
    cleaned = _redact_payload(dict(payload), sensitive_values)
    serialized = json.dumps(cleaned, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(serialized, encoding="utf-8", newline="")
    os.replace(temporary, path)
    return path


def base_receipt(
    operation: str,
    direction: str,
    repo_root: Path,
    config: BridgeConfig,
    runner: SystemRunner,
) -> dict[str, Any]:
    git = local_git_status(repo_root, runner)
    return {
        "schema": SCHEMA_VERSION,
        "operation": operation,
        "direction": direction,
        "started_at": utc_now(),
        "finished_at": None,
        "local_git": {
            "branch": git.get("branch"),
            "head": git.get("head"),
            "dirty": git.get("dirty"),
        },
        "remote_host": config.target if config.host else None,
        "remote_ssh_port": config.port if config.host else None,
        "host_profile": config.host_profile,
        "machine_id": config.machine_id,
        "host_role": config.host_role,
        "remote_repo_head": None,
        "valid": False,
        "failures": [],
        "warnings": [],
    }


def execute_receipted(
    operation: str,
    direction: str,
    repo_root: Path,
    config: BridgeConfig,
    runner: SystemRunner,
    action: Callable[[dict[str, Any]], Mapping[str, Any]],
) -> tuple[dict[str, Any], Path, BridgeError | None]:
    receipt = base_receipt(operation, direction, repo_root, config, runner)
    error: BridgeError | None = None
    try:
        details = dict(action(receipt))
        receipt.update(details)
        if not receipt.get("failures") and "valid" not in details:
            receipt["valid"] = True
    except BridgeError as exc:
        error = exc
        receipt.setdefault("failures", []).append(str(exc))
        receipt["valid"] = False
    except OSError as exc:
        error = BridgeError(f"local filesystem/process operation failed: {exc}")
        receipt.setdefault("failures", []).append(str(error))
        receipt["valid"] = False
    receipt["finished_at"] = utc_now()
    receipt_path = write_receipt(
        repo_root,
        receipt,
        sensitive_values=config_sensitive_values(config),
    )
    return receipt, receipt_path, error


def build_deploy_script(config: BridgeConfig, expected_head: str) -> str:
    require_remote_config(config)
    if not re.fullmatch(r"[0-9a-f]{40}", expected_head):
        raise BridgeError("expected deploy HEAD must be a full lowercase SHA-1")
    remote_repo = config.remote_repo or ""
    parent = str(PurePosixPath(remote_repo).parent)
    return f"""
set -eu
repo={shlex.quote(remote_repo)}
parent={shlex.quote(parent)}
branch={shlex.quote(config.branch)}
url={shlex.quote(config.repository_url)}
expected={shlex.quote(expected_head)}
if ! command -v git >/dev/null 2>&1; then printf 'git: MISSING\\n' >&2; exit 127; fi
if [ -e "$repo" ] && [ ! -d "$repo/.git" ]; then printf 'remote repo path exists but is not a Git repository\\n' >&2; exit 3; fi
if [ ! -d "$repo/.git" ]; then
  mkdir -p "$parent"
  git clone --branch "$branch" --single-branch -- "$url" "$repo"
fi
if [ -n "$(git -C "$repo" status --porcelain)" ]; then printf 'remote repository is dirty\\n' >&2; exit 4; fi
git -C "$repo" fetch --prune origin "$branch:refs/remotes/origin/$branch"
if git -C "$repo" show-ref --verify --quiet "refs/heads/$branch"; then
  git -C "$repo" switch "$branch"
else
  git -C "$repo" switch --track -c "$branch" "origin/$branch"
fi
git -C "$repo" merge --ff-only "$expected"
actual=$(git -C "$repo" rev-parse HEAD)
if [ "$actual" != "$expected" ]; then printf 'HEAD mismatch: expected %s found %s\\n' "$expected" "$actual" >&2; exit 5; fi
printf 'deployed_head=%s\\n' "$actual"
""".strip()


def _parse_ls_remote_head(output: str, branch: str) -> str | None:
    expected_ref = f"refs/heads/{branch}"
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1] == expected_ref and re.fullmatch(r"[0-9a-f]{40}", fields[0]):
            return fields[0]
    return None


def deploy_code_action(
    receipt: dict[str, Any],
    config: BridgeConfig,
    repo_root: Path,
    runner: SystemRunner,
    *,
    allow_dirty: bool,
    allow_unpushed: bool,
) -> Mapping[str, Any]:
    require_remote_config(config)
    require_tool("git")
    require_tool("ssh")
    local = local_git_status(repo_root, runner)
    if not local.get("available"):
        raise BridgeError("local Git repository is unavailable")
    if local.get("branch") != config.branch:
        raise BridgeError(
            f"local branch is {local.get('branch')!r}, expected {config.branch!r}"
        )
    if local.get("dirty") and not allow_dirty:
        raise BridgeError("local repository is dirty; commit/stash changes before deploy-code")
    if local.get("dirty"):
        receipt["warnings"].append("diagnostic override: local repository was dirty")
    local_head = str(local.get("head"))
    remote_ref = runner.run(
        ["git", "ls-remote", "--heads", config.repository_url, f"refs/heads/{config.branch}"],
        cwd=repo_root,
        env={"GIT_TERMINAL_PROMPT": "0"},
    )
    if remote_ref.returncode != 0:
        raise _controlled_failure(remote_ref, "GitHub branch query")
    pushed_head = _parse_ls_remote_head(remote_ref.stdout, config.branch)
    if pushed_head != local_head and not allow_unpushed:
        raise BridgeError(
            f"local HEAD {local_head} is not the published branch HEAD {pushed_head or 'MISSING'}"
        )
    if pushed_head != local_head:
        receipt["warnings"].append("diagnostic override: local HEAD was not branch HEAD on GitHub")
    script = build_deploy_script(config, local_head)
    command = ssh_argv(config, script)
    receipt["command"] = public_argv(command)
    result = runner.run(command)
    receipt["ssh_return_code"] = result.returncode
    if result.returncode != 0:
        raise _controlled_failure(result, "remote code deployment")
    deployed = _parse_key_values(result.stdout).get("deployed_head")
    if deployed != local_head:
        raise BridgeError(
            f"remote deployment did not verify exact HEAD: expected {local_head}, found {deployed!r}"
        )
    return {
        "valid": True,
        "deployed_head": deployed,
        "remote_repo_head": deployed,
        "published_branch_head": pushed_head,
    }


def build_prepare_input_dirs_script(config: BridgeConfig) -> str:
    data_root = posixpath.join(config.remote_cloud_root, "data")
    canonical = posixpath.join(
        config.remote_cloud_root, "data/canonical/gretil_iast"
    )
    representations = posixpath.join(config.remote_cloud_root, "data/representations")
    return f"""
set -eu
{_remote_mount_guard(config)}
data_root={shlex.quote(data_root)}
if [ -e "$data_root" ]; then
  data_real=$(readlink -f "$data_root")
  case "$data_real" in "$cloud_real"/*) ;; *) printf 'input data root resolves outside cloud data root\\n' >&2; exit 13;; esac
fi
mkdir -p -- {shlex.quote(canonical)} {shlex.quote(representations)}
for path in {shlex.quote(canonical)} {shlex.quote(representations)}; do
  path_real=$(readlink -f "$path")
  case "$path_real" in "$cloud_real"/*) ;; *) printf 'input destination resolves outside cloud data root\\n' >&2; exit 14;; esac
done
printf 'input_destinations_ready=true\\n'
""".strip()


def _run_rsync(
    argv: Sequence[str],
    runner: SystemRunner,
    receipt: dict[str, Any],
    label: str,
) -> list[dict[str, Any]]:
    result = runner.run(argv)
    transfer = {
        "label": label,
        "command": public_argv(argv),
        "return_code": result.returncode,
        "records": parse_rsync_records(result.stdout),
    }
    receipt.setdefault("transfers", []).append(transfer)
    if result.returncode != 0:
        raise _controlled_failure(result, f"rsync {label}")
    return transfer["records"]


def push_inputs_action(
    receipt: dict[str, Any],
    config: BridgeConfig,
    repo_root: Path,
    runner: SystemRunner,
    *,
    verify_after: bool,
) -> Mapping[str, Any]:
    require_remote_config(config)
    require_transfer_platform()
    require_tool("git")
    require_tool("ssh")
    require_tool("rsync")
    local = local_git_status(repo_root, runner)
    if not local.get("available"):
        raise BridgeError("local Git repository is unavailable")
    if local.get("dirty"):
        raise BridgeError("local repository is dirty; tracked manifests must match deployed code")
    if local.get("branch") != config.branch:
        raise BridgeError(
            f"local branch is {local.get('branch')!r}, expected {config.branch!r}"
        )
    local_head = str(local.get("head"))
    remote_head = remote_repo_head(config, runner)
    receipt["remote_repo_head"] = remote_head
    if remote_head != local_head:
        raise BridgeError(
            f"remote repo HEAD {remote_head} does not match local HEAD {local_head}; deploy-code first"
        )

    validation = run_local_input_validation(repo_root, runner)
    receipt["local_input_validation"] = validation
    receipt["freeze_id"] = validation.get("freeze_id")
    receipt["remote_mount"] = check_remote_data_mount(config, runner)

    canonical_source = repo_root / "data/canonical/gretil_iast"
    representations_source = repo_root / "data/representations"
    if not canonical_source.is_dir() or not representations_source.is_dir():
        raise BridgeError("validated local input directories are unavailable")
    canonical_destination = posixpath.join(
        config.remote_cloud_root, "data/canonical/gretil_iast"
    )
    representations_destination = posixpath.join(
        config.remote_cloud_root, "data/representations"
    )
    for destination in (canonical_destination, representations_destination):
        if not _is_remote_child(destination, config.remote_cloud_root):
            raise BridgeError(f"input destination escapes remote cloud root: {destination}")

    prepare = run_ssh(config, build_prepare_input_dirs_script(config), runner)
    receipt["prepare_destinations_return_code"] = prepare.returncode
    if prepare.returncode != 0:
        raise _controlled_failure(prepare, "remote input-destination preparation")

    receipt["input_sets"] = {
        "canonical_m0": {
            "source": "data/canonical/gretil_iast/",
            "destination": canonical_destination + "/",
            **_tree_summary(canonical_source),
        },
        "representations": {
            "source": "data/representations/",
            "destination": representations_destination + "/",
            **_tree_summary(representations_source),
        },
    }
    canonical_command = build_rsync_argv(
        config,
        source=canonical_source,
        destination=canonical_destination,
        direction="push",
    )
    representations_command = build_rsync_argv(
        config,
        source=representations_source,
        destination=representations_destination,
        direction="push",
    )
    _run_rsync(canonical_command, runner, receipt, "canonical_m0")
    _run_rsync(representations_command, runner, receipt, "representations")

    remote_validation: dict[str, Any] | None = None
    if verify_after:
        remote_validation = verify_remote_inputs(config, runner)
        receipt["remote_input_validation"] = remote_validation
    else:
        receipt["warnings"].append("remote validation skipped by --no-verify")
    return {
        "valid": True,
        "remote_repo_head": remote_head,
        "remote_validator_result": remote_validation,
    }


def profile_files(profile: str) -> tuple[tuple[str, ...] | None, tuple[str, ...] | None]:
    if profile == "report":
        return REPORT_RUN_FILES, REPORT_METRICS_FILES
    if profile == "scientific":
        run_files = tuple(dict.fromkeys((*REPORT_RUN_FILES, *SCIENTIFIC_FILES)))
        return run_files, REPORT_METRICS_FILES
    if profile == "full":
        return None, None
    raise BridgeError(f"unknown result profile: {profile}")


def _result_paths(config: BridgeConfig, run_id: str, metrics_id: str) -> tuple[str, str]:
    remote_repo = config.remote_repo or ""
    run_path = posixpath.join(remote_repo, "artifacts/latent_benchmarks", run_id)
    metrics_path = posixpath.join(remote_repo, "artifacts/cloud_metrics", metrics_id)
    return run_path, metrics_path


def build_result_probe_script(
    config: BridgeConfig,
    run_id: str,
    metrics_id: str,
) -> str:
    run_path, metrics_path = _result_paths(config, run_id, metrics_id)
    return f"""
run={shlex.quote(run_path)}
metrics={shlex.quote(metrics_path)}
if [ -d "$run" ]; then printf 'run_exists=true\\n'; else printf 'run_exists=false\\n'; fi
if [ -d "$metrics" ]; then printf 'metrics_exists=true\\n'; else printf 'metrics_exists=false\\n'; fi
""".strip()


def _local_collection_root(
    repo_root: Path,
    output_root: Path | None,
    run_id: str,
) -> Path:
    base = output_root or (repo_root / "artifacts/cloud_collected")
    if not base.is_absolute():
        base = repo_root / base
    destination = (base.resolve() / run_id).resolve()
    if destination == repo_root:
        raise BridgeError("collection destination may not be the repository root")
    if destination.exists():
        raise BridgeError(f"local collected result already exists; refusing overwrite: {destination}")
    return destination


def _inventory_collected_files(root: Path, profile: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    hash_names = set(REPORT_RUN_FILES) | set(REPORT_METRICS_FILES) | set(SCIENTIFIC_FILES)
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        row: dict[str, Any] = {"path": relative, "bytes": path.stat().st_size}
        if profile != "full" or path.name in hash_names or path.stat().st_size <= 10 * 1024 * 1024:
            row["sha256"] = file_sha256(path)
        else:
            row["sha256"] = None
            row["hash_note"] = "omitted for noncanonical full-profile file above 10 MiB"
        rows.append(row)
    return rows


def transfer_results(
    receipt: dict[str, Any],
    config: BridgeConfig,
    repo_root: Path,
    runner: SystemRunner,
    *,
    run_id: str,
    metrics_id: str,
    profile: str,
    output_root: Path | None,
) -> tuple[Path, Mapping[str, Any]]:
    require_remote_config(config)
    require_transfer_platform()
    require_tool("ssh")
    require_tool("rsync")
    run_id = validate_run_id(run_id)
    metrics_id = validate_run_id(metrics_id)
    run_files, metrics_files = profile_files(profile)
    remote_head = remote_repo_head(config, runner)
    receipt["remote_repo_head"] = remote_head
    probe = run_ssh(config, build_result_probe_script(config, run_id, metrics_id), runner)
    if probe.returncode != 0:
        raise _controlled_failure(probe, "remote result probe")
    availability = _parse_key_values(probe.stdout)
    if availability.get("run_exists") != "true":
        raise BridgeError(f"remote benchmark run is missing: {run_id}")

    collection = _local_collection_root(repo_root, output_root, run_id)
    benchmark_destination = collection / "benchmark"
    metrics_destination = collection / "metrics"
    benchmark_destination.mkdir(parents=True)
    run_path, metrics_path = _result_paths(config, run_id, metrics_id)
    run_command = build_rsync_argv(
        config,
        source=run_path,
        destination=benchmark_destination,
        direction="pull",
        includes=run_files,
    )
    _run_rsync(run_command, runner, receipt, f"benchmark:{profile}")

    metrics_available = availability.get("metrics_exists") == "true"
    if metrics_available:
        metrics_destination.mkdir(parents=True)
        metrics_command = build_rsync_argv(
            config,
            source=metrics_path,
            destination=metrics_destination,
            direction="pull",
            includes=metrics_files,
        )
        _run_rsync(metrics_command, runner, receipt, f"metrics:{profile}")
    else:
        receipt["warnings"].append(f"remote metrics directory is missing: {metrics_id}")

    if run_files is not None:
        missing_run = [name for name in run_files if not (benchmark_destination / name).is_file()]
        if missing_run:
            receipt["warnings"].append(f"optional/unavailable benchmark files: {missing_run}")
    if metrics_available and metrics_files is not None:
        missing_metrics = [name for name in metrics_files if not (metrics_destination / name).is_file()]
        if missing_metrics:
            receipt["warnings"].append(f"optional/unavailable metrics files: {missing_metrics}")
    files = _inventory_collected_files(collection, profile)
    details = {
        "run_id": run_id,
        "metrics_id": metrics_id,
        "transfer_profile": profile,
        "remote_sources": {"benchmark": run_path, "metrics": metrics_path},
        "local_destination": str(collection),
        "files": files,
        "file_count": len(files),
        "byte_count": sum(int(row["bytes"]) for row in files),
        "remote_repo_head": remote_head,
    }
    receipt.update(details)
    return collection, details


def pull_results_action(
    receipt: dict[str, Any],
    config: BridgeConfig,
    repo_root: Path,
    runner: SystemRunner,
    *,
    run_id: str,
    metrics_id: str,
    profile: str,
    output_root: Path | None,
) -> Mapping[str, Any]:
    assignment = collection_registry_assignment(
        repo_root, config, validate_run_id(run_id), validate_run_id(metrics_id)
    )
    if assignment is not None:
        receipt["registry_assignment"] = assignment
    _collection, details = transfer_results(
        receipt,
        config,
        repo_root,
        runner,
        run_id=run_id,
        metrics_id=metrics_id,
        profile=profile,
        output_root=output_root,
    )
    return {**details, "valid": True}


def build_remote_audit_script(config: BridgeConfig, run_id: str) -> str:
    require_remote_config(config)
    run_path, _metrics = _result_paths(config, run_id, run_id)
    return f"""
repo={shlex.quote(config.remote_repo or '')}
run={shlex.quote(run_path)}
if [ ! -d "$repo/.git" ]; then printf 'remote repository: MISSING\\n' >&2; exit 4; fi
if [ ! -x "$repo/.venv/bin/python" ]; then printf 'remote Python venv: MISSING\\n' >&2; exit 5; fi
cd "$repo"
exec ./.venv/bin/python scripts/cloud/audit_latent_run.py "$run"
""".strip()


def remote_audit_result(
    config: BridgeConfig,
    runner: SystemRunner,
    run_id: str,
) -> dict[str, Any]:
    result = run_ssh(config, build_remote_audit_script(config, validate_run_id(run_id)), runner)
    if not result.stdout.strip():
        return {
            "valid": False,
            "failures": [str(_controlled_failure(result, "remote run audit"))],
            "ssh_return_code": result.returncode,
        }
    try:
        payload = parse_json_output(result.stdout, "remote run audit")
    except BridgeError as exc:
        return {
            "valid": False,
            "failures": [str(exc)],
            "ssh_return_code": result.returncode,
        }
    payload["ssh_return_code"] = result.returncode
    if result.returncode != 0:
        payload["valid"] = False
        payload.setdefault("failures", []).append(
            f"remote audit process exited {result.returncode}"
        )
    return payload


def validate_downloaded_audit_hashes(
    collection: Path,
    audit: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    comparisons: list[dict[str, Any]] = []
    failures: list[str] = []
    scientific = audit.get("scientific_artifacts")
    if not isinstance(scientific, dict):
        return comparisons, failures
    for name, expected in scientific.items():
        if not isinstance(expected, dict):
            continue
        local_path = collection / "benchmark" / str(name)
        if not local_path.is_file():
            continue
        actual_bytes = local_path.stat().st_size
        actual_sha256 = file_sha256(local_path)
        equal = (
            actual_bytes == expected.get("bytes")
            and actual_sha256 == expected.get("sha256")
        )
        comparisons.append(
            {
                "path": f"benchmark/{name}",
                "bytes": actual_bytes,
                "sha256": actual_sha256,
                "remote_audit_equal": equal,
            }
        )
        if not equal:
            failures.append(f"downloaded artifact differs from remote audit: {name}")
    return comparisons, failures


def collect_action(
    receipt: dict[str, Any],
    config: BridgeConfig,
    repo_root: Path,
    runner: SystemRunner,
    *,
    run_id: str,
    metrics_id: str,
    output_root: Path | None,
) -> Mapping[str, Any]:
    assignment = collection_registry_assignment(
        repo_root, config, validate_run_id(run_id), validate_run_id(metrics_id)
    )
    if assignment is not None:
        receipt["registry_assignment"] = assignment
    require_tool("ssh")
    audit = remote_audit_result(config, runner, run_id)
    receipt["remote_audit"] = audit
    collection, details = transfer_results(
        receipt,
        config,
        repo_root,
        runner,
        run_id=run_id,
        metrics_id=metrics_id,
        profile="report",
        output_root=output_root,
    )
    audit_path = collection / "remote_audit.json"
    with audit_path.open("x", encoding="utf-8", newline="") as handle:
        json.dump(audit, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    audit_file = {
        "path": "remote_audit.json",
        "bytes": audit_path.stat().st_size,
        "sha256": file_sha256(audit_path),
    }
    files = [*details["files"], audit_file]
    comparisons, hash_failures = validate_downloaded_audit_hashes(collection, audit)
    remote_only = [name for name in SCIENTIFIC_FILES if name not in REPORT_RUN_FILES]
    valid = audit.get("valid") is True and not hash_failures
    if audit.get("valid") is not True:
        receipt["failures"].append("remote scientific audit is invalid")
    receipt["failures"].extend(hash_failures)
    return {
        **details,
        "valid": valid,
        "remote_audit": audit,
        "files": files,
        "file_count": len(files),
        "byte_count": sum(int(row["bytes"]) for row in files),
        "downloaded_hash_validation": comparisons,
        "remote_only_scientific_files": remote_only,
        "full_profile_only": ["learner.sqlite", "other run/shard artifacts"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        help="TOML config (default: repository .sktlm-bridge.toml when present)",
    )
    parser.add_argument("--host", help="override remote SSH host")
    parser.add_argument("--user", help="override remote SSH user")
    parser.add_argument("--port", type=int, help="override remote SSH port")
    parser.add_argument("--identity-file", help="override SSH identity-file path")
    parser.add_argument("--remote-repo", help="override absolute remote repository path")
    parser.add_argument(
        "--remote-data-mount", help="override absolute remote data mount path"
    )
    parser.add_argument(
        "--remote-cloud-root", help="override absolute remote sktlm data root"
    )
    parser.add_argument("--branch", help="override Git branch")
    parser.add_argument("--repository-url", help="override public Git repository URL")

    host_selection = argparse.ArgumentParser(add_help=False)
    host_selection.add_argument(
        "--host-profile",
        help="select one [host_profiles.<name>] entry from the TOML config",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser(
        "status", parents=[host_selection], help="read-only local/remote status"
    )
    status.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    deploy = commands.add_parser(
        "deploy-code",
        parents=[host_selection],
        help="deploy the exact published local HEAD via GitHub",
    )
    deploy.add_argument(
        "--allow-dirty",
        action="store_true",
        help="diagnostic override; still deploys only committed HEAD",
    )
    deploy.add_argument(
        "--allow-unpushed",
        action="store_true",
        help="diagnostic override; remote fetch must still be able to obtain HEAD",
    )

    push = commands.add_parser(
        "push-inputs",
        parents=[host_selection],
        help="validate and rsync frozen non-Git inputs to the data disk",
    )
    push.add_argument(
        "--no-verify",
        action="store_true",
        help="skip the default post-transfer remote authoritative validation",
    )

    verify = commands.add_parser(
        "verify-remote",
        parents=[host_selection],
        help="run and interpret the remote authoritative input validator",
    )
    verify.add_argument("--json", action="store_true", help="emit validator JSON")

    pull = commands.add_parser(
        "pull-results",
        parents=[host_selection],
        help="selectively rsync one remote run to a new local directory",
    )
    pull.add_argument("run_id")
    pull.add_argument("--metrics-id", help="metrics directory ID (default: run ID)")
    pull.add_argument(
        "--profile",
        choices=("report", "scientific", "full"),
        default="report",
    )
    pull.add_argument("--output-root", type=Path)

    collect = commands.add_parser(
        "collect",
        parents=[host_selection],
        help="remote audit followed by report-profile collection",
    )
    collect.add_argument("run_id")
    collect.add_argument("--metrics-id", help="metrics directory ID (default: run ID)")
    collect.add_argument("--output-root", type=Path)
    return parser


def _config_overrides(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "host": args.host,
        "user": args.user,
        "port": args.port,
        "identity_file": args.identity_file,
        "remote_repo": args.remote_repo,
        "remote_data_mount": args.remote_data_mount,
        "remote_cloud_root": args.remote_cloud_root,
        "branch": args.branch,
        "repository_url": args.repository_url,
    }


def _print_human_status(snapshot: Mapping[str, Any]) -> None:
    selection = snapshot.get("host_selection", {})
    if selection.get("host_profile"):
        print(
            f"host selection: profile={selection.get('host_profile')} "
            f"machine={selection.get('machine_id')} role={selection.get('role')}"
        )
    local = snapshot["local"]
    remote = snapshot["remote"]
    if local.get("available"):
        state = "DIRTY" if local.get("dirty") else "clean"
        print(
            f"local: {local.get('branch')} {local.get('head')} {state} "
            f"repo={local.get('repository_root')}"
        )
    else:
        print(f"local: Git {local.get('status', 'MISSING')}")
    canonical = local.get("canonical", {})
    representations = local.get("representations", {})
    print(
        "local inputs: "
        f"canonical={'available' if canonical.get('available') else 'MISSING'} "
        f"representations={'available' if representations.get('available') else 'MISSING'}"
    )
    if not remote.get("reachable"):
        print(f"remote: {remote.get('status', 'UNREACHABLE')}")
        return
    repo_state = "MISSING"
    if remote.get("repo_exists"):
        repo_state = "DIRTY" if remote.get("repo_dirty") else "clean"
    print(
        f"remote: reachable hostname={remote.get('hostname')} "
        f"repo={repo_state} head={remote.get('repo_head', 'MISSING')}"
    )
    print(
        f"remote tools: git={remote.get('git_version', 'MISSING')} "
        f"python3.11={remote.get('python311_version', 'MISSING')}"
    )
    print(
        f"remote data: source={remote.get('data_source', 'MISSING')} "
        f"target={remote.get('data_target', 'MISSING')} "
        f"fstype={remote.get('data_fstype', 'MISSING')} "
        f"free_bytes={remote.get('data_free_bytes', 'MISSING')}"
    )


def _print_receipt_result(
    receipt: Mapping[str, Any],
    receipt_path: Path,
) -> None:
    print(f"operation={receipt.get('operation')}")
    print(f"valid={str(bool(receipt.get('valid'))).lower()}")
    print(f"receipt={receipt_path}")
    if receipt.get("remote_repo_head"):
        print(f"remote_repo_head={receipt.get('remote_repo_head')}")
    for warning in receipt.get("warnings", []):
        print(f"warning: {warning}")
    for failure in receipt.get("failures", []):
        print(f"failure: {failure}", file=sys.stderr)


def _run_receipted_cli(
    operation: str,
    direction: str,
    repo_root: Path,
    config: BridgeConfig,
    runner: SystemRunner,
    action: Callable[[dict[str, Any]], Mapping[str, Any]],
) -> int:
    receipt, path, error = execute_receipted(
        operation,
        direction,
        repo_root,
        config,
        runner,
        action,
    )
    safe_receipt = _redact_payload(receipt, config_sensitive_values(config))
    _print_receipt_result(safe_receipt, path)
    return 1 if error is not None or receipt.get("valid") is not True else 0


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: SystemRunner | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    active_runner = runner or SystemRunner()
    config: BridgeConfig | None = None
    try:
        repo_root = discover_repo_root(active_runner)
        config_path = args.config
        explicit_config = config_path is not None
        if config_path is None:
            config_path = repo_root / ".sktlm-bridge.toml"
        elif not config_path.is_absolute():
            config_path = (Path.cwd() / config_path).resolve()
        config = load_config(
            config_path,
            _config_overrides(args),
            explicit=explicit_config,
            host_profile=args.host_profile,
        )

        if args.command == "status":
            snapshot = status_snapshot(repo_root, config, active_runner)
            if args.json:
                print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                _print_human_status(snapshot)
            return 0
        if args.command == "verify-remote":
            result = verify_remote_inputs(config, active_runner)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(
                    "remote inputs: valid "
                    f"freeze_id={result.get('freeze_id')} "
                    f"representations={result.get('representation_files')}"
                )
            return 0
        if args.command == "deploy-code":
            return _run_receipted_cli(
                "deploy-code",
                "github_to_remote",
                repo_root,
                config,
                active_runner,
                lambda receipt: deploy_code_action(
                    receipt,
                    config,
                    repo_root,
                    active_runner,
                    allow_dirty=args.allow_dirty,
                    allow_unpushed=args.allow_unpushed,
                ),
            )
        if args.command == "push-inputs":
            return _run_receipted_cli(
                "push-inputs",
                "local_to_remote",
                repo_root,
                config,
                active_runner,
                lambda receipt: push_inputs_action(
                    receipt,
                    config,
                    repo_root,
                    active_runner,
                    verify_after=not args.no_verify,
                ),
            )
        if args.command == "pull-results":
            metrics_id = args.metrics_id or args.run_id
            return _run_receipted_cli(
                "pull-results",
                "remote_to_local",
                repo_root,
                config,
                active_runner,
                lambda receipt: pull_results_action(
                    receipt,
                    config,
                    repo_root,
                    active_runner,
                    run_id=args.run_id,
                    metrics_id=metrics_id,
                    profile=args.profile,
                    output_root=args.output_root,
                ),
            )
        if args.command == "collect":
            metrics_id = args.metrics_id or args.run_id
            return _run_receipted_cli(
                "collect",
                "remote_to_local",
                repo_root,
                config,
                active_runner,
                lambda receipt: collect_action(
                    receipt,
                    config,
                    repo_root,
                    active_runner,
                    run_id=args.run_id,
                    metrics_id=metrics_id,
                    output_root=args.output_root,
                ),
            )
        parser.error(f"unsupported command: {args.command}")
    except BridgeError as exc:
        message = str(exc)
        if config is not None:
            for sensitive in config_sensitive_values(config):
                message = message.replace(sensitive, "<redacted>")
        print(f"bridge error: {message}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
