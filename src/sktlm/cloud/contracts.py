"""Strict, experiment-neutral cloud bridge contract loader."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import yaml


CONTRACT_SCHEMA = "sktlm-cloud-experiment-contract/v1"
SECRET_RE = re.compile(r"(?:password|passwd|secret|token|private[_-]?key|credential)", re.I)
PROFILE_NAMES = frozenset({"report", "scientific", "full"})


class ContractError(ValueError):
    pass


def _reject_secret_fields(value: Any, location: str = "contract") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if SECRET_RE.search(str(key)):
                raise ContractError(f"secret-bearing field is forbidden at {location}.{key}")
            _reject_secret_fields(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_fields(item, f"{location}[{index}]")


def safe_relative_path(value: str, *, label: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts or path.parts[0] in {"", "."}:
        raise ContractError(f"{label} must be a normalized relative path: {value!r}")
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class InputSet:
    input_id: str
    paths: tuple[str, ...]
    validator_argv: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExperimentContract:
    contract_id: str
    branch: str
    input_sets: tuple[InputSet, ...]
    remote_run_root: str
    optional_metrics_root: str | None
    audit_argv: tuple[str, ...]
    audit_inventory_key: str
    profiles: Mapping[str, tuple[str, ...] | None]
    required_audited_files: tuple[str, ...]
    local_collection_root: str
    completion_schema: str

    def profile_files(self, profile: str) -> tuple[str, ...] | None:
        if profile not in PROFILE_NAMES or profile not in self.profiles:
            raise ContractError(f"unknown collection profile: {profile}")
        return self.profiles[profile]


def load_experiment_contract(path: Path) -> ExperimentContract:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ContractError("experiment contract must be a mapping")
    _reject_secret_fields(value)
    allowed = {
        "schema_version", "contract_id", "branch", "input_sets", "remote_run_root",
        "optional_metrics_root", "audit", "collection_profiles", "required_audited_files",
        "local_collection_root", "completion",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ContractError(f"unknown experiment contract fields: {sorted(unknown)}")
    if value.get("schema_version") != CONTRACT_SCHEMA:
        raise ContractError(f"unsupported experiment contract schema: {value.get('schema_version')}")

    raw_inputs = value.get("input_sets")
    if not isinstance(raw_inputs, list) or not raw_inputs:
        raise ContractError("experiment contract requires input_sets")
    inputs: list[InputSet] = []
    for item in raw_inputs:
        if not isinstance(item, Mapping) or set(item) != {"input_id", "paths", "validator_argv"}:
            raise ContractError("each input set requires input_id, paths, and validator_argv")
        paths = item["paths"]
        argv = item["validator_argv"]
        if not isinstance(paths, list) or not paths or not isinstance(argv, list) or not argv:
            raise ContractError("input paths and validator argv must be non-empty lists")
        inputs.append(
            InputSet(
                input_id=str(item["input_id"]),
                paths=tuple(
                    safe_relative_path(str(item_path), label="input path") for item_path in paths
                ),
                validator_argv=tuple(str(part) for part in argv),
            )
        )
    if len({item.input_id for item in inputs}) != len(inputs):
        raise ContractError("input set IDs must be unique")

    audit = value.get("audit")
    if not isinstance(audit, Mapping) or set(audit) != {"entrypoint_argv", "inventory_key"}:
        raise ContractError("audit requires entrypoint_argv and inventory_key")
    audit_argv = audit["entrypoint_argv"]
    if not isinstance(audit_argv, list) or not audit_argv:
        raise ContractError("audit entrypoint argv must be a non-empty list")

    raw_profiles = value.get("collection_profiles")
    if not isinstance(raw_profiles, Mapping) or set(raw_profiles) != PROFILE_NAMES:
        raise ContractError("collection profiles must declare report, scientific, and full")
    profiles: dict[str, tuple[str, ...] | None] = {}
    for name, paths in raw_profiles.items():
        if paths is None:
            profiles[str(name)] = None
        elif isinstance(paths, list) and paths:
            profiles[str(name)] = tuple(
                safe_relative_path(str(item), label=f"{name} profile path") for item in paths
            )
        else:
            raise ContractError(f"profile {name} must be null or a non-empty path list")

    required = value.get("required_audited_files")
    if not isinstance(required, list) or not required:
        raise ContractError("required_audited_files must be non-empty")
    required_paths = tuple(
        safe_relative_path(str(item), label="required audited file") for item in required
    )
    completion = value.get("completion")
    if not isinstance(completion, Mapping) or set(completion) != {"schema_version"}:
        raise ContractError("completion requires exactly schema_version")
    optional_metrics = value.get("optional_metrics_root")
    return ExperimentContract(
        contract_id=str(value["contract_id"]),
        branch=str(value["branch"]),
        input_sets=tuple(inputs),
        remote_run_root=safe_relative_path(str(value["remote_run_root"]), label="remote run root"),
        optional_metrics_root=(
            safe_relative_path(str(optional_metrics), label="optional metrics root")
            if optional_metrics is not None
            else None
        ),
        audit_argv=tuple(str(part) for part in audit_argv),
        audit_inventory_key=str(audit["inventory_key"]),
        profiles=profiles,
        required_audited_files=required_paths,
        local_collection_root=safe_relative_path(
            str(value["local_collection_root"]), label="local collection root"
        ),
        completion_schema=str(completion["schema_version"]),
    )
