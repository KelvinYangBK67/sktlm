#!/usr/bin/env python3
"""Generic, contract-driven and fail-closed SSH/rsync experiment bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility.
    import tomli as tomllib  # type: ignore[import-not-found]

from sktlm.cloud.contracts import ExperimentContract, load_experiment_contract


RECEIPT_SCHEMA = "sktlm-cloud-transfer-receipt/v1"
COLLECTION_STATE_FILE = ".sktlm-collection.json"
SECRET_RE = re.compile(r"(?:password|passwd|secret|token|private[_-]?key|credential)", re.I)
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class BridgeError(RuntimeError):
    pass


class SystemRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(argv), cwd=cwd, check=check, capture_output=True, text=True
        )


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    host: str | None = None
    user: str | None = None
    port: int = 22
    identity_file: str | None = None
    remote_repo: str | None = None
    remote_data_mount: str = "/mnt/sktlm-data"
    remote_cloud_root: str = "/mnt/sktlm-data/sktlm"
    repository_url: str = "https://github.com/KelvinYangBK67/sktlm.git"
    host_profile: str | None = None
    machine_id: str | None = None
    host_role: str | None = None
    available_host_profiles: tuple[str, ...] = ()

    @property
    def target(self) -> str:
        if not self.host:
            raise BridgeError("remote host is not configured")
        return f"{self.user}@{self.host}" if self.user else self.host


def _reject_secret_keys(value: Any, path: str = "config") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if SECRET_RE.search(str(key)):
                raise BridgeError(f"secret-bearing config field is forbidden: {path}.{key}")
            _reject_secret_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_keys(item, f"{path}[{index}]")


def _normalize_remote_path(value: str, field: str) -> str:
    if not value.startswith("/") or ".." in value.split("/"):
        raise BridgeError(f"{field} must be an absolute normalized remote path")
    normalized = posixpath.normpath(value)
    if normalized == "/":
        raise BridgeError(f"{field} cannot be the remote filesystem root")
    return normalized


def _is_remote_child(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip("/") + "/")


def validate_config(config: BridgeConfig) -> BridgeConfig:
    if config.host is not None and not re.fullmatch(r"[A-Za-z0-9._:\-\[\]]+", config.host):
        raise BridgeError("host contains unsupported characters")
    if config.user is not None and not re.fullmatch(r"[A-Za-z0-9._-]+", config.user):
        raise BridgeError("user contains unsupported characters")
    if not 1 <= int(config.port) <= 65535:
        raise BridgeError("SSH port is outside 1..65535")
    if re.match(r"https?://[^/@]+:[^/@]+@", config.repository_url):
        raise BridgeError("repository URL must not embed credentials")
    mount = _normalize_remote_path(config.remote_data_mount, "remote_data_mount")
    cloud = _normalize_remote_path(config.remote_cloud_root, "remote_cloud_root")
    if not _is_remote_child(cloud, mount):
        raise BridgeError("remote_cloud_root must be inside remote_data_mount")
    remote_repo = (
        _normalize_remote_path(config.remote_repo, "remote_repo")
        if config.remote_repo is not None
        else None
    )
    return replace(
        config,
        remote_data_mount=mount,
        remote_cloud_root=cloud,
        remote_repo=remote_repo,
    )


def load_config(path: Path, *, host_profile: str | None = None) -> BridgeConfig:
    if not path.is_file():
        return validate_config(BridgeConfig())
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise BridgeError("bridge config must be a TOML table")
    _reject_secret_keys(raw)
    if set(raw) - {"bridge", "host_profiles"}:
        raise BridgeError(f"unknown bridge config tables: {sorted(set(raw) - {'bridge', 'host_profiles'})}")
    base = raw.get("bridge", {})
    profiles = raw.get("host_profiles", {})
    if not isinstance(base, dict) or not isinstance(profiles, dict):
        raise BridgeError("bridge and host_profiles must be TOML tables")
    allowed = {
        "host", "user", "port", "identity_file", "remote_repo", "remote_data_mount",
        "remote_cloud_root", "repository_url",
    }
    if set(base) - allowed:
        raise BridgeError(f"unknown bridge fields: {sorted(set(base) - allowed)}")
    selected = dict(base)
    machine_id = role = None
    if host_profile is not None:
        if host_profile not in profiles:
            raise BridgeError(
                f"unknown host profile {host_profile!r}; available: {sorted(profiles)}"
            )
        profile = profiles[host_profile]
        if not isinstance(profile, dict):
            raise BridgeError("host profile must be a TOML table")
        profile_allowed = allowed | {"machine_id", "role", "notes"}
        if set(profile) - profile_allowed:
            raise BridgeError(f"unknown host profile fields: {sorted(set(profile) - profile_allowed)}")
        selected.update({key: value for key, value in profile.items() if key in allowed})
        machine_id = str(profile.get("machine_id", host_profile))
        role = str(profile["role"]) if "role" in profile else None
    return validate_config(
        BridgeConfig(
            **selected,
            host_profile=host_profile,
            machine_id=machine_id,
            host_role=role,
            available_host_profiles=tuple(sorted(profiles)),
        )
    )


def require_remote_config(config: BridgeConfig) -> None:
    if not config.host or not config.remote_repo:
        raise BridgeError("host and remote_repo must be configured")


def ssh_argv(config: BridgeConfig, script: str) -> list[str]:
    require_remote_config(config)
    argv = ["ssh", "-p", str(config.port), "-o", "BatchMode=yes"]
    if config.identity_file:
        argv.extend(["-i", os.path.expanduser(config.identity_file)])
    argv.extend([config.target, "sh", "-lc", script])
    return argv


def _remote_mount_guard(config: BridgeConfig, remote_path: str) -> str:
    path = _normalize_remote_path(remote_path, "guarded remote path")
    if not _is_remote_child(path, config.remote_data_mount):
        raise BridgeError(f"remote path escapes the configured data mount: {path}")
    mount = shlex.quote(config.remote_data_mount)
    target = shlex.quote(path)
    return (
        f"test -d {mount} && "
        f"case \"$(realpath -m {target})\" in \"$(realpath -m {mount})\"|\"$(realpath -m {mount})\"/*) ;; "
        "*) exit 73 ;; esac"
    )


def build_rsync_argv(
    config: BridgeConfig,
    *,
    source: str,
    destination: str,
    direction: str,
    include_files: Sequence[str] | None = None,
) -> list[str]:
    require_remote_config(config)
    if direction not in {"push", "pull"}:
        raise BridgeError("rsync direction must be push or pull")
    transport = ["ssh", "-p", str(config.port), "-o", "BatchMode=yes"]
    if config.identity_file:
        transport.extend(["-i", os.path.expanduser(config.identity_file)])
    argv = ["rsync", "-a", "--partial", "--append-verify", "-e", shlex.join(transport)]
    if include_files is not None:
        argv.extend(["--include", "*/"])
        for item in include_files:
            if item.startswith("/") or ".." in Path(item).parts:
                raise BridgeError(f"unsafe rsync include path: {item}")
            argv.extend(["--include", f"/{item}"])
        argv.extend(["--exclude", "*"])
    endpoint = config.target
    if direction == "push":
        argv.extend([source, f"{endpoint}:{destination}"])
    else:
        argv.extend([f"{endpoint}:{source}", destination])
    return argv


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id):
        raise BridgeError(f"invalid run/condition identity: {run_id!r}")
    return run_id


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _local_collection_root(
    base: Path,
    run_id: str,
    *,
    resume_identity: Mapping[str, Any],
) -> Path:
    run_id = validate_run_id(run_id)
    destination = base / run_id
    marker = destination / COLLECTION_STATE_FILE
    if destination.exists():
        if not marker.is_file():
            raise FileExistsError(f"refusing existing unmarked collection: {destination}")
        state = json.loads(marker.read_text(encoding="utf-8"))
        if state.get("complete") is True:
            raise FileExistsError(f"refusing completed collection overwrite: {destination}")
        if state.get("identity") != dict(resume_identity):
            raise BridgeError("partial collection identity differs; refusing unsafe resume")
        return destination
    destination.mkdir(parents=True)
    marker.write_text(
        json.dumps({"complete": False, "identity": dict(resume_identity)}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def _complete_collection(destination: Path) -> None:
    marker = destination / COLLECTION_STATE_FILE
    state = json.loads(marker.read_text(encoding="utf-8"))
    state["complete"] = True
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, marker)


def validate_downloaded_audit_hashes(
    collection: Path,
    audit: Mapping[str, Any],
    contract: ExperimentContract,
    profile: str,
) -> list[str]:
    inventory = audit.get(contract.audit_inventory_key)
    if not isinstance(inventory, Mapping):
        raise BridgeError(f"remote audit lacks inventory key {contract.audit_inventory_key!r}")
    selected = contract.profile_files(profile)
    expected = set(inventory) if selected is None else set(selected)
    expected.update(contract.required_audited_files)
    failures: list[str] = []
    for relative in sorted(expected):
        row = inventory.get(relative)
        if not isinstance(row, Mapping):
            failures.append(f"remote audit lacks required item: {relative}")
            continue
        path = collection / relative
        if not path.is_file():
            failures.append(f"downloaded file is missing: {relative}")
            continue
        if path.stat().st_size != int(row.get("bytes", -1)):
            failures.append(f"downloaded size mismatch: {relative}")
        if file_sha256(path) != row.get("sha256"):
            failures.append(f"downloaded SHA-256 mismatch: {relative}")
    return failures


def registry_assignment(
    registry_path: Path,
    *,
    condition_id: str,
    config: BridgeConfig,
) -> Mapping[str, Any] | None:
    if not registry_path.is_file():
        return None
    raw = tomllib.loads(registry_path.read_text(encoding="utf-8"))
    assignments = raw.get("assignments", [])
    matches = [row for row in assignments if row.get("condition_id") == condition_id]
    if len(matches) > 1:
        raise BridgeError(f"duplicate host assignments for {condition_id}")
    if not matches:
        return None
    assignment = matches[0]
    if config.host_profile is None:
        raise BridgeError("assigned collection requires --host-profile")
    if assignment.get("host_profile") != config.host_profile:
        raise BridgeError(
            f"condition {condition_id} is assigned to {assignment.get('host_profile')}, not {config.host_profile}"
        )
    return assignment


def _redact(value: Any, sensitive: Sequence[str]) -> Any:
    if isinstance(value, dict):
        return {key: _redact(item, sensitive) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, sensitive) for item in value]
    if isinstance(value, str):
        output = value
        for item in sensitive:
            if item:
                output = output.replace(item, "<redacted>")
        return output
    return value


def write_receipt(repo_root: Path, operation: str, receipt: Mapping[str, Any]) -> Path:
    root = repo_root / "artifacts/cloud_transfers"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"{stamp}_{operation}.json"
    counter = 1
    while path.exists():
        path = root / f"{stamp}_{operation}_{counter}.json"
        counter += 1
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def local_git_status(repo_root: Path, runner: SystemRunner) -> dict[str, Any]:
    head = runner.run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    status = runner.run(["git", "status", "--porcelain"], cwd=repo_root)
    branch = runner.run(["git", "branch", "--show-current"], cwd=repo_root)
    return {
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "clean": status.returncode == 0 and not status.stdout.strip(),
    }


def require_deployable_head(
    repo_root: Path, contract: ExperimentContract, runner: SystemRunner
) -> str:
    state = local_git_status(repo_root, runner)
    if state["clean"] is not True:
        raise BridgeError("code deployment requires a clean local worktree")
    if state["branch"] != contract.branch:
        raise BridgeError(f"code deployment requires branch {contract.branch}")
    result = runner.run(
        ["git", "ls-remote", "--heads", "origin", f"refs/heads/{contract.branch}"],
        cwd=repo_root,
    )
    fields = result.stdout.split()
    if result.returncode != 0 or len(fields) < 2 or fields[0] != state["head"]:
        raise BridgeError("local HEAD must equal the remote branch HEAD before deployment")
    return str(state["head"])


def deploy_code(
    *,
    repo_root: Path,
    config: BridgeConfig,
    contract: ExperimentContract,
    runner: SystemRunner,
) -> tuple[dict[str, Any], Path]:
    require_remote_config(config)
    head = require_deployable_head(repo_root, contract, runner)
    assert config.remote_repo is not None
    if not _is_remote_child(config.remote_repo, config.remote_data_mount):
        raise BridgeError("code deployment target must be inside the guarded data mount")
    parent = posixpath.dirname(config.remote_repo)
    guard = _remote_mount_guard(config, parent)
    repository = shlex.quote(config.repository_url)
    branch = shlex.quote(contract.branch)
    remote_repo = shlex.quote(config.remote_repo)
    parent_q = shlex.quote(parent)
    script = (
        f"{guard} && mkdir -p {parent_q} && "
        f"if test -d {remote_repo}/.git; then "
        f"cd {remote_repo} && test -z \"$(git status --porcelain)\" && "
        f"git fetch origin {branch} && git checkout --detach {shlex.quote(head)}; "
        f"else git clone --branch {branch} --single-branch {repository} {remote_repo} && "
        f"cd {remote_repo} && git checkout --detach {shlex.quote(head)}; fi && "
        f"test \"$(git rev-parse HEAD)\" = {shlex.quote(head)}"
    )
    result = runner.run(ssh_argv(config, script))
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "operation": "deploy-code",
        "contract_id": contract.contract_id,
        "expected_head": head,
        "return_code": result.returncode,
        "failures": [] if result.returncode == 0 else [result.stderr.strip() or "remote deployment failed"],
        "valid": result.returncode == 0,
    }
    path = write_receipt(
        repo_root,
        "deploy-code",
        _redact(receipt, [config.host or "", config.user or "", config.identity_file or ""]),
    )
    return receipt, path


def push_inputs(
    *,
    repo_root: Path,
    config: BridgeConfig,
    contract: ExperimentContract,
    runner: SystemRunner,
) -> tuple[dict[str, Any], Path]:
    require_remote_config(config)
    assert config.remote_repo is not None
    if not _is_remote_child(config.remote_repo, config.remote_data_mount):
        raise BridgeError("input deployment requires remote_repo inside the guarded data mount")
    transfers: list[dict[str, Any]] = []
    failures: list[str] = []
    for input_set in contract.input_sets:
        validation = runner.run(input_set.validator_argv, cwd=repo_root)
        if validation.returncode != 0:
            failures.append(f"local input validator failed for {input_set.input_id}")
            break
        for relative in input_set.paths:
            source = repo_root / relative
            if not source.exists():
                failures.append(f"local input path is missing: {relative}")
                break
            destination_parent = posixpath.dirname(posixpath.join(config.remote_repo, relative))
            guard = _remote_mount_guard(config, destination_parent)
            prepared = runner.run(
                ssh_argv(config, f"{guard} && mkdir -p {shlex.quote(destination_parent)}")
            )
            if prepared.returncode != 0:
                failures.append(f"remote input destination preparation failed: {relative}")
                break
            command = build_rsync_argv(
                config,
                source=str(source),
                destination=destination_parent.rstrip("/") + "/",
                direction="push",
            )
            transferred = runner.run(command)
            transfers.append(
                {"input_id": input_set.input_id, "path": relative, "return_code": transferred.returncode}
            )
            if transferred.returncode != 0:
                failures.append(f"input transfer failed: {relative}")
                break
        if failures:
            break
    if not failures:
        for input_set in contract.input_sets:
            remote_validator = (
                f"cd {shlex.quote(config.remote_repo)} && {shlex.join(input_set.validator_argv)}"
            )
            result = runner.run(ssh_argv(config, remote_validator))
            if result.returncode != 0:
                failures.append(f"remote input validator failed for {input_set.input_id}")
                break
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "operation": "push-inputs",
        "contract_id": contract.contract_id,
        "transfers": transfers,
        "failures": failures,
        "valid": not failures,
    }
    path = write_receipt(
        repo_root,
        "push-inputs",
        _redact(receipt, [config.host or "", config.user or "", config.identity_file or ""]),
    )
    return receipt, path


def remote_audit(
    config: BridgeConfig,
    contract: ExperimentContract,
    condition_id: str,
    artifact_dir: str,
    runner: SystemRunner,
) -> dict[str, Any]:
    require_remote_config(config)
    values = {"condition_id": validate_run_id(condition_id), "artifact_dir": artifact_dir}
    argv = [part.format_map(values) for part in contract.audit_argv]
    script = f"cd {shlex.quote(config.remote_repo or '')} && {shlex.join(argv)}"
    result = runner.run(ssh_argv(config, script))
    if result.returncode != 0:
        raise BridgeError(f"remote audit failed: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BridgeError("remote audit did not return JSON") from exc
    if not isinstance(payload, dict) or payload.get("valid") is not True:
        raise BridgeError("remote audit rejected the result bundle")
    return payload


def collect(
    *,
    repo_root: Path,
    config: BridgeConfig,
    contract: ExperimentContract,
    condition_id: str,
    profile: str,
    output_root: Path | None,
    registry_path: Path,
    runner: SystemRunner,
) -> tuple[dict[str, Any], Path]:
    condition_id = validate_run_id(condition_id)
    assignment = registry_assignment(
        registry_path, condition_id=condition_id, config=config
    )
    remote_bundle = posixpath.join(
        config.remote_repo or "", contract.remote_run_root, condition_id, "seed_0"
    )
    audit = remote_audit(config, contract, condition_id, remote_bundle, runner)
    identity = {
        "contract_id": contract.contract_id,
        "condition_id": condition_id,
        "profile": profile,
        "host_profile": config.host_profile,
        "audit": hashlib.sha256(json.dumps(audit, sort_keys=True).encode()).hexdigest(),
    }
    base = output_root or repo_root / contract.local_collection_root
    destination = _local_collection_root(base, condition_id, resume_identity=identity)
    selected = contract.profile_files(profile)
    command = build_rsync_argv(
        config,
        source=remote_bundle.rstrip("/") + "/",
        destination=str(destination) + "/",
        direction="pull",
        include_files=selected,
    )
    result = runner.run(command)
    failures = [] if result.returncode == 0 else [f"rsync exited {result.returncode}"]
    failures.extend(validate_downloaded_audit_hashes(destination, audit, contract, profile))
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "operation": "collect",
        "contract_id": contract.contract_id,
        "condition_id": condition_id,
        "profile": profile,
        "host_profile": config.host_profile,
        "registry_assignment": assignment,
        "remote_audit": audit,
        "command": command,
        "failures": failures,
        "valid": not failures,
    }
    if not failures:
        _complete_collection(destination)
    receipt_path = write_receipt(
        repo_root,
        "collect",
        _redact(receipt, [config.host or "", config.user or "", config.identity_file or ""]),
    )
    return receipt, receipt_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path(".sktlm-bridge.toml"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--host-profile")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate-contract")
    commands.add_parser("status")
    commands.add_parser("deploy-code")
    commands.add_parser("push-inputs")
    collect_parser = commands.add_parser("collect")
    collect_parser.add_argument("--condition", required=True)
    collect_parser.add_argument("--profile", choices=("report", "scientific", "full"), default="full")
    collect_parser.add_argument("--output-root", type=Path)
    collect_parser.add_argument(
        "--registry", type=Path, default=Path("configs/cloud/full_m0_host_registry.toml")
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    contract = load_experiment_contract(args.contract)
    if args.command == "validate-contract":
        print(json.dumps({"valid": True, "contract_id": contract.contract_id}, indent=2))
        return 0
    config = load_config(args.config, host_profile=args.host_profile)
    runner = SystemRunner()
    if args.command == "status":
        print(
            json.dumps(
                {
                    "contract_id": contract.contract_id,
                    "local_git": local_git_status(args.repo_root, runner),
                    "remote_configured": bool(config.host and config.remote_repo),
                    "host_profile": config.host_profile,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "deploy-code":
        receipt, path = deploy_code(
            repo_root=args.repo_root,
            config=config,
            contract=contract,
            runner=runner,
        )
        print(f"valid={str(receipt['valid']).lower()}")
        print(f"receipt={path}")
        return 0 if receipt["valid"] else 1
    if args.command == "push-inputs":
        receipt, path = push_inputs(
            repo_root=args.repo_root,
            config=config,
            contract=contract,
            runner=runner,
        )
        print(f"valid={str(receipt['valid']).lower()}")
        print(f"receipt={path}")
        return 0 if receipt["valid"] else 1
    if args.command == "collect":
        receipt, path = collect(
            repo_root=args.repo_root,
            config=config,
            contract=contract,
            condition_id=args.condition,
            profile=args.profile,
            output_root=args.output_root,
            registry_path=args.registry,
            runner=runner,
        )
        print(f"valid={str(receipt['valid']).lower()}")
        print(f"receipt={path}")
        return 0 if receipt["valid"] else 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
