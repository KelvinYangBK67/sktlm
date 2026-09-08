"""Strict, experiment-neutral cloud experiment contract loader."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import yaml


CONTRACT_SCHEMA = "sktlm-cloud-experiment-contract/v1"
DEPLOYMENT_MODES = frozenset({"git_bundle", "git_remote"})
PROFILE_NAMES = frozenset({"report", "scientific", "full"})
SECRET_RE = re.compile(
    r"(?:password|passwd|passphrase|secret|token|private[_-]?key|credential)",
    re.IGNORECASE,
)
IDENTITY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
BRANCH_RE = re.compile(r"[A-Za-z0-9._/-]+\Z")


class ContractError(ValueError):
    """Raised when a tracked experiment contract is unsafe or incomplete."""


def _reject_secret_fields(value: Any, location: str = "contract") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if SECRET_RE.search(str(key)):
                raise ContractError(
                    f"secret-bearing field is forbidden at {location}.{key}"
                )
            _reject_secret_fields(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_fields(item, f"{location}[{index}]")


def safe_relative_path(value: str, *, label: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or path.parts[0] in {"", "."}
    ):
        raise ContractError(f"{label} must be a normalized relative path: {value!r}")
    return path.as_posix()


def _validate_branch(value: object) -> str:
    branch = str(value)
    if (
        not BRANCH_RE.fullmatch(branch)
        or branch.startswith(("-", "/"))
        or branch.endswith((".", "/"))
        or ".." in branch
        or "@{" in branch
    ):
        raise ContractError(f"branch is invalid: {branch!r}")
    return branch


def _validate_identity(value: object, *, label: str) -> str:
    identity = str(value)
    if not IDENTITY_RE.fullmatch(identity) or identity in {".", ".."}:
        raise ContractError(f"{label} is invalid: {identity!r}")
    return identity


@dataclass(frozen=True, slots=True)
class InputSet:
    input_id: str
    paths: tuple[str, ...]
    validator_argv: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HostAssignment:
    workload_id: str
    host_role: str


@dataclass(frozen=True, slots=True)
class Deployment:
    mode: str
    require_published_head: bool


@dataclass(frozen=True, slots=True)
class ExperimentContract:
    contract_id: str
    branch: str
    deployment: Deployment
    input_sets: tuple[InputSet, ...]
    remote_run_root: str
    optional_metrics_root: str | None
    audit_argv: tuple[str, ...]
    audit_inventory_key: str
    profiles: Mapping[str, tuple[str, ...] | None]
    required_audited_files: tuple[str, ...]
    local_collection_root: str
    completion_schema: str
    host_registry: str | None
    host_assignments: tuple[HostAssignment, ...]

    def profile_files(self, profile: str) -> tuple[str, ...] | None:
        if profile not in PROFILE_NAMES or profile not in self.profiles:
            raise ContractError(f"unknown collection profile: {profile}")
        return self.profiles[profile]

    def host_role_for(self, workload_id: str) -> str | None:
        matches = [
            item.host_role
            for item in self.host_assignments
            if item.workload_id == workload_id
        ]
        if len(matches) > 1:
            raise ContractError(f"duplicate host assignment: {workload_id}")
        return matches[0] if matches else None

    @property
    def deployment_identity(self) -> dict[str, object]:
        return {
            "contract_id": self.contract_id,
            "branch": self.branch,
            "mode": self.deployment.mode,
            "require_published_head": self.deployment.require_published_head,
        }


def _load_input_sets(value: object) -> tuple[InputSet, ...]:
    if not isinstance(value, list) or not value:
        raise ContractError("experiment contract requires input_sets")
    inputs: list[InputSet] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "input_id",
            "paths",
            "validator_argv",
        }:
            raise ContractError(
                "each input set requires input_id, paths, and validator_argv"
            )
        paths = item["paths"]
        argv = item["validator_argv"]
        if (
            not isinstance(paths, list)
            or not paths
            or not isinstance(argv, list)
            or not argv
            or not all(isinstance(part, str) and part for part in argv)
        ):
            raise ContractError("input paths and validator argv must be non-empty lists")
        inputs.append(
            InputSet(
                input_id=_validate_identity(item["input_id"], label="input set ID"),
                paths=tuple(
                    safe_relative_path(str(item_path), label="input path")
                    for item_path in paths
                ),
                validator_argv=tuple(argv),
            )
        )
    if len({item.input_id for item in inputs}) != len(inputs):
        raise ContractError("input set IDs must be unique")
    return tuple(inputs)


def _load_profiles(value: object) -> Mapping[str, tuple[str, ...] | None]:
    if not isinstance(value, Mapping) or set(value) != PROFILE_NAMES:
        raise ContractError("collection profiles must declare report, scientific, and full")
    profiles: dict[str, tuple[str, ...] | None] = {}
    for name, paths in value.items():
        if paths is None:
            profiles[str(name)] = None
        elif isinstance(paths, list) and paths:
            profiles[str(name)] = tuple(
                safe_relative_path(str(item), label=f"{name} profile path")
                for item in paths
            )
        else:
            raise ContractError(f"profile {name} must be null or a non-empty path list")
    return profiles


def _load_host_assignments(value: object) -> tuple[HostAssignment, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ContractError("host_assignments must be a list")
    assignments: list[HostAssignment] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"workload_id", "host_role"}:
            raise ContractError(
                "each host assignment requires workload_id and host_role"
            )
        assignments.append(
            HostAssignment(
                workload_id=_validate_identity(
                    item["workload_id"], label="workload ID"
                ),
                host_role=_validate_identity(item["host_role"], label="host role"),
            )
        )
    ids = [item.workload_id for item in assignments]
    if len(set(ids)) != len(ids):
        raise ContractError("host assignment workload IDs must be unique")
    return tuple(assignments)


def load_experiment_contract(path: Path) -> ExperimentContract:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ContractError("experiment contract must be a mapping")
    _reject_secret_fields(value)
    allowed = {
        "schema_version",
        "contract_id",
        "branch",
        "deployment",
        "input_sets",
        "remote_run_root",
        "optional_metrics_root",
        "audit",
        "collection_profiles",
        "required_audited_files",
        "local_collection_root",
        "completion",
        "host_registry",
        "host_assignments",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ContractError(f"unknown experiment contract fields: {sorted(unknown)}")
    if value.get("schema_version") != CONTRACT_SCHEMA:
        raise ContractError(
            f"unsupported experiment contract schema: {value.get('schema_version')}"
        )

    deployment_value = value.get("deployment", {"mode": "git_remote"})
    if not isinstance(deployment_value, Mapping) or set(deployment_value) - {
        "mode",
        "require_published_head",
    }:
        raise ContractError("deployment accepts only mode and require_published_head")
    mode = str(deployment_value.get("mode", "git_remote"))
    if mode not in DEPLOYMENT_MODES:
        raise ContractError(f"unsupported deployment mode: {mode}")
    require_published = deployment_value.get("require_published_head", True)
    if not isinstance(require_published, bool):
        raise ContractError("deployment.require_published_head must be boolean")

    audit = value.get("audit")
    if not isinstance(audit, Mapping) or set(audit) != {
        "entrypoint_argv",
        "inventory_key",
    }:
        raise ContractError("audit requires entrypoint_argv and inventory_key")
    audit_argv = audit["entrypoint_argv"]
    if (
        not isinstance(audit_argv, list)
        or not audit_argv
        or not all(isinstance(part, str) and part for part in audit_argv)
    ):
        raise ContractError("audit entrypoint argv must be a non-empty string list")

    required = value.get("required_audited_files")
    if not isinstance(required, list) or not required:
        raise ContractError("required_audited_files must be non-empty")
    completion = value.get("completion")
    if not isinstance(completion, Mapping) or set(completion) != {"schema_version"}:
        raise ContractError("completion requires exactly schema_version")
    host_registry_value = value.get("host_registry")
    optional_metrics = value.get("optional_metrics_root")

    return ExperimentContract(
        contract_id=_validate_identity(value["contract_id"], label="contract ID"),
        branch=_validate_branch(value["branch"]),
        deployment=Deployment(mode=mode, require_published_head=require_published),
        input_sets=_load_input_sets(value.get("input_sets")),
        remote_run_root=safe_relative_path(
            str(value["remote_run_root"]), label="remote run root"
        ),
        optional_metrics_root=(
            safe_relative_path(str(optional_metrics), label="optional metrics root")
            if optional_metrics is not None
            else None
        ),
        audit_argv=tuple(audit_argv),
        audit_inventory_key=_validate_identity(
            audit["inventory_key"], label="audit inventory key"
        ),
        profiles=_load_profiles(value.get("collection_profiles")),
        required_audited_files=tuple(
            safe_relative_path(str(item), label="required audited file")
            for item in required
        ),
        local_collection_root=safe_relative_path(
            str(value["local_collection_root"]), label="local collection root"
        ),
        completion_schema=_validate_identity(
            completion["schema_version"], label="completion schema"
        ),
        host_registry=(
            safe_relative_path(str(host_registry_value), label="host registry")
            if host_registry_value is not None
            else None
        ),
        host_assignments=_load_host_assignments(value.get("host_assignments")),
    )
