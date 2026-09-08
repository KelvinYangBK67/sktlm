#!/usr/bin/env python3
"""Fail-closed six-host operator commands for the frozen S1M2 pre-VM plan."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import posixpath
import re
import shlex
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Mapping

from sktlm.cloud.contracts import ExperimentContract, load_experiment_contract
from sktlm.production import s1m2


BRIDGE_PATH = Path(__file__).with_name("sktlm_bridge.py")
BRIDGE_SPEC = importlib.util.spec_from_file_location(
    "_sktlm_bridge_runtime", BRIDGE_PATH
)
if BRIDGE_SPEC is None or BRIDGE_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load cloud bridge: {BRIDGE_PATH}")
bridge = importlib.util.module_from_spec(BRIDGE_SPEC)
sys.modules[BRIDGE_SPEC.name] = bridge
BRIDGE_SPEC.loader.exec_module(bridge)


SCHEMA = "sktlm-s1m2-vm-operation/v1"
CORE_HOST_ROLES = tuple(f"core-{index:02d}" for index in range(1, 7))
DEFAULT_CONTRACT = Path("configs/cloud/s1m2_prevm.yaml")
DEFAULT_PRODUCTION_CONTRACT = Path("configs/production/s1m2_six_cell.json")
SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class VmOpsError(RuntimeError):
    """A controlled S1M2 operator failure."""


def _parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_artifact_path(repo_root: Path, path: Path) -> Path:
    resolved = path if path.is_absolute() else repo_root / path
    resolved = resolved.resolve()
    artifact_root = (repo_root / "artifacts").resolve()
    if resolved == artifact_root or artifact_root not in resolved.parents:
        raise VmOpsError("operation output must be below the repository artifacts directory")
    return resolved


def _write_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise VmOpsError(f"refusing to overwrite operation receipt: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _resolve_repo_path(repo_root: Path, path: Path, *, label: str) -> tuple[Path, str]:
    resolved = path if path.is_absolute() else repo_root / path
    resolved = resolved.resolve()
    try:
        relative = resolved.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise VmOpsError(f"{label} must be inside the repository") from exc
    return resolved, relative


def load_host_configs(
    config_path: Path,
    contract: ExperimentContract,
) -> dict[str, Any]:
    configs: dict[str, Any] = {}
    endpoint_ids: set[tuple[str, int, str | None]] = set()
    for role in CORE_HOST_ROLES:
        config = bridge.load_config(
            config_path,
            explicit=True,
            host_profile=role,
        )
        config = bridge.bind_experiment_contract(config, contract)
        if (
            config.host_profile != role
            or config.machine_id != role
            or config.host_role != role
        ):
            raise VmOpsError(
                f"host profile {role} must declare machine_id and role as {role!r}"
            )
        endpoint = (config.host or "", config.port, config.user)
        if endpoint in endpoint_ids:
            raise VmOpsError("six host profiles must resolve to six distinct SSH endpoints")
        endpoint_ids.add(endpoint)
        configs[role] = config
    return configs


def _parallel(
    configs: Mapping[str, Any],
    action: Callable[[str, Any], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    def guarded(role: str) -> dict[str, Any]:
        try:
            return {"host_role": role, "valid": True, **dict(action(role, configs[role]))}
        except Exception as exc:  # aggregate every host before failing closed
            return {
                "host_role": role,
                "valid": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    with ThreadPoolExecutor(max_workers=len(CORE_HOST_ROLES)) as pool:
        futures = {role: pool.submit(guarded, role) for role in CORE_HOST_ROLES}
        return [futures[role].result() for role in CORE_HOST_ROLES]


def _identity_guard(config: Any, expected_head: str) -> str:
    if not SHA1_RE.fullmatch(expected_head):
        raise VmOpsError("expected HEAD must be a full lowercase SHA-1")
    repo = config.remote_repo or ""
    branch = bridge.require_branch(config)
    return f"""
repo={shlex.quote(repo)}
expected={shlex.quote(expected_head)}
branch={shlex.quote(branch)}
if [ ! -d "$repo/.git" ]; then printf 'repository: MISSING\\n' >&2; exit 20; fi
actual=$(git -C "$repo" rev-parse HEAD)
if [ "$actual" != "$expected" ]; then printf 'HEAD mismatch\\n' >&2; exit 21; fi
actual_branch=$(git -C "$repo" branch --show-current)
if [ "$actual_branch" != "$branch" ]; then printf 'branch mismatch\\n' >&2; exit 22; fi
if [ -n "$(git -C "$repo" status --porcelain)" ]; then printf 'dirty worktree\\n' >&2; exit 23; fi
""".strip()


def build_preflight_script(config: Any, role: str) -> str:
    repo = config.remote_repo or ""
    mount = config.remote_data_mount
    cloud = config.remote_cloud_root
    return f"""
repo={shlex.quote(repo)}
mount={shlex.quote(mount)}
cloud={shlex.quote(cloud)}
printf 'host_role=%s\\n' {shlex.quote(role)}
printf 'hostname=%s\\n' "$(hostname 2>/dev/null || printf MISSING)"
printf 'machine_identity=%s\\n' "$(cat /etc/machine-id 2>/dev/null || printf MISSING)"
printf 'boot_identity=%s\\n' "$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || printf MISSING)"
printf 'cpu_count=%s\\n' "$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf MISSING)"
printf 'ram_bytes=%s\\n' "$(awk '/^MemTotal:/ {{print $2 * 1024}}' /proc/meminfo 2>/dev/null || printf MISSING)"
printf 'data_target=%s\\n' "$(findmnt -n -o TARGET -T "$mount" 2>/dev/null || printf MISSING)"
printf 'data_source=%s\\n' "$(findmnt -n -o SOURCE -T "$mount" 2>/dev/null || printf MISSING)"
printf 'data_fstype=%s\\n' "$(findmnt -n -o FSTYPE -T "$mount" 2>/dev/null || printf MISSING)"
printf 'data_free_bytes=%s\\n' "$(df -B1 --output=avail "$mount" 2>/dev/null | tail -n 1 | tr -d ' ' || printf MISSING)"
if [ -d "$repo/.git" ]; then
  printf 'repo_exists=true\\n'
  printf 'repo_head=%s\\n' "$(git -C "$repo" rev-parse HEAD 2>/dev/null || printf ERROR)"
  printf 'repo_branch=%s\\n' "$(git -C "$repo" branch --show-current 2>/dev/null || printf ERROR)"
  if [ -n "$(git -C "$repo" status --porcelain 2>/dev/null)" ]; then printf 'repo_clean=false\\n'; else printf 'repo_clean=true\\n'; fi
else
  printf 'repo_exists=false\\nrepo_head=MISSING\\nrepo_branch=MISSING\\nrepo_clean=MISSING\\n'
fi
if command -v pgrep >/dev/null 2>&1; then printf 'process_probe_available=true\\n'; else printf 'process_probe_available=false\\n'; fi
processes=$(pgrep -af '[s]ktlm.production.s1m2|[r]un_with_metrics.py' 2>/dev/null || true)
printf 'active_s1m2_process_count=%s\\n' "$(printf '%s\\n' "$processes" | sed '/^$/d' | wc -l | tr -d ' ')"
printf 'active_s1m2_processes=%s\\n' "$(printf '%s' "$processes" | tr '\\n' '|')"
if [ -x "$repo/.venv/bin/python" ]; then
  printf 'venv_exists=true\\n'
  printf 'venv_python=%s\\n' "$("$repo/.venv/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || printf ERROR)"
  if "$repo/.venv/bin/python" -m pip check >/dev/null 2>&1; then printf 'pip_check=true\\n'; else printf 'pip_check=false\\n'; fi
else
  printf 'venv_exists=false\\nvenv_python=MISSING\\npip_check=false\\n'
fi
if [ -d "$cloud/data/canonical/gretil_iast" ] && [ -f "$cloud/data/manifests/canonical_corpus.csv" ]; then printf 'm0_present=true\\n'; else printf 'm0_present=false\\n'; fi
if [ -d "$cloud/data/representations/gretil" ] && [ -f "$cloud/data/manifests/representations.csv" ]; then printf 'm0_representations_present=true\\n'; else printf 'm0_representations_present=false\\n'; fi
if [ -d "$cloud/data/derived/m0_prime/iast/continuous" ] && [ -f "$cloud/artifacts/m0_prime/m0_prime_iast_continuous_v1/manifest.csv" ]; then printf 'm0_prime_present=true\\n'; else printf 'm0_prime_present=false\\n'; fi
""".strip()


def preflight_action(configs: Mapping[str, Any], runner: Any) -> list[dict[str, Any]]:
    rows = _parallel(
        configs,
        lambda role, config: _preflight_one(runner, config, role),
    )
    identities = [row.get("machine_identity") for row in rows if row.get("valid")]
    identity_ok = (
        len(identities) == 6
        and all(identity not in {None, "", "MISSING"} for identity in identities)
        and len(set(identities)) == 6
    )
    if not identity_ok:
        for row in rows:
            row["valid"] = False
            row.setdefault("error", "six distinct physical machine identities were not observed")
    return rows


def _preflight_one(runner: Any, config: Any, role: str) -> dict[str, Any]:
    result = bridge.run_ssh(config, build_preflight_script(config, role), runner)
    if result.returncode != 0:
        raise VmOpsError(
            f"SSH preflight exited {result.returncode}: {(result.stderr or '').strip()}"
        )
    values = _parse_key_values(result.stdout)
    if values.get("host_role") != role:
        raise VmOpsError("remote preflight host-role echo mismatch")
    values["ssh_reachable"] = True
    values["ready_for_round1"] = all(
        values.get(key) == "true"
        for key in (
            "repo_clean",
            "venv_exists",
            "pip_check",
            "m0_present",
            "m0_representations_present",
            "m0_prime_present",
            "process_probe_available",
        )
    ) and values.get("active_s1m2_process_count") == "0"
    return values


def deploy_action(
    configs: Mapping[str, Any],
    contract: ExperimentContract,
    repo_root: Path,
    runner: Any,
    *,
    bundle_path: Path,
    bundle_sha256: str,
    expected_head: str,
) -> list[dict[str, Any]]:
    if not SHA1_RE.fullmatch(expected_head) or not SHA256_RE.fullmatch(bundle_sha256):
        raise VmOpsError("deploy requires full lowercase HEAD and bundle SHA-256")
    local = bridge.local_git_status(repo_root, runner)
    if local.get("head") != expected_head or local.get("dirty"):
        raise VmOpsError("local repository must be clean at the declared deployment HEAD")
    if _sha256(bundle_path) != bundle_sha256:
        raise VmOpsError("declared bundle SHA-256 does not match the local bundle")

    def prepare_cloud_root(_role: str, config: Any) -> Mapping[str, Any]:
        mount = config.remote_data_mount
        cloud = config.remote_cloud_root
        script = f"""
set -eu
mount={shlex.quote(mount)}
cloud={shlex.quote(cloud)}
if [ ! -d "$mount" ]; then printf 'data mount: MISSING\\n' >&2; exit 10; fi
mount_real=$(readlink -f "$mount")
target_real=$(readlink -f "$(findmnt -n -o TARGET -T "$mount")")
if [ "$target_real" = / ] || [ "$target_real" != "$mount_real" ]; then printf 'invalid data mount\\n' >&2; exit 11; fi
mkdir -p "$cloud"
cloud_real=$(readlink -f "$cloud")
case "$cloud_real" in "$mount_real"/*) ;; *) printf 'cloud root outside data mount\\n' >&2; exit 12;; esac
printf 'cloud_root_ready=true\\n'
""".strip()
        prepared = bridge.run_ssh(config, script, runner)
        if prepared.returncode != 0:
            raise VmOpsError(
                f"cloud-root preparation exited {prepared.returncode}: {(prepared.stderr or '').strip()}"
            )
        if _parse_key_values(prepared.stdout).get("cloud_root_ready") != "true":
            raise VmOpsError("cloud-root preparation omitted its ready marker")
        return {"cloud_root_ready": True}

    preparation = _parallel(configs, prepare_cloud_root)
    if not all(row["valid"] for row in preparation):
        return preparation

    def deploy_one(role: str, config: Any) -> Mapping[str, Any]:
        receipt: dict[str, Any] = {"warnings": []}
        result = bridge.deploy_bundle_action(
            receipt,
            config,
            contract,
            repo_root,
            runner,
            bundle_path=bundle_path,
            expected_bundle_sha256=bundle_sha256,
        )
        if result.get("deployed_head") != expected_head:
            raise VmOpsError(f"{role} did not deploy the declared exact HEAD")
        return {**result, "bridge_receipt": receipt}

    return _parallel(configs, deploy_one)


def build_environment_check_script(config: Any, expected_head: str) -> str:
    repo = config.remote_repo or ""
    return f"""
set -eu
{_identity_guard(config, expected_head)}
test -x "$repo/.venv/bin/python"
"$repo/.venv/bin/python" -c 'import sys; assert sys.version_info[:2] == (3, 11); import sktlm'
"$repo/.venv/bin/python" -m pip check >/dev/null
printf 'environment_valid=true\\n'
""".strip()


def build_environment_setup_script(config: Any, expected_head: str) -> str:
    repo = config.remote_repo or ""
    mount = config.remote_data_mount
    cloud = config.remote_cloud_root
    return f"""
set -eu
{_identity_guard(config, expected_head)}
mount={shlex.quote(mount)}
cloud={shlex.quote(cloud)}
if ! command -v python3.11 >/dev/null 2>&1; then printf 'python3.11: MISSING\\n' >&2; exit 30; fi
mount_real=$(readlink -f "$mount")
target_real=$(readlink -f "$(findmnt -n -o TARGET -T "$mount")")
if [ "$target_real" = / ] || [ "$target_real" != "$mount_real" ]; then printf 'invalid data mount\\n' >&2; exit 31; fi
cloud_real=$(readlink -f "$cloud")
case "$cloud_real" in "$mount_real"/*) ;; *) printf 'cloud root outside data mount\\n' >&2; exit 32;; esac
link_dir() {{
  target=$1; link=$2; mkdir -p "$target"
  if [ -L "$link" ]; then
    [ "$(readlink -f "$link")" = "$(readlink -f "$target")" ] || {{ printf 'symlink mismatch: %s\\n' "$link" >&2; exit 33; }}
  elif [ -e "$link" ]; then printf 'refusing to replace existing path: %s\\n' "$link" >&2; exit 34
  else ln -s "$target" "$link"; fi
}}
link_dir "$cloud/artifacts" "$repo/artifacts"
link_dir "$cloud/data/canonical" "$repo/data/canonical"
link_dir "$cloud/data/representations" "$repo/data/representations"
link_dir "$cloud/data/derived" "$repo/data/derived"
link_dir "$cloud/venv-py311" "$repo/.venv"
if [ ! -x "$repo/.venv/bin/python" ]; then python3.11 -m venv "$cloud/venv-py311"; fi
if "$repo/.venv/bin/python" -c 'import sys; assert sys.version_info[:2] == (3, 11); import sktlm' >/dev/null 2>&1 && "$repo/.venv/bin/python" -m pip check >/dev/null 2>&1; then
  printf 'environment_action=SKIPPED_ALREADY_VALID\\n'
else
  export PIP_CACHE_DIR="$cloud/pip-cache"; mkdir -p "$PIP_CACHE_DIR"
  "$repo/.venv/bin/python" -m pip install -e "$repo"
  "$repo/.venv/bin/python" -m pip check >/dev/null
  printf 'environment_action=INSTALLED\\n'
fi
"$repo/.venv/bin/python" -c 'import sys; assert sys.version_info[:2] == (3, 11); import sktlm'
"$repo/.venv/bin/python" -m pip check >/dev/null
printf 'environment_valid=true\\n'
""".strip()


def environment_action(
    configs: Mapping[str, Any], runner: Any, expected_head: str
) -> list[dict[str, Any]]:
    def environment_one(_role: str, config: Any) -> Mapping[str, Any]:
        check = bridge.run_ssh(
            config, build_environment_check_script(config, expected_head), runner
        )
        if check.returncode == 0:
            return {"environment_action": "SKIPPED_ALREADY_VALID"}
        setup = bridge.run_ssh(
            config, build_environment_setup_script(config, expected_head), runner
        )
        if setup.returncode != 0:
            raise VmOpsError(
                f"environment setup exited {setup.returncode}: {(setup.stderr or '').strip()}"
            )
        values = _parse_key_values(setup.stdout)
        if values.get("environment_valid") != "true":
            raise VmOpsError("environment setup did not emit its validity marker")
        return values

    return _parallel(configs, environment_one)


def build_input_probe_script(
    config: Any, contract: ExperimentContract, expected_head: str
) -> str:
    commands = [shlex.join(item.validator_argv) for item in contract.input_sets]
    return "\n".join(
        [
            "set -eu",
            _identity_guard(config, expected_head),
            'if [ ! -x "$repo/.venv/bin/python" ]; then printf \'environment: MISSING\\n\' >&2; exit 30; fi',
            'export PATH="$repo/.venv/bin:$PATH"',
            'cd "$repo"',
            "set +e",
            f"( {' && '.join(commands)} ) >/dev/null 2>&1",
            "validator_exit=$?",
            "set -e",
            "if [ \"$validator_exit\" -eq 0 ]; then printf 'inputs_valid=true\\n'; else printf 'inputs_valid=false\\n'; fi",
        ]
    )


def sync_inputs_action(
    configs: Mapping[str, Any],
    contract: ExperimentContract,
    repo_root: Path,
    runner: Any,
    expected_head: str,
) -> list[dict[str, Any]]:
    local = bridge.local_git_status(repo_root, runner)
    if local.get("head") != expected_head or local.get("dirty"):
        raise VmOpsError("local repository must be clean at the declared input identity")
    bridge.validate_contract_inputs_local(repo_root, contract, runner)

    def sync_one(_role: str, config: Any) -> Mapping[str, Any]:
        probe = bridge.run_ssh(
            config, build_input_probe_script(config, contract, expected_head), runner
        )
        if probe.returncode != 0:
            raise VmOpsError(
                f"input precheck exited {probe.returncode}: {(probe.stderr or '').strip()}"
            )
        if _parse_key_values(probe.stdout).get("inputs_valid") == "true":
            return {"input_action": "SKIPPED_ALREADY_VALID"}
        receipt: dict[str, Any] = {"warnings": [], "transfers": []}
        result = bridge.push_contract_inputs_action(
            receipt,
            config,
            contract,
            repo_root,
            runner,
            verify_after=True,
        )
        return {**result, "input_action": "SYNCED_AND_VERIFIED", "bridge_receipt": receipt}

    return _parallel(configs, sync_one)


def build_remote_validate_script(
    config: Any,
    role: str,
    expected_head: str,
    minimum_free_bytes: int,
) -> str:
    repo = config.remote_repo or ""
    mount = config.remote_data_mount
    return f"""
set -eu
{_identity_guard(config, expected_head)}
mount={shlex.quote(mount)}
role={shlex.quote(role)}
target=$(findmnt -n -o TARGET -T "$mount")
if [ "$(readlink -f "$target")" != "$(readlink -f "$mount")" ] || [ "$(readlink -f "$target")" = / ]; then printf 'invalid data mount\\n' >&2; exit 31; fi
free=$(df -B1 --output=avail "$mount" | tail -n 1 | tr -d ' ')
if [ "$free" -lt {minimum_free_bytes} ]; then printf 'free-space gate failed\\n' >&2; exit 32; fi
test -x "$repo/.venv/bin/python"
"$repo/.venv/bin/python" -c 'import sys; assert sys.version_info[:2] == (3, 11); import sktlm'
"$repo/.venv/bin/python" -m pip check >/dev/null
cd "$repo"
"$repo/.venv/bin/python" -m sktlm.production.s1m2 validate-contract >/dev/null
printf 'host_role=%s\\n' "$role"
printf 'machine_identity=%s\\n' "$(cat /etc/machine-id)"
printf 'validated_head=%s\\n' "$expected"
printf 'free_bytes=%s\\n' "$free"
printf 'remote_validation=PASS\\n'
""".strip()


def remote_validate_action(
    configs: Mapping[str, Any],
    runner: Any,
    expected_head: str,
    minimum_free_bytes: int,
) -> list[dict[str, Any]]:
    def validate_one(role: str, config: Any) -> Mapping[str, Any]:
        result = bridge.run_ssh(
            config,
            build_remote_validate_script(
                config, role, expected_head, minimum_free_bytes
            ),
            runner,
        )
        if result.returncode != 0:
            raise VmOpsError(
                f"remote validation exited {result.returncode}: {(result.stderr or '').strip()}"
            )
        values = _parse_key_values(result.stdout)
        if values.get("remote_validation") != "PASS" or values.get("host_role") != role:
            raise VmOpsError("remote validation did not emit exact PASS identity")
        return values

    rows = _parallel(configs, validate_one)
    identities = [row.get("machine_identity") for row in rows if row.get("valid")]
    if len(identities) != 6 or len(set(identities)) != 6:
        for row in rows:
            row["valid"] = False
            row.setdefault("error", "remote validation requires six physical machines")
    return rows


def load_round1_plan(
    repo_root: Path,
    plan_path: Path,
    production_contract_path: Path,
    expected_head: str,
) -> tuple[dict[str, Any], Path, str]:
    resolved_plan, relative_plan = _resolve_repo_path(
        repo_root, plan_path, label="Round 1 plan"
    )
    contract = s1m2.load_contract(
        production_contract_path, repo_root=repo_root, verify_files=True
    )
    plan = json.loads(resolved_plan.read_text(encoding="utf-8"))
    s1m2._validate_plan(plan, contract)
    if (
        plan.get("plan_type") != "round1"
        or plan.get("launch_mode") != "six_way_parallel"
        or plan.get("git_sha") != expected_head
        or plan.get("branch") != contract["deployment"]["branch"]
    ):
        raise VmOpsError("Round 1 plan identity does not match the frozen deployment")
    assignments = [
        (job.get("host_role"), job.get("workers")) for job in plan["jobs"]
    ]
    if assignments != list(zip(CORE_HOST_ROLES, s1m2.ROUND1_WORKERS, strict=True)):
        raise VmOpsError("Round 1 plan does not contain the exact six-host worker map")
    return plan, resolved_plan, relative_plan


def build_round1_launch_script(
    config: Any,
    job: Mapping[str, Any],
    expected_head: str,
    relative_plan: str,
    plan_sha256: str,
) -> str:
    repo = config.remote_repo or ""
    run_path = posixpath.join(repo, str(job["run_dir"]))
    control_path = posixpath.join(repo, str(job["control_dir"]))
    launch_root = posixpath.join(config.remote_cloud_root, "launches/s1m2_round1")
    job_id = str(job["job_id"])
    command = str(job["launch_command_shell"])
    command_sha256 = hashlib.sha256(command.encode("utf-8")).hexdigest()
    wrapper = posixpath.join(launch_root, f"{job_id}.wrapper.sh")
    manifest = posixpath.join(launch_root, f"{job_id}.detached.json")
    exit_status = posixpath.join(launch_root, f"{job_id}.exit.json")
    stdout = posixpath.join(launch_root, f"{job_id}.stdout.log")
    stderr = posixpath.join(launch_root, f"{job_id}.stderr.log")
    remote_plan = posixpath.join(repo, relative_plan)
    wrapper_lines = [
        "#!/bin/sh",
        "set +e",
        f"cd {shlex.quote(repo)}",
        'export PATH="$PWD/.venv/bin:$PATH"',
        command,
        "code=$?",
        'ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)',
        f"tmp={shlex.quote(exit_status)}.tmp.$$",
        (
            "printf '{\"schema_version\":\"sktlm-detached-exit/v1\","
            f"\"job_id\":\"{job_id}\",\"exit_code\":%s,"
            "\"ended_at\":\"%s\"}\\n' \"$code\" \"$ended\" > \"$tmp\""
        ),
        f"mv \"$tmp\" {shlex.quote(exit_status)}",
        'exit "$code"',
    ]
    wrapper_text = "\n".join(wrapper_lines) + "\n"
    return f"""
set -eu
{_identity_guard(config, expected_head)}
plan={shlex.quote(remote_plan)}
if [ "$(sha256sum "$plan" | awk '{{print $1}}')" != {shlex.quote(plan_sha256)} ]; then printf 'plan SHA-256 mismatch\\n' >&2; exit 40; fi
if [ -e {shlex.quote(run_path)} ] || [ -e {shlex.quote(control_path)} ]; then printf 'run or control path already exists\\n' >&2; exit 41; fi
command -v pgrep >/dev/null 2>&1 || {{ printf 'pgrep: MISSING\\n' >&2; exit 44; }}
if pgrep -af '[s]ktlm.production.s1m2|[r]un_with_metrics.py' >/dev/null 2>&1; then printf 'another S1M2 process is already active\\n' >&2; exit 43; fi
mkdir -p {shlex.quote(launch_root)}
for path in {shlex.quote(wrapper)} {shlex.quote(manifest)} {shlex.quote(exit_status)}; do [ ! -e "$path" ] || {{ printf 'launch identity already exists: %s\\n' "$path" >&2; exit 42; }}; done
printf %s {shlex.quote(wrapper_text)} > {shlex.quote(wrapper)}
chmod 700 {shlex.quote(wrapper)}
nohup sh {shlex.quote(wrapper)} > {shlex.quote(stdout)} 2> {shlex.quote(stderr)} < /dev/null &
pid=$!
start_ticks=$(awk '{{print $22}}' "/proc/$pid/stat")
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
machine=$(cat /etc/machine-id)
boot=$(cat /proc/sys/kernel/random/boot_id)
tmp={shlex.quote(manifest)}.tmp.$$
printf '{{"schema_version":"sktlm-detached-job/v1","job_id":"{job_id}","host_role":"{job['host_role']}","command_sha256":"{command_sha256}","pid":%s,"process_start_ticks":%s,"machine_identity":"%s","boot_identity":"%s","started_at":"%s","completion_marker":"{exit_status}","result_path":"{run_path}","exit_status":null}}\\n' "$pid" "$start_ticks" "$machine" "$boot" "$started" > "$tmp"
mv "$tmp" {shlex.quote(manifest)}
printf 'job_id=%s\\n' {shlex.quote(job_id)}
printf 'pid=%s\\n' "$pid"
printf 'process_start_ticks=%s\\n' "$start_ticks"
printf 'command_sha256=%s\\n' {shlex.quote(command_sha256)}
printf 'detached_manifest=%s\\n' {shlex.quote(manifest)}
printf 'completion_marker=%s\\n' {shlex.quote(exit_status)}
""".strip()


def launch_round1_action(
    configs: Mapping[str, Any],
    runner: Any,
    *,
    repo_root: Path,
    plan: Mapping[str, Any],
    plan_path: Path,
    relative_plan: str,
    expected_head: str,
) -> list[dict[str, Any]]:
    plan_sha256 = _sha256(plan_path)
    remote_plan_by_role: dict[str, str] = {}
    jobs = {str(job["host_role"]): job for job in plan["jobs"]}

    def precheck(role: str, config: Any) -> Mapping[str, Any]:
        job = jobs[role]
        run_path = posixpath.join(config.remote_repo or "", str(job["run_dir"]))
        control_path = posixpath.join(
            config.remote_repo or "", str(job["control_dir"])
        )
        script = f"""
set -eu
{_identity_guard(config, expected_head)}
if [ -e {shlex.quote(run_path)} ] || [ -e {shlex.quote(control_path)} ]; then printf 'run or control path already exists\\n' >&2; exit 41; fi
command -v pgrep >/dev/null 2>&1 || {{ printf 'pgrep: MISSING\\n' >&2; exit 44; }}
if pgrep -af '[s]ktlm.production.s1m2|[r]un_with_metrics.py' >/dev/null 2>&1; then printf 'another S1M2 process is already active\\n' >&2; exit 43; fi
printf 'machine_identity=%s\\n' "$(cat /etc/machine-id)"
""".strip()
        result = bridge.run_ssh_stdin(config, script, runner)
        if result.returncode != 0:
            raise VmOpsError(
                f"launch precheck exited {result.returncode}: {(result.stderr or '').strip()}"
            )
        return _parse_key_values(result.stdout)

    prechecked = _parallel(configs, precheck)
    machine_ids = [row.get("machine_identity") for row in prechecked if row["valid"]]
    if not all(row["valid"] for row in prechecked) or len(set(machine_ids)) != 6:
        if len(set(machine_ids)) != 6:
            for row in prechecked:
                row["valid"] = False
                row.setdefault("error", "Round 1 requires six physical machines")
        return prechecked

    def prepare(role: str, config: Any) -> Mapping[str, Any]:
        remote_plan = posixpath.join(config.remote_repo or "", relative_plan)
        incoming = f"{remote_plan}.incoming-{plan_sha256[:12]}"
        parent = posixpath.dirname(remote_plan)
        script = f"""
set -eu
{_identity_guard(config, expected_head)}
mkdir -p {shlex.quote(parent)}
if [ -e {shlex.quote(remote_plan)} ] || [ -e {shlex.quote(incoming)} ]; then printf 'remote plan path already exists\\n' >&2; exit 40; fi
""".strip()
        prepared = bridge.run_ssh(config, script, runner)
        if prepared.returncode != 0:
            raise VmOpsError(
                f"plan destination preparation exited {prepared.returncode}: {(prepared.stderr or '').strip()}"
            )
        transferred = runner.run(bridge.scp_argv(config, plan_path, incoming))
        if transferred.returncode != 0:
            raise VmOpsError(
                f"plan transfer exited {transferred.returncode}: {(transferred.stderr or '').strip()}"
            )
        verify = bridge.run_ssh(
            config,
            f"set -eu\n[ \"$(sha256sum {shlex.quote(incoming)} | awk '{{print $1}}')\" = {shlex.quote(plan_sha256)} ]\nmv {shlex.quote(incoming)} {shlex.quote(remote_plan)}",
            runner,
        )
        if verify.returncode != 0:
            raise VmOpsError(
                f"remote plan verification exited {verify.returncode}: {(verify.stderr or '').strip()}"
            )
        remote_plan_by_role[role] = remote_plan
        return {"plan_path": remote_plan, "plan_sha256": plan_sha256}

    prepared = _parallel(configs, prepare)
    if not all(row["valid"] for row in prepared):
        return prepared

    def launch(role: str, config: Any) -> Mapping[str, Any]:
        result = bridge.run_ssh_stdin(
            config,
            build_round1_launch_script(
                config,
                jobs[role],
                expected_head,
                relative_plan,
                plan_sha256,
            ),
            runner,
        )
        if result.returncode != 0:
            raise VmOpsError(
                f"detached launch exited {result.returncode}: {(result.stderr or '').strip()}"
            )
        values = _parse_key_values(result.stdout)
        if values.get("job_id") != jobs[role]["job_id"]:
            raise VmOpsError("detached launcher returned the wrong job identity")
        return {**values, "plan_path": remote_plan_by_role[role]}

    return _parallel(configs, launch)


def collect_round1_attestations_action(
    configs: Mapping[str, Any],
    runner: Any,
    *,
    plan: Mapping[str, Any],
    plan_path: Path,
    relative_plan: str,
    expected_head: str,
    attestation_dir: Path,
) -> list[dict[str, Any]]:
    """Run formal audits remotely and pull only their compact attestations."""

    if attestation_dir.exists():
        raise VmOpsError(f"refusing to overwrite attestation directory: {attestation_dir}")
    attestation_dir.mkdir(parents=True)
    plan_sha256 = _sha256(plan_path)
    jobs = {str(job["host_role"]): job for job in plan["jobs"]}

    def collect_one(role: str, config: Any) -> Mapping[str, Any]:
        job = jobs[role]
        filename = s1m2.round1_attestation_filename(str(job["job_id"]))
        local_path = attestation_dir / filename
        remote_plan = posixpath.join(config.remote_repo or "", relative_plan)
        remote_path = posixpath.join(
            config.remote_repo or "", str(job["control_dir"]), filename
        )
        relative_output = posixpath.join(str(job["control_dir"]), filename)
        command = shlex.join(
            [
                "./.venv/bin/python",
                "-m",
                "sktlm.production.s1m2",
                "attest-round1",
                "--plan",
                relative_plan,
                "--job-id",
                str(job["job_id"]),
                "--output",
                relative_output,
            ]
        )
        script = f"""
set -eu
{_identity_guard(config, expected_head)}
if [ "$(sha256sum {shlex.quote(remote_plan)} | awk '{{print $1}}')" != {shlex.quote(plan_sha256)} ]; then printf 'plan SHA-256 mismatch\\n' >&2; exit 40; fi
if [ -e {shlex.quote(remote_path)} ]; then printf 'attestation already exists\\n' >&2; exit 41; fi
cd "$repo"
set +e
{command} >/dev/null
audit_return_code=$?
set -e
if [ ! -f {shlex.quote(remote_path)} ]; then printf 'attestation was not produced\\n' >&2; exit 42; fi
printf 'audit_return_code=%s\\n' "$audit_return_code"
printf 'attestation_sha256=%s\\n' "$(sha256sum {shlex.quote(remote_path)} | awk '{{print $1}}')"
printf 'attestation_bytes=%s\\n' "$(wc -c < {shlex.quote(remote_path)} | tr -d ' ')"
""".strip()
        audited = bridge.run_ssh(config, script, runner)
        if audited.returncode != 0:
            raise VmOpsError(
                f"remote attestation exited {audited.returncode}: {(audited.stderr or '').strip()}"
            )
        remote_values = _parse_key_values(audited.stdout)
        pulled = runner.run(bridge.scp_pull_argv(config, remote_path, local_path))
        if pulled.returncode != 0:
            raise VmOpsError(
                f"compact attestation pull exited {pulled.returncode}: {(pulled.stderr or '').strip()}"
            )
        if _sha256(local_path) != remote_values.get("attestation_sha256"):
            raise VmOpsError("downloaded attestation SHA-256 differs from the remote file")
        payload = json.loads(local_path.read_text(encoding="utf-8"))
        if payload.get("job_id") != job["job_id"] or payload.get("host_role") != role:
            raise VmOpsError("downloaded attestation identity differs from the plan")
        audit_passed = (
            remote_values.get("audit_return_code") == "0"
            and payload.get("valid") is True
        )
        return {
            "valid": audit_passed,
            "job_id": job["job_id"],
            "workers": job["workers"],
            "attestation_path": str(local_path),
            **remote_values,
        }

    return _parallel(configs, collect_one)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument(
        "--production-contract", type=Path, default=DEFAULT_PRODUCTION_CONTRACT
    )
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--output", type=Path, required=True)
    for name in ("environment", "sync-inputs", "validate"):
        item = commands.add_parser(name)
        item.add_argument("--expected-head", required=True)
        item.add_argument("--output", type=Path, required=True)
    deploy = commands.add_parser("deploy")
    deploy.add_argument("--bundle", type=Path, required=True)
    deploy.add_argument("--bundle-sha256", required=True)
    deploy.add_argument("--expected-head", required=True)
    deploy.add_argument("--output", type=Path, required=True)
    launch = commands.add_parser("launch-round1")
    launch.add_argument("--plan", type=Path, required=True)
    launch.add_argument("--expected-head", required=True)
    launch.add_argument("--output", type=Path, required=True)
    attest = commands.add_parser("collect-round1-attestations")
    attest.add_argument("--plan", type=Path, required=True)
    attest.add_argument("--expected-head", required=True)
    attest.add_argument("--attestation-dir", type=Path, required=True)
    attest.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None, *, runner: Any | None = None) -> int:
    args = build_parser().parse_args(argv)
    active_runner = runner or bridge.SystemRunner()
    repo_root = args.repo_root.resolve()
    config_path, _ = _resolve_repo_path(repo_root, args.config, label="bridge config")
    contract_path, _ = _resolve_repo_path(
        repo_root, args.contract, label="cloud contract"
    )
    production_path, _ = _resolve_repo_path(
        repo_root, args.production_contract, label="production contract"
    )
    output = _safe_artifact_path(repo_root, args.output)
    contract = load_experiment_contract(contract_path)
    production = s1m2.load_contract(
        production_path, repo_root=repo_root, verify_files=False
    )
    if (
        contract.branch != production["deployment"]["branch"]
        or contract.deployment.mode != production["deployment"]["mode"]
    ):
        raise VmOpsError("cloud and production deployment contracts differ")
    configs = load_host_configs(config_path, contract)

    if args.command == "preflight":
        hosts = preflight_action(configs, active_runner)
    elif args.command == "deploy":
        bundle = args.bundle if args.bundle.is_absolute() else repo_root / args.bundle
        hosts = deploy_action(
            configs,
            contract,
            repo_root,
            active_runner,
            bundle_path=bundle.resolve(),
            bundle_sha256=args.bundle_sha256,
            expected_head=args.expected_head,
        )
    elif args.command == "environment":
        hosts = environment_action(configs, active_runner, args.expected_head)
    elif args.command == "sync-inputs":
        hosts = sync_inputs_action(
            configs, contract, repo_root, active_runner, args.expected_head
        )
    elif args.command == "validate":
        hosts = remote_validate_action(
            configs,
            active_runner,
            args.expected_head,
            int(production["gates"]["storage_min_free_bytes_end"]),
        )
    elif args.command == "launch-round1":
        plan, plan_path, relative_plan = load_round1_plan(
            repo_root, args.plan, production_path, args.expected_head
        )
        hosts = launch_round1_action(
            configs,
            active_runner,
            repo_root=repo_root,
            plan=plan,
            plan_path=plan_path,
            relative_plan=relative_plan,
            expected_head=args.expected_head,
        )
    else:
        plan, plan_path, relative_plan = load_round1_plan(
            repo_root, args.plan, production_path, args.expected_head
        )
        attestation_dir = _safe_artifact_path(repo_root, args.attestation_dir)
        hosts = collect_round1_attestations_action(
            configs,
            active_runner,
            plan=plan,
            plan_path=plan_path,
            relative_plan=relative_plan,
            expected_head=args.expected_head,
            attestation_dir=attestation_dir,
        )

    status = "PASS" if all(row.get("valid") for row in hosts) else "FAIL"
    payload = {
        "schema_version": SCHEMA,
        "operation": args.command,
        "status": status,
        "contract_id": contract.contract_id,
        "branch": contract.branch,
        "deployment_mode": contract.deployment.mode,
        "host_count": len(hosts),
        "hosts": hosts,
    }
    _write_receipt(output, payload)
    print(json.dumps({"status": status, "receipt": str(output)}, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    try:
        raise SystemExit(main())
    except (VmOpsError, bridge.BridgeError, ValueError, OSError) as exc:
        print(f"S1M2 VM operation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
