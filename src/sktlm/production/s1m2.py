"""S1M2 pre-VM plans, execution manifests, audits, and worker selection.

This module is an engineering control plane.  It resolves the frozen six-cell
contract into the existing exact trainer and Linux process-tree metrics wrapper;
it contains no candidate, scoring, inference, or update logic.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import platform
import shutil
import shlex
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

from sktlm.cloud.contracts import load_experiment_contract
from sktlm.latent.training import (
    COMPACT_EXACT_S1M2,
    S1M2_MODEL,
    TrainingConfig,
    run_training,
)


CONTRACT_PATH = Path("configs/production/s1m2_six_cell.json")
CONTRACT_SCHEMA = "sktlm-s1m2-production-contract/v1"
PLAN_SCHEMA = "sktlm-s1m2-production-plan/v1"
RUN_SCHEMA = "sktlm-s1m2-run-manifest/v1"
ROUND1_SCHEMA = "sktlm-s1m2-round1-result/v1"
ROUND1_ATTESTATION_SCHEMA = "sktlm-s1m2-round1-attestation/v1"
ROUND2_SCHEMA = "sktlm-s1m2-round2-result/v1"
ROUND2_ATTESTATION_SCHEMA = "sktlm-s1m2-round2-attestation/v1"
ROUND3_CLOSURE_SCHEMA = "sktlm-s1m2-round3-closure/v1"
BOUND_VALIDATION_SCHEMA = "sktlm-s1m2-bounded-validation/v1"
SCRIPT_NEUTRAL_ARTIFACTS = (
    "piece_inventory.tsv",
    "lexical_diagnostics.tsv",
    "rule_usage.tsv",
)
ROUND1_WORKERS = (4, 8, 12, 16, 20, 24)
ROUND2_PRIMARY_WORKERS = (12, 16, 24)
FULL_EXECUTION_BUNDLE_CELL_ID = "s1m2_m0_devanagari_continuous"
FULL_EXECUTION_BUNDLE_PLAN = (
    "artifacts/s1m2_execution_bundle_plans/"
    "full_m0_devanagari_continuous_tp279047"
)
FULL_EXECUTION_BUNDLE_PLAN_SHA256 = (
    "9c828b6612d3e60b443511907dc2f731a08548be07caf513ea346e43b7d6414a"
)
FULL_IAST_EXECUTION_BUNDLE_CELL_ID = "s1m2_m0_prime_iast_continuous"
FULL_IAST_EXECUTION_BUNDLE_PLAN = (
    "artifacts/s1m2_execution_bundle_plans/"
    "full_m0_prime_iast_continuous_tp279047"
)
FULL_IAST_EXECUTION_BUNDLE_PLAN_SHA256 = (
    "9b88f7dd64d48f11b5730723f49acbec0a01ecb71c9391d1aea7a8ca5385cfca"
)
FULL_EXECUTION_BUNDLE_SPECS = {
    FULL_EXECUTION_BUNDLE_CELL_ID: {
        "execution_bundle_plan": FULL_EXECUTION_BUNDLE_PLAN,
        "execution_bundle_plan_sha256": FULL_EXECUTION_BUNDLE_PLAN_SHA256,
        "script": "devanagari",
        "condition": "continuous",
    },
    FULL_IAST_EXECUTION_BUNDLE_CELL_ID: {
        "execution_bundle_plan": FULL_IAST_EXECUTION_BUNDLE_PLAN,
        "execution_bundle_plan_sha256": FULL_IAST_EXECUTION_BUNDLE_PLAN_SHA256,
        "script": "iast_m0_prime",
        "condition": "continuous",
    },
}
COMPACT_EXACT_INFERENCE_COMMIT = "7752da2c453804a000dac83a36bd4aa58b9a0b8c"
COMPACT_OCCURRENCE_SUPPORT_FIX_COMMIT = (
    "ba4cc5f99752e66d01944869bea92b77b0dd32b7"
)
ROUND3_RETAINED_WORKERS = 12
ROUND3_REAL_OFFENDER_EVIDENCE = Path(
    "artifacts/s1m2_candidate_pressure/round3_real_offender_exactness_raw520.json"
)
ROUND3_WORKER_EQUIVALENCE_EVIDENCE = Path(
    "artifacts/s1m2_candidate_pressure/round3_local_worker_equivalence_w2_w4.json"
)
ROUND3_TAIL_EVIDENCE = tuple(
    Path(
        "artifacts/s1m2_candidate_pressure/round3_compact_tail/"
        f"raw{raw}_postfix.json"
    )
    for raw in (1002, 1410, 1841, 2484)
)


def _full_execution_bundle_specs(
    contract: dict[str, Any],
) -> dict[str, dict[str, str]]:
    """Return explicitly declared Full bundle plans, with legacy defaults."""

    declared = contract.get("full_execution_bundle_plans")
    if declared is None:
        return FULL_EXECUTION_BUNDLE_SPECS
    if not isinstance(declared, dict):
        raise ValueError("Full execution bundle declarations must be a mapping.")
    cells = {cell["cell_id"]: cell for cell in contract["cells"]}
    result: dict[str, dict[str, str]] = {}
    for cell_id, spec in declared.items():
        cell = cells.get(cell_id)
        if (
            cell is None
            or not isinstance(spec, dict)
            or spec.get("script") != cell["script"]
            or spec.get("condition") != cell["condition"]
            or not spec.get("execution_bundle_plan")
            or len(str(spec.get("execution_bundle_plan_sha256", ""))) != 64
        ):
            raise ValueError(f"Invalid Full execution bundle declaration: {cell_id}")
        result[str(cell_id)] = dict(spec)
    return result
CORE_HOST_ROLES = tuple(f"core-{index:02d}" for index in range(1, 7))
WORKER_CALIBRATION_DOCUMENTS = 72
WORKER_CALIBRATION_STRUCTURE_SHA256 = (
    "03ebdf71afc80f82492d9d36cc593ab50c380fd3b0b57689862ea8e98c7b39f8"
)
SCIENTIFIC_CONFIG_FIELDS = (
    "lexical_alpha",
    "complexity_weight",
    "complexity_tau",
    "whitespace_merge_penalty",
    "allow_whitespace_merge",
    "max_internal_matches",
    "max_segment_tokens",
    "analysis_top_k",
    "usage_posterior_threshold",
    "high_confidence_threshold",
    "low_count_threshold",
    "seed",
    "piece_max_length",
    "piece_boundary_probability",
    "piece_alpha",
    "piece_complexity_weight",
    "piece_complexity_kappa",
    "piece_complexity_beta",
    "piece_complexity_tau",
    "piece_base_stop_probability",
    "piece_min_reuse_occurrences",
    "piece_support_epsilon",
)
ENGINEERING_CONFIG_FIELDS = (
    "lexicon_cache_size",
    "flush_types",
    "piece_score_cache_entries",
    "piece_score_cache_bytes",
    "piece_form_cache_entries",
    "piece_form_cache_bytes",
    "piece_shared_token_marginals",
    "piece_shared_prefix_nodes",
    "piece_shared_top_k_piece_references",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    os.replace(temporary, path)


def _resolve(repo_root: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else repo_root / value


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def git_identity(repo_root: Path) -> dict[str, Any]:
    return {
        "git_sha": _git(repo_root, "rev-parse", "HEAD"),
        "branch": _git(repo_root, "branch", "--show-current"),
        "dirty_worktree": bool(_git(repo_root, "status", "--porcelain")),
    }


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not-installed"


def runtime_versions() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "sqlite": sqlite3.sqlite_version,
        "sktlm": _package_version("sktlm"),
    }


def load_contract(
    path: Path = CONTRACT_PATH,
    *,
    repo_root: Path = Path("."),
    verify_files: bool = True,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    resolved = _resolve(repo_root, path)
    contract = _read_json(resolved)
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise ValueError("Unsupported S1M2 production contract schema.")
    if contract.get("model") != S1M2_MODEL or contract.get("passes") != 3:
        raise ValueError("Production contract must select exact three-pass S1M2.")
    if contract.get("inference", {}).get("approximate_inference_allowed") is not False:
        raise ValueError("Approximate inference is forbidden by the production contract.")
    deployment = contract.get("deployment", {})
    if deployment.get("branch") != "exp/s1m2-reusable-pieces":
        raise ValueError("S1M2 deployment branch is not the production branch.")
    if deployment.get("mode") != "git_bundle":
        raise ValueError("S1M2 production deployment must use git_bundle.")
    if deployment.get("cloud_contract") != "configs/cloud/s1m2_prevm.yaml":
        raise ValueError("S1M2 cloud contract path is not the frozen path.")
    cells = contract.get("cells", [])
    if len(cells) != 6 or len({item.get("cell_id") for item in cells}) != 6:
        raise ValueError("Production contract must contain six unique cells.")
    combinations = {(item.get("script"), item.get("condition")) for item in cells}
    expected = {
        (script, condition)
        for script in ("iast", "devanagari")
        for condition in ("surface_word", "legacy_joined")
    } | {
        ("iast_m0_prime", "continuous"),
        ("devanagari", "continuous"),
    }
    if combinations != expected:
        raise ValueError("Six-cell script/condition mapping is not the frozen mapping.")
    continuous_iast = [
        item for item in cells if item.get("condition") == "continuous"
        and item.get("script") in {"iast", "iast_m0_prime"}
    ]
    if len(continuous_iast) != 1 or continuous_iast[0].get("substrate") != "M0-prime":
        raise ValueError("IAST continuous must fail closed unless it resolves to M0-prime.")
    workers = tuple(contract.get("round1", {}).get("workers", ()))
    if workers != ROUND1_WORKERS:
        raise ValueError("Round 1 worker matrix is not the frozen six-value matrix.")
    round1_hosts = tuple(contract.get("round1", {}).get("host_roles", ()))
    round2_hosts = tuple(contract.get("round2", {}).get("host_roles", ()))
    if round1_hosts != CORE_HOST_ROLES or round2_hosts != CORE_HOST_ROLES:
        raise ValueError("Round 1 and Round 2 must map exactly to core-01..core-06.")
    if len(set(round1_hosts)) != 6 or len(set(round2_hosts)) != 6:
        raise ValueError("Round 1 and Round 2 require six distinct host roles.")
    round2 = contract.get("round2", {})
    if (
        round2.get("mode") != "bundle_worker_recalibration"
        or tuple(round2.get("primary_workers", ())) != ROUND2_PRIMARY_WORKERS
        or round2.get("worker_20_status") != "RESERVED_IF_DECISION_CRITICAL"
        or round2.get("target_pressure") != 279047
        or round2.get("max_segments_per_bundle") != 256
        or round2.get("max_segment_tokens") != 128
        or round2.get("practical_tie_wall_fraction") != 0.1
    ):
        raise ValueError("Round 2 worker-recalibration policy is not frozen.")
    round2_jobs = round2.get("jobs", ())
    expected_round2 = tuple(
        (workload, workers, host)
        for workload, host_group in (
            ("representative", CORE_HOST_ROLES[:3]),
            ("stress", CORE_HOST_ROLES[3:]),
        )
        for workers, host in zip(ROUND2_PRIMARY_WORKERS, host_group, strict=True)
    )
    actual_round2 = tuple(
        (job.get("workload"), job.get("workers"), job.get("host_role"))
        for job in round2_jobs
    )
    if actual_round2 != expected_round2:
        raise ValueError("Round 2 does not contain the frozen six-job worker matrix.")
    for job in round2_jobs:
        if (
            job.get("cell_id") != "s1m2_m0_devanagari_continuous"
            or job.get("execution_bundle_plan_status")
            not in {"MATERIALIZATION_REQUIRED", "MATERIALIZED"}
            or not job.get("execution_bundle_plan")
        ):
            raise ValueError("Round 2 bundle-plan declaration is incomplete.")
        plan_sha = job.get("execution_bundle_plan_sha256")
        if plan_sha is not None and (
            len(str(plan_sha)) != 64
            or any(character not in "0123456789abcdef" for character in str(plan_sha))
        ):
            raise ValueError("Round 2 bundle-plan SHA-256 is invalid.")
    if verify_files:
        cloud_contract = load_experiment_contract(
            _resolve(repo_root, deployment["cloud_contract"])
        )
        if (
            cloud_contract.branch != deployment["branch"]
            or cloud_contract.deployment.mode != deployment["mode"]
        ):
            raise ValueError("Cloud and production deployment identities differ.")
        checks = [
            (
                contract["corpus"]["m0_manifest"],
                contract["corpus"]["m0_manifest_sha256"],
            ),
            (
                contract["corpus"]["m0_prime_manifest"],
                contract["corpus"]["m0_prime_manifest_sha256"],
            ),
            (contract["grammar"]["path"], contract["grammar"]["sha256"]),
        ]
        checks.extend(
            (item["document_list"], item["document_list_sha256"])
            for item in contract["workloads"].values()
            if item.get("document_list") is not None
        )
        for relative, expected_hash in checks:
            candidate = _resolve(repo_root, relative)
            if not candidate.is_file():
                raise FileNotFoundError(candidate)
            actual = _sha256(candidate)
            if actual != expected_hash:
                raise ValueError(
                    f"Production input hash mismatch for {relative}: "
                    f"expected {expected_hash}, got {actual}"
                )
    return contract


def _cell(contract: dict[str, Any], cell_id: str) -> dict[str, Any]:
    for item in contract["cells"]:
        if item["cell_id"] == cell_id:
            return item
    raise ValueError(f"Unknown production cell: {cell_id}")


def _manifest_details(
    contract: dict[str, Any], cell: dict[str, Any]
) -> tuple[str, str]:
    key = cell["manifest_key"]
    return contract["corpus"][key], contract["corpus"][f"{key}_sha256"]


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def _training_command(job: dict[str, Any], *, resume: bool = False) -> list[str]:
    command = [
        "python",
        "-m",
        "sktlm.experiments.training.latent_lexicon",
        "--manifest",
        job["manifest"],
        "--output-root",
        job["output_root"],
        "--run-id",
        job["run_id"],
        "--model",
        S1M2_MODEL,
        "--script",
        job["script"],
        "--condition",
        job["condition"],
        "--passes",
        str(job["passes"]),
        "--workers",
        str(job["workers"]),
    ]
    if job.get("document_list") is not None:
        command.extend(["--document-list", job["document_list"]])
    if job.get("max_lines_per_document") is not None:
        command.extend(
            ["--max-lines-per-document", str(job["max_lines_per_document"])]
        )
    if job.get("execution_bundle_plan") is not None:
        command.extend(
            ["--execution-bundle-plan", str(job["execution_bundle_plan"])]
        )
    for name in SCIENTIFIC_CONFIG_FIELDS + ENGINEERING_CONFIG_FIELDS:
        value = job["resolved_config"][name]
        if isinstance(value, bool):
            if not value:
                negative = {
                    "allow_whitespace_merge": "--no-whitespace-merge",
                    "piece_shared_token_marginals": "--no-piece-shared-token-marginals",
                }.get(name)
                if negative is None:
                    raise ValueError(f"No explicit negative CLI flag for {name}.")
                command.append(negative)
        else:
            command.extend([_flag(name), str(value)])
    if resume:
        command.append("--resume")
    return command


def _job(
    contract: dict[str, Any],
    *,
    plan_type: str,
    cell_id: str,
    workload_id: str,
    workers: int,
    output_root: Path,
    metrics_root: Path,
    host_role: str | None = None,
    execution_bundle_plan: str | None = None,
    execution_bundle_plan_sha256: str | None = None,
    execution_bundle_materialization_sha256: str | None = None,
) -> dict[str, Any]:
    cell = _cell(contract, cell_id)
    workload = contract["workloads"][workload_id]
    manifest, manifest_hash = _manifest_details(contract, cell)
    short_cell = cell_id.removeprefix("s1m2_")
    worker_suffix = (
        f"_w{workers}"
        if plan_type in {"round1", "round2"}
        else ""
    )
    run_id = (
        f"s1m2_{plan_type}_{short_cell}_{workload_id}"
        f"{worker_suffix}_p{workload.get('passes', contract['passes'])}"
    )
    metrics_id = run_id.removeprefix("s1m2_")
    resolved_config = {
        **contract["scientific_config"],
        **{
            key: value
            for key, value in contract["engineering_config"].items()
            if key in ENGINEERING_CONFIG_FIELDS
        },
    }
    job = {
        "job_id": run_id,
        "cell_id": cell_id,
        "workload_id": workload_id,
        "model": contract["model"],
        "substrate": cell["substrate"],
        "script": cell["script"],
        "condition": cell["condition"],
        "manifest": manifest,
        "manifest_sha256": manifest_hash,
        "document_list": workload.get("document_list"),
        "document_list_sha256": workload.get("document_list_sha256"),
        "max_lines_per_document": workload.get("max_lines_per_document"),
        "passes": workload.get("passes", contract["passes"]),
        "workers": workers,
        "run_id": run_id,
        "metrics_id": metrics_id,
        "output_root": output_root.as_posix(),
        "run_dir": (output_root / run_id).as_posix(),
        "metrics_root": metrics_root.as_posix(),
        "control_dir": (metrics_root / metrics_id).as_posix(),
        "host_role": "local-validation" if plan_type == "bounded" else host_role,
        "resolved_config": resolved_config,
        "resume_policy": copy.deepcopy(contract["resume_policy"]),
    }
    if execution_bundle_plan is not None:
        job.update(
            {
                "execution_bundle_plan": execution_bundle_plan,
                "execution_bundle_plan_sha256": execution_bundle_plan_sha256,
                "execution_bundle_materialization_sha256": (
                    execution_bundle_materialization_sha256
                ),
            }
        )
    job["training_command"] = _training_command(job)
    return job


def _base_plan(
    contract: dict[str, Any],
    *,
    contract_path: Path,
    plan_type: str,
    jobs: list[dict[str, Any]],
    identity: dict[str, Any],
) -> dict[str, Any]:
    if identity["dirty_worktree"]:
        raise RuntimeError("Production plans require a clean Git worktree.")
    plan = {
        "schema_version": PLAN_SCHEMA,
        "plan_type": plan_type,
        "status": "PREPARED_NOT_STARTED",
        "created_at": _utc_now(),
        "contract_path": contract_path.as_posix(),
        "production_contract_sha256": _canonical_sha256(contract),
        **identity,
        "jobs": jobs,
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def build_round1_plan(
    contract: dict[str, Any],
    *,
    contract_path: Path = CONTRACT_PATH,
    output_root: Path = Path("artifacts/latent_benchmarks"),
    metrics_root: Path = Path("artifacts/cloud_metrics"),
    identity: dict[str, Any],
) -> dict[str, Any]:
    settings = contract["round1"]
    jobs = [
        _job(
            contract,
            plan_type="round1",
            cell_id=settings["cell_id"],
            workload_id=settings["workload_id"],
            workers=workers,
            output_root=output_root,
            metrics_root=metrics_root,
            host_role=host_role,
        )
        for workers, host_role in zip(
            settings["workers"], settings["host_roles"], strict=True
        )
    ]
    plan = _base_plan(
        contract,
        contract_path=contract_path,
        plan_type="round1",
        jobs=jobs,
        identity=identity,
    )
    plan["expected_job_count"] = 6
    plan["scientific_invariant"] = (
        "All jobs share one frozen cell/workload/scientific configuration; "
        "only engineering worker count and physical host assignment differ."
    )
    plan["launch_mode"] = "six_way_parallel"
    plan["plan_sha256"] = _canonical_sha256(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )
    return plan


def build_bounded_plan(
    contract: dict[str, Any],
    *,
    contract_path: Path = CONTRACT_PATH,
    output_root: Path = Path("artifacts/s1m2_prevm_validation/runs"),
    metrics_root: Path = Path("artifacts/s1m2_prevm_validation/metrics"),
    identity: dict[str, Any],
) -> dict[str, Any]:
    jobs = [
        _job(
            contract,
            plan_type="bounded",
            cell_id=cell["cell_id"],
            workload_id="bounded_interface",
            workers=1,
            output_root=output_root,
            metrics_root=metrics_root,
        )
        for cell in contract["cells"]
    ]
    return _base_plan(
        contract,
        contract_path=contract_path,
        plan_type="bounded",
        jobs=jobs,
        identity=identity,
    )


def _bundle_plan_details(
    repo_root: Path,
    declaration: dict[str, Any],
    workload: dict[str, Any],
    scientific_config: dict[str, Any],
) -> dict[str, str]:
    relative = str(declaration["execution_bundle_plan"])
    root = _resolve(repo_root, relative).resolve()
    required = tuple(
        root / name
        for name in ("scan_summary.json", "summary.json", "bundles.jsonl", "documents.tsv")
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(
            "Round 2 bundle plans must be materialized before plan generation: "
            + ", ".join(str(path) for path in missing)
        )
    scan = _read_json(required[0])
    summary = _read_json(required[1])
    plan_sha = str(summary.get("plan_sha256", ""))
    if len(plan_sha) != 64 or any(
        character not in "0123456789abcdef" for character in plan_sha
    ):
        raise ValueError("Round 2 execution bundle plan has no valid plan SHA-256.")
    expected = {
        "script": declaration.get("script", "devanagari"),
        "condition": declaration.get("condition", "continuous"),
        "max_segment_tokens": scientific_config["max_segment_tokens"],
        "max_lines_per_document": workload.get("max_lines_per_document"),
        "target_pressure": declaration.get("target_pressure", 279047),
        "max_segments_per_bundle": declaration.get(
            "max_segments_per_bundle", 256
        ),
    }
    for name, value in expected.items():
        payload = summary if name in {"target_pressure", "max_segments_per_bundle"} else scan
        if payload.get(name) != value:
            raise ValueError(f"Round 2 bundle plan has invalid {name}.")
    for name in ("script", "condition", "max_segment_tokens", "max_lines_per_document"):
        if summary.get(name) != expected[name]:
            raise ValueError(f"Round 2 bundle-plan summary has invalid {name}.")
    if (
        scan.get("document_list") != workload["document_list"]
        or scan.get("document_list_sha256") != workload["document_list_sha256"]
    ):
        raise ValueError("Round 2 bundle plan document-list identity differs.")
    declared_sha = declaration.get("execution_bundle_plan_sha256")
    if declared_sha is not None and declared_sha != plan_sha:
        raise ValueError("Round 2 declared bundle-plan identity differs.")
    digest = hashlib.sha256()
    for path in required:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {
        "path": relative,
        "plan_sha256": plan_sha,
        "materialization_sha256": digest.hexdigest(),
    }


def build_round2_plan(
    contract: dict[str, Any],
    *,
    contract_path: Path = CONTRACT_PATH,
    output_root: Path = Path("artifacts/latent_benchmarks"),
    metrics_root: Path = Path("artifacts/cloud_metrics"),
    repo_root: Path = Path("."),
    identity: dict[str, Any],
) -> dict[str, Any]:
    round1 = contract["round1"]
    if (
        round1.get("status")
        != "MANUALLY_TERMINATED_AFTER_DIAGNOSTIC_CONVERGENCE"
        or round1.get("formal_winner") != "UNRESOLVED"
    ):
        raise RuntimeError("Round 2 requires the recorded Round 1 diagnostic closure.")
    details: dict[str, dict[str, str]] = {}
    jobs = []
    for declaration in contract["round2"]["jobs"]:
        workload_id = str(declaration["workload"])
        if workload_id not in details:
            details[workload_id] = _bundle_plan_details(
                repo_root,
                declaration,
                contract["workloads"][workload_id],
                contract["scientific_config"],
            )
        bundle = details[workload_id]
        jobs.append(
            _job(
                contract,
                plan_type="round2",
                cell_id=str(declaration["cell_id"]),
                workload_id=workload_id,
                workers=int(declaration["workers"]),
                output_root=output_root,
                metrics_root=metrics_root,
                host_role=str(declaration["host_role"]),
                execution_bundle_plan=bundle["path"],
                execution_bundle_plan_sha256=bundle["plan_sha256"],
                execution_bundle_materialization_sha256=(
                    bundle["materialization_sha256"]
                ),
            )
        )
    plan = _base_plan(
        contract,
        contract_path=contract_path,
        plan_type="round2",
        jobs=jobs,
        identity=identity,
    )
    plan.update(
        {
            "round1_diagnostic_status": round1["status"],
            "round1_formal_winner": round1["formal_winner"],
            "round2_mode": "bundle_worker_recalibration",
            "primary_workers": list(ROUND2_PRIMARY_WORKERS),
            "worker_20_status": contract["round2"]["worker_20_status"],
            "launch_mode": "six_way_parallel",
        }
    )
    plan["plan_sha256"] = _canonical_sha256(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )
    return plan


def select_worker_calibration_documents(
    structure: dict[str, Any],
) -> list[str]:
    """Select the frozen 72-stratum engineering calibration document set.

    The tracked list was derived only from the frozen continuous static-structure
    artifact identified by WORKER_CALIBRATION_STRUCTURE_SHA256.
    """

    cells = structure.get("cells")
    if not isinstance(cells, dict):
        raise ValueError("Static structure output has no cell mapping.")
    cell = cells.get("m0_devanagari_continuous")
    if not isinstance(cell, dict) or cell.get("script") != "devanagari":
        raise ValueError("Static structure output lacks the M0 Devanagari basis cell.")
    documents = cell.get("documents")
    stress = structure.get("selection", {}).get("stress")
    if not isinstance(documents, list) or not isinstance(stress, list) or len(stress) != 2:
        raise ValueError("Static structure output lacks documents or two stress paths.")
    stress_paths = {str(path) for path in stress}
    remaining = [
        item
        for item in documents
        if isinstance(item, dict) and item.get("relative_path") not in stress_paths
    ]
    if len(remaining) != len(documents) - 2:
        raise ValueError("Stress exclusion did not remove exactly two documents.")
    ordered = sorted(
        remaining,
        key=lambda item: (
            int(item["span_squared_phonemes"]),
            int(item["continuous_spans"]["max"]),
            int(item["phonemes"]),
            str(item["relative_path"]),
        ),
    )
    total = len(ordered)
    selected = []
    for index in range(WORKER_CALIBRATION_DOCUMENTS):
        lower = index * total // WORKER_CALIBRATION_DOCUMENTS
        upper = (index + 1) * total // WORKER_CALIBRATION_DOCUMENTS - 1
        if lower > upper:
            raise ValueError("A worker-calibration stratum is empty.")
        selected.append(str(ordered[(lower + upper) // 2]["relative_path"]))
    if len(selected) != WORKER_CALIBRATION_DOCUMENTS or len(set(selected)) != len(selected):
        raise ValueError("Worker calibration must select 72 distinct documents.")
    if stress_paths.intersection(selected):
        raise ValueError("Worker calibration includes a frozen stress document.")
    return selected


def _git_is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def _evidence_path(repo_root: Path, path: Path) -> str:
    resolved = _resolve(repo_root, path).resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _validate_historical_round2(
    round2: dict[str, Any], contract: dict[str, Any]
) -> None:
    if round2.get("schema_version") != ROUND2_SCHEMA:
        raise ValueError("Unsupported Round 2 result schema.")
    if round2.get("production_contract_sha256") != _canonical_sha256(contract):
        raise ValueError("Round 2 result does not bind the production contract.")
    if round2.get("ROUND2_STATUS") != "FAIL":
        raise ValueError("Round 3 requires the immutable Round 2 FAIL result.")
    if round2.get("WINNER_WORKERS") is not None:
        raise ValueError("Historical Round 2 must retain no formal winner.")
    if len(round2.get("jobs", ())) != 6:
        raise ValueError("Round 2 result does not contain the primary six jobs.")
    if len(str(round2.get("plan_sha256", ""))) != 64:
        raise ValueError("Round 2 result has no valid plan identity.")
    if not any(int(job.get("candidate_overflow", 0)) > 0 for job in round2["jobs"]):
        raise ValueError("Round 2 FAIL does not retain candidate-overflow evidence.")


def _validate_round3_evidence(
    real_offender: dict[str, Any],
    worker_equivalence: dict[str, Any],
    tail_cases: tuple[dict[str, Any], ...],
) -> None:
    case = real_offender.get("case", {})
    compact = real_offender.get("compact", {})
    scientific = real_offender.get("scientific_equivalence", {})
    if (
        real_offender.get("status") != "PASS"
        or real_offender.get("gate")
        != "REAL_OFFENDER_COMPACT_VS_LEGACY_EXACTNESS"
        or case.get("raw_internal_matches") != 520
        or case.get("retained_internal_matches") != 520
        or compact.get("support_truncation_tokens") != 0
        or compact.get("shared_batch_fallbacks") != 0
        or not scientific
        or any(value != "PASS" for value in scientific.values())
    ):
        raise ValueError("Round 3 real-offender exactness evidence failed.")

    artifacts = worker_equivalence.get("scientific_artifacts", {})
    if (
        worker_equivalence.get("status") != "PASS"
        or worker_equivalence.get("gate")
        != "COMPACT_LOCAL_WORKER_SCIENTIFIC_EQUIVALENCE"
        or worker_equivalence.get("scientific_artifacts_all_byte_identical")
        is not True
        or worker_equivalence.get("workers") != [2, 4]
        or worker_equivalence.get("same_bundle_plan") is not True
        or worker_equivalence.get("training_history") != "EXACT"
        or worker_equivalence.get("piece_lexicon_state") != "EXACT"
        or worker_equivalence.get("worker_selection_reopened") is not False
        or worker_equivalence.get("round2_engineering_preference_retained")
        != ROUND3_RETAINED_WORKERS
        or not artifacts
        or any(item.get("equal") is not True for item in artifacts.values())
    ):
        raise ValueError("Round 3 worker-equivalence evidence failed.")

    expected_raws = (1002, 1410, 1841, 2484)
    if len(tail_cases) != len(expected_raws):
        raise ValueError("Round 3 pressure-tail evidence is incomplete.")
    for expected_raw, evidence in zip(expected_raws, tail_cases, strict=True):
        case = evidence.get("case", {})
        compact = evidence.get("compact", {})
        posterior_mass = evidence.get("posterior_mass")
        if (
            evidence.get("status") != "PASS"
            or evidence.get("gate") != "COMPACT_PRODUCTION_PASS1_TAIL"
            or case.get("raw") != expected_raw
            or case.get("retained") != expected_raw
            or compact.get("support_truncation_tokens") != 0
            or compact.get("shared_batch_fallbacks") != 0
            or not isinstance(posterior_mass, (int, float))
            or abs(float(posterior_mass) - 1.0) > 1e-12
        ):
            raise ValueError(
                f"Round 3 pressure-tail evidence failed for raw={expected_raw}."
            )


def validate_round3_closure(
    closure: dict[str, Any],
    contract: dict[str, Any],
    round2: dict[str, Any],
    *,
    repo_root: Path = Path("."),
) -> None:
    if closure.get("schema_version") != ROUND3_CLOSURE_SCHEMA:
        raise ValueError("Unsupported Round 3 closure schema.")
    expected_hash = _canonical_sha256(
        {key: value for key, value in closure.items() if key != "closure_sha256"}
    )
    if closure.get("closure_sha256") != expected_hash:
        raise ValueError("Round 3 closure SHA-256 mismatch.")
    if closure.get("production_contract_sha256") != _canonical_sha256(contract):
        raise ValueError("Round 3 closure does not bind the production contract.")
    _validate_historical_round2(round2, contract)
    round2_path = _resolve(repo_root, closure.get("round2_result_path", ""))
    if not round2_path.is_file():
        raise ValueError("Round 3 closure Round 2 artifact is missing.")
    if closure.get("round2_result_sha256") != _sha256(round2_path):
        raise ValueError("Round 3 closure Round 2 artifact hash differs.")
    if closure.get("round2_payload_sha256") != _canonical_sha256(round2):
        raise ValueError("Round 3 closure Round 2 payload differs.")
    if _canonical_sha256(_read_json(round2_path)) != _canonical_sha256(round2):
        raise ValueError("Supplied Round 2 result differs from the bound artifact.")
    if (
        closure.get("round2_formal_status") != "FAIL_CANDIDATE_OVERFLOW"
        or closure.get("round2_formal_winner") is not None
        or closure.get("compact_git_sha") != COMPACT_EXACT_INFERENCE_COMMIT
        or closure.get("compact_occurrence_support_fix_git_sha")
        != COMPACT_OCCURRENCE_SUPPORT_FIX_COMMIT
    ):
        raise ValueError("Round 3 closure changes immutable history or code identity.")
    for commit in (
        COMPACT_EXACT_INFERENCE_COMMIT,
        COMPACT_OCCURRENCE_SUPPORT_FIX_COMMIT,
    ):
        if not _git_is_ancestor(repo_root, commit, "HEAD"):
            raise ValueError(f"Required compact commit is not in current history: {commit}")

    evidence_entries = closure.get("evidence", {})
    try:
        real_entry = evidence_entries["real_offender_exactness"]
        worker_entry = evidence_entries["local_worker_equivalence"]
        tail_entries = tuple(evidence_entries["pressure_tail"])
    except (KeyError, TypeError):
        raise ValueError("Round 3 closure evidence manifest is incomplete.") from None

    def load_entry(entry: dict[str, Any]) -> dict[str, Any]:
        path = _resolve(repo_root, entry.get("path", ""))
        if not path.is_file() or entry.get("sha256") != _sha256(path):
            raise ValueError("Round 3 evidence file identity differs.")
        return _read_json(path)

    real = load_entry(real_entry)
    worker = load_entry(worker_entry)
    tails = tuple(load_entry(entry) for entry in tail_entries)
    _validate_round3_evidence(real, worker, tails)
    if (
        closure.get("candidate_overflow_blocker")
        != "RESOLVED_BY_COMPACT_EXACT_INFERENCE"
        or closure.get("worker_selection_reopened") is not False
        or closure.get("retained_workers") != ROUND3_RETAINED_WORKERS
        or closure.get("round3_status") != "PASS"
        or closure.get("round3_vm_required") is not False
        or closure.get("w20_active_path") != "RETIRED"
        or closure.get("legacy_3h_gate") != "NOT_APPLICABLE"
    ):
        raise ValueError("Round 3 closure eligibility fields are invalid.")


def build_round3_closure(
    contract: dict[str, Any],
    round2_result_path: Path,
    *,
    real_offender_path: Path = ROUND3_REAL_OFFENDER_EVIDENCE,
    worker_equivalence_path: Path = ROUND3_WORKER_EQUIVALENCE_EVIDENCE,
    tail_paths: tuple[Path, ...] = ROUND3_TAIL_EVIDENCE,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    round2_path = _resolve(repo_root, round2_result_path)
    round2 = _read_json(round2_path)
    _validate_historical_round2(round2, contract)
    real = _read_json(_resolve(repo_root, real_offender_path))
    worker = _read_json(_resolve(repo_root, worker_equivalence_path))
    tails = tuple(_read_json(_resolve(repo_root, path)) for path in tail_paths)
    _validate_round3_evidence(real, worker, tails)
    closure = {
        "schema_version": ROUND3_CLOSURE_SCHEMA,
        "production_contract_sha256": _canonical_sha256(contract),
        "round2_result_path": _evidence_path(repo_root, round2_path),
        "round2_result_sha256": _sha256(round2_path),
        "round2_payload_sha256": _canonical_sha256(round2),
        "round2_formal_status": "FAIL_CANDIDATE_OVERFLOW",
        "round2_formal_winner": None,
        "compact_git_sha": COMPACT_EXACT_INFERENCE_COMMIT,
        "compact_occurrence_support_fix_git_sha": (
            COMPACT_OCCURRENCE_SUPPORT_FIX_COMMIT
        ),
        "evidence": {
            "real_offender_exactness": {
                "path": _evidence_path(repo_root, real_offender_path),
                "sha256": _sha256(_resolve(repo_root, real_offender_path)),
            },
            "local_worker_equivalence": {
                "path": _evidence_path(repo_root, worker_equivalence_path),
                "sha256": _sha256(_resolve(repo_root, worker_equivalence_path)),
            },
            "pressure_tail": [
                {
                    "path": _evidence_path(repo_root, path),
                    "sha256": _sha256(_resolve(repo_root, path)),
                }
                for path in tail_paths
            ],
        },
        "real_offender_exactness": "PASS",
        "local_worker_equivalence": "PASS",
        "pressure_tail": "PASS",
        "full_max_raw": 2484,
        "worker_selection_reopened": False,
        "retained_workers": ROUND3_RETAINED_WORKERS,
        "candidate_overflow_blocker": "RESOLVED_BY_COMPACT_EXACT_INFERENCE",
        "round3_status": "PASS",
        "round3_vm_required": False,
        "w20_active_path": "RETIRED",
        "legacy_3h_gate": "NOT_APPLICABLE",
    }
    closure["closure_sha256"] = _canonical_sha256(closure)
    validate_round3_closure(closure, contract, round2, repo_root=repo_root)
    return closure


def build_final_plan(
    contract: dict[str, Any],
    round2: dict[str, Any],
    round3_closure: dict[str, Any],
    *,
    contract_path: Path = CONTRACT_PATH,
    output_root: Path = Path("artifacts/latent_benchmarks"),
    metrics_root: Path = Path("artifacts/cloud_metrics"),
    identity: dict[str, Any],
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    validate_round3_closure(
        round3_closure, contract, round2, repo_root=repo_root
    )
    winner = int(round3_closure["retained_workers"])

    full_bundles: dict[str, dict[str, str]] = {}
    bundle_specs = _full_execution_bundle_specs(contract)
    for bundle_cell_id, bundle_spec in bundle_specs.items():
        declaration = {
            **bundle_spec,
            "target_pressure": contract["round2"]["target_pressure"],
            "max_segments_per_bundle": contract["round2"]["max_segments_per_bundle"],
        }
        full_bundle = _bundle_plan_details(
            repo_root.resolve(),
            declaration,
            contract["workloads"]["full"],
            contract["scientific_config"],
        )
        if (
            full_bundle["plan_sha256"]
            != bundle_spec["execution_bundle_plan_sha256"]
        ):
            raise RuntimeError(
                f"Full execution bundle plan identity differs for {bundle_cell_id}."
            )
        full_bundles[bundle_cell_id] = full_bundle

    jobs = []
    for cell, host_role in zip(
        contract["cells"], CORE_HOST_ROLES, strict=True
    ):
        bundle_kwargs = {}
        full_bundle = full_bundles.get(cell["cell_id"])
        if full_bundle is not None:
            bundle_kwargs = {
                "execution_bundle_plan": full_bundle["path"],
                "execution_bundle_plan_sha256": full_bundle["plan_sha256"],
                "execution_bundle_materialization_sha256": (
                    full_bundle["materialization_sha256"]
                ),
            }
        jobs.append(
            _job(
                contract,
                plan_type="full",
                cell_id=cell["cell_id"],
                workload_id="full",
                workers=winner,
                output_root=output_root,
                metrics_root=metrics_root,
                host_role=host_role,
                **bundle_kwargs,
            )
        )
    plan = _base_plan(
        contract,
        contract_path=contract_path,
        plan_type="full",
        jobs=jobs,
        identity=identity,
    )
    plan.update(
        {
            "full_worker_selection": {
                "round2_result_sha256": round3_closure["round2_result_sha256"],
                "round3_closure_sha256": round3_closure["closure_sha256"],
                "workers": winner,
                "basis": (
                    "round2_engineering_preference_retained_by_round3_closure"
                ),
            },
            "ROUND2_FORMAL_RESULT": "PRESERVED_FAIL",
            "ROUND2_FORMAL_WINNER": None,
            "ROUND3_STATUS": "PASS",
            "ROUND3_TO_FULL_CONTROL_PLANE": "PASS",
            "FULL_ELIGIBILITY": "PASS",
            "FULL_WORKERS": winner,
            "WORKER_SELECTION_REOPENED": "NO",
            "W20_ACTIVE_PATH": "RETIRED",
            "LEGACY_3H_GATE": "NOT_APPLICABLE",
            "FULL_M0_AUTHORIZED": "NO",
            "FULL_M0_SIX_CELL_CONFIG": "FROZEN",
            "FULL_M0_LAUNCH_PLAN": "PREPARED",
            "FULL_M0_PROCESS_RUNNING": "NO",
        }
    )
    plan["plan_sha256"] = _canonical_sha256(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )
    return plan


def _validate_plan(plan: dict[str, Any], contract: dict[str, Any]) -> None:
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise ValueError("Unsupported production plan schema.")
    expected_hash = _canonical_sha256(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )
    if plan.get("plan_sha256") != expected_hash:
        raise ValueError("Production plan SHA-256 mismatch.")
    if plan.get("production_contract_sha256") != _canonical_sha256(contract):
        raise ValueError("Plan does not bind the supplied production contract.")
    if plan.get("dirty_worktree") is not False:
        raise ValueError("Production plan must bind a clean Git worktree.")
    ids = [job["job_id"] for job in plan.get("jobs", ())]
    if len(ids) != len(set(ids)):
        raise ValueError("Production plan contains duplicate job IDs.")
    plan_type = plan.get("plan_type")
    jobs = plan.get("jobs", [])
    actual_cells = [(job.get("cell_id"), job.get("workload_id")) for job in jobs]
    if plan_type == "round1":
        expected_cells = [
            (contract["round1"]["cell_id"], contract["round1"]["workload_id"])
        ] * len(ROUND1_WORKERS)
        if actual_cells != expected_cells or tuple(
            job.get("workers") for job in jobs
        ) != ROUND1_WORKERS:
            raise ValueError("Round 1 plan differs from the frozen matrix.")
        if tuple(job.get("host_role") for job in jobs) != tuple(
            contract["round1"]["host_roles"]
        ):
            raise ValueError("Round 1 plan differs from the frozen host mapping.")
    elif plan_type == "round2":
        declarations = contract["round2"]["jobs"]
        expected_cells = [
            (item["cell_id"], item["workload"]) for item in declarations
        ]
        if actual_cells != expected_cells:
            raise ValueError("Round 2 plan differs from the frozen matrix.")
        if tuple(job.get("host_role") for job in jobs) != tuple(
            item["host_role"] for item in declarations
        ) or tuple(job.get("workers") for job in jobs) != tuple(
            item["workers"] for item in declarations
        ):
            raise ValueError("Round 2 plan differs from the frozen host mapping.")
    elif plan_type in {"bounded", "full"}:
        workload_id = "bounded_interface" if plan_type == "bounded" else "full"
        expected_cells = [(cell["cell_id"], workload_id) for cell in contract["cells"]]
        if actual_cells != expected_cells:
            raise ValueError(f"{plan_type} plan differs from the six-cell contract.")
    else:
        raise ValueError(f"Unsupported production plan type: {plan_type}")
    if plan_type not in {"round1", "round2"}:
        workers = {job.get("workers") for job in jobs}
        if len(workers) != 1 or not workers <= set(ROUND1_WORKERS) | {1}:
            raise ValueError("Production plan has an invalid worker assignment.")
        if plan_type == "bounded" and workers != {1}:
            raise ValueError("Bounded validation must use one worker.")
        if plan_type == "full":
            selection = plan.get("full_worker_selection", {})
            if (
                workers != {ROUND3_RETAINED_WORKERS}
                or selection.get("workers") != ROUND3_RETAINED_WORKERS
                or selection.get("basis")
                != "round2_engineering_preference_retained_by_round3_closure"
                or len(str(selection.get("round2_result_sha256", ""))) != 64
                or len(str(selection.get("round3_closure_sha256", ""))) != 64
                or plan.get("ROUND2_FORMAL_RESULT") != "PRESERVED_FAIL"
                or plan.get("ROUND2_FORMAL_WINNER") is not None
                or plan.get("ROUND3_STATUS") != "PASS"
                or plan.get("ROUND3_TO_FULL_CONTROL_PLANE") != "PASS"
                or plan.get("FULL_ELIGIBILITY") != "PASS"
                or plan.get("FULL_WORKERS") != ROUND3_RETAINED_WORKERS
                or plan.get("WORKER_SELECTION_REOPENED") != "NO"
                or plan.get("W20_ACTIVE_PATH") != "RETIRED"
                or plan.get("LEGACY_3H_GATE") != "NOT_APPLICABLE"
                or plan.get("FULL_M0_AUTHORIZED") != "NO"
            ):
                raise ValueError("Full plan has invalid Round 3 eligibility binding.")
    expected_config = {
        **contract["scientific_config"],
        **{
            key: value
            for key, value in contract["engineering_config"].items()
            if key in ENGINEERING_CONFIG_FIELDS
        },
    }
    for job in jobs:
        cell = _cell(contract, job["cell_id"])
        workload = contract["workloads"][job["workload_id"]]
        manifest, manifest_hash = _manifest_details(contract, cell)
        expected = {
            "model": contract["model"],
            "substrate": cell["substrate"],
            "script": cell["script"],
            "condition": cell["condition"],
            "manifest": manifest,
            "manifest_sha256": manifest_hash,
            "document_list": workload.get("document_list"),
            "document_list_sha256": workload.get("document_list_sha256"),
            "max_lines_per_document": workload.get("max_lines_per_document"),
            "passes": workload.get("passes", contract["passes"]),
            "resolved_config": expected_config,
        }
        for name, value in expected.items():
            if job.get(name) != value:
                raise ValueError(f"Plan job {job.get('job_id')} has invalid {name}.")
        if plan_type == "round2":
            for name in (
                "execution_bundle_plan",
                "execution_bundle_plan_sha256",
                "execution_bundle_materialization_sha256",
            ):
                value = job.get(name)
                if not value or (name.endswith("sha256") and len(str(value)) != 64):
                    raise ValueError(
                        f"Plan job {job.get('job_id')} has invalid {name}."
                    )
        elif plan_type == "full":
            bundle_fields = (
                "execution_bundle_plan",
                "execution_bundle_plan_sha256",
                "execution_bundle_materialization_sha256",
            )
            bundle_spec = _full_execution_bundle_specs(contract).get(job["cell_id"])
            if bundle_spec is not None:
                if (
                    job.get("execution_bundle_plan")
                    != bundle_spec["execution_bundle_plan"]
                ):
                    raise ValueError(
                        "Full job has invalid execution bundle plan."
                    )
                if (
                    job.get("execution_bundle_plan_sha256")
                    != bundle_spec["execution_bundle_plan_sha256"]
                ):
                    raise ValueError(
                        "Full job has invalid bundle-plan identity."
                    )
                materialization_sha = job.get(
                    "execution_bundle_materialization_sha256"
                )
                if not materialization_sha or len(str(materialization_sha)) != 64:
                    raise ValueError(
                        "Full job has invalid bundle materialization."
                    )
            elif any(job.get(name) is not None for name in bundle_fields):
                raise ValueError(
                    "Only explicitly declared Full cells may use execution bundle plans."
                )
        if job.get("training_command") != _training_command(job):
            raise ValueError(f"Plan job {job['job_id']} has an invalid trainer command.")
        if Path(job["run_dir"]) != Path(job["output_root"]) / job["run_id"]:
            raise ValueError(f"Plan job {job['job_id']} has an invalid run path.")
        if Path(job["control_dir"]) != Path(job["metrics_root"]) / job["metrics_id"]:
            raise ValueError(f"Plan job {job['job_id']} has an invalid metrics path.")


def _job_from_plan(plan: dict[str, Any], job_id: str) -> dict[str, Any]:
    for job in plan["jobs"]:
        if job["job_id"] == job_id:
            return job
    raise ValueError(f"Unknown plan job: {job_id}")


def _config_for_job(job: dict[str, Any], *, resume: bool) -> TrainingConfig:
    values = {
        "manifest": Path(job["manifest"]),
        "document_list": (
            None if job.get("document_list") is None else Path(job["document_list"])
        ),
        "output_root": Path(job["output_root"]),
        "run_id": job["run_id"],
        "model": S1M2_MODEL,
        "script": job["script"],
        "condition": job["condition"],
        "passes": int(job["passes"]),
        "workers": int(job["workers"]),
        "max_lines_per_document": job.get("max_lines_per_document"),
        "execution_bundle_plan": (
            None
            if job.get("execution_bundle_plan") is None
            else Path(job["execution_bundle_plan"])
        ),
        "resume": resume,
        **job["resolved_config"],
    }
    return TrainingConfig(**values)


def _audit_artifacts(
    job: dict[str, Any],
    contract: dict[str, Any],
    *,
    repo_root: Path,
    metrics_summary: Path | None,
) -> dict[str, Any]:
    failures: list[str] = []
    run_dir = _resolve(repo_root, job["run_dir"])
    required = [
        *contract["artifact_contract"]["scientific"],
        *contract["artifact_contract"]["operational"],
    ]
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        return {"valid": False, "failures": [f"missing artifacts: {missing}"]}
    config = _read_json(run_dir / "config.json")
    provenance = _read_json(run_dir / "provenance.json")
    checkpoint = _read_json(run_dir / "checkpoint.json")
    summary = _read_json(run_dir / "summary.json")
    storage = _read_json(run_dir / "storage_manifest.json")
    expected_config = _config_for_job(job, resume=False).payload()
    if config != expected_config:
        failures.append("trainer config differs from the resolved job config")
    if checkpoint.get("completed_passes") != job["passes"]:
        failures.append("checkpoint pass count differs")
    if checkpoint.get("inspection_complete") is not True:
        failures.append("inspection is incomplete")
    if summary.get("overflowed_tokens") != 0:
        failures.append("candidate overflow is nonzero")
    if provenance.get("git_commit") is None:
        failures.append("trainer provenance has no Git commit")
    if provenance.get("freeze_id") != contract["corpus"]["freeze_id"]:
        failures.append("corpus freeze identity differs")
    if provenance.get("rules_sha256") != contract["grammar"]["sha256"]:
        failures.append("grammar hash differs")
    if provenance.get("external_rule_count") != contract["grammar"]["rule_count"]:
        failures.append("external rule count differs")
    if provenance.get("document_list_sha256") != job.get("document_list_sha256"):
        failures.append("document-list hash differs")
    if provenance.get("script") != job["script"] or provenance.get("condition") != job["condition"]:
        failures.append("trainer cell identity differs")
    if job.get("execution_bundle_plan") is not None:
        bundle_provenance = provenance.get("training_execution_bundle_plan", {})
        if (
            bundle_provenance.get("plan_sha256")
            != job.get("execution_bundle_plan_sha256")
            or bundle_provenance.get("materialization_sha256")
            != job.get("execution_bundle_materialization_sha256")
        ):
            failures.append("execution bundle plan provenance differs")
    if storage.get("status") != "COMPACT":
        failures.append("completed S1M2 SQLite state is not compact")
    topology = storage.get("compiled_topology", {})
    if topology.get("mutable_scores_or_posteriors_stored") is not False:
        failures.append("topology archive claims mutable scientific state")
    legacy_topology_required = not COMPACT_EXACT_S1M2
    if legacy_topology_required and not tuple(
        run_dir.glob(contract["artifact_contract"]["topology_glob"])
    ):
        failures.append("no compiled topology archives were retained")
    residue = sorted(
        str(path.relative_to(run_dir))
        for path in run_dir.rglob("*")
        if path.is_file()
        and (path.name.endswith(".tmp") or path.name.startswith("learner.sqlite-"))
    )
    if residue:
        failures.append(f"temporary/SQLite sidecar residue: {residue}")
    try:
        uri = (run_dir / "learner.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True)
        try:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                failures.append("SQLite quick_check failed")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if tables != {"metadata", "piece_lexicon"}:
                failures.append(f"unexpected completed SQLite tables: {sorted(tables)}")
        finally:
            connection.close()
    except sqlite3.Error as error:
        failures.append(f"SQLite audit failed: {error}")
    metrics: dict[str, Any] | None = None
    if metrics_summary is not None:
        if not metrics_summary.is_file():
            failures.append(f"missing process metrics: {metrics_summary}")
        else:
            metrics = _read_json(metrics_summary)
            if metrics.get("return_code") != 0:
                failures.append("process-tree wrapper return code is nonzero")
            required_metrics = (
                "wall_seconds",
                "peak_process_tree_rss_bytes",
                "peak_watched_run_bytes",
                "sampled_process_tree_cpu_seconds",
                "host_memory_bytes",
                "filesystem_free_bytes_end",
            )
            missing_metrics = [
                name for name in required_metrics if metrics.get(name) is None
            ]
            if missing_metrics:
                failures.append(f"process telemetry fields are missing: {missing_metrics}")
    scientific = {
        name: {"bytes": (run_dir / name).stat().st_size, "sha256": _sha256(run_dir / name)}
        for name in contract["artifact_contract"]["scientific"]
    }
    return {
        "valid": not failures,
        "failures": failures,
        "run_dir": run_dir.as_posix(),
        "legacy_topology_required": legacy_topology_required,
        "completion": {
            "completed_passes": checkpoint.get("completed_passes"),
            "inspection_complete": checkpoint.get("inspection_complete"),
            "documents": summary.get("documents"),
            "segments": summary.get("segments"),
            "characters": summary.get("characters"),
            "overflowed_tokens": summary.get("overflowed_tokens"),
        },
        "scientific_artifacts": scientific,
        "metrics": metrics,
    }


def _manifest_path(repo_root: Path, job: dict[str, Any]) -> Path:
    return _resolve(repo_root, job["control_dir"]) / "run_manifest.json"


def audit_job(
    plan: dict[str, Any],
    job: dict[str, Any],
    contract: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    manifest_path = _manifest_path(repo_root, job)
    if not manifest_path.is_file():
        return {"valid": False, "failures": [f"missing run manifest: {manifest_path}"]}
    manifest = _read_json(manifest_path)
    failures: list[str] = []
    if manifest.get("schema_version") != RUN_SCHEMA:
        failures.append("run manifest schema differs")
    if manifest.get("plan_sha256") != plan["plan_sha256"]:
        failures.append("run manifest plan identity differs")
    for name in contract["provenance_required_fields"]:
        if name not in manifest:
            failures.append(f"run manifest missing provenance field: {name}")
    expected = {
        "git_sha": plan["git_sha"],
        "branch": plan["branch"],
        "dirty_worktree": False,
        "cell_id": job["cell_id"],
        "workload_id": job["workload_id"],
        "corpus_freeze_id": contract["corpus"]["freeze_id"],
        "input_manifest_sha256": job["manifest_sha256"],
        "representation_manifest_sha256": job["manifest_sha256"],
        "grammar_sha256": contract["grammar"]["sha256"],
        "production_contract_sha256": plan["production_contract_sha256"],
        "workers": job["workers"],
        "run_id": job["run_id"],
        "metrics_id": job["metrics_id"],
        "host_id": job["host_role"],
    }
    for name, value in expected.items():
        if manifest.get(name) != value:
            failures.append(f"run manifest {name} differs")
    attempts = manifest.get("resume_history")
    if not isinstance(attempts, list) or not attempts:
        failures.append("run manifest has no execution/resume history")
        metrics_path = None
    else:
        metrics_path = _resolve(repo_root, attempts[-1]["metrics_dir"]) / "process_tree_summary.json"
    artifact_audit = _audit_artifacts(
        job, contract, repo_root=repo_root, metrics_summary=metrics_path
    )
    failures.extend(artifact_audit["failures"])
    if artifact_audit.get("valid") and manifest.get("result_status") != "PASS":
        failures.append("run manifest result status is not PASS")
    return {
        "valid": not failures,
        "failures": failures,
        "run_manifest": manifest,
        "artifact_audit": artifact_audit,
    }


def run_job(
    *,
    plan_path: Path,
    job_id: str,
    contract_path: Path,
    repo_root: Path,
    host_id: str,
    resume: bool,
) -> int:
    repo_root = repo_root.resolve()
    contract = load_contract(contract_path, repo_root=repo_root)
    plan = _read_json(_resolve(repo_root, plan_path))
    _validate_plan(plan, contract)
    identity = git_identity(repo_root)
    if identity["dirty_worktree"]:
        raise RuntimeError("Production execution requires a clean Git worktree.")
    if identity["git_sha"] != plan["git_sha"] or identity["branch"] != plan["branch"]:
        raise RuntimeError("Current Git identity differs from the frozen plan.")
    job = _job_from_plan(plan, job_id)
    if host_id != job["host_role"]:
        raise RuntimeError(
            f"Host role mismatch: plan requires {job['host_role']}, got {host_id}."
        )
    for relative, expected in (
        (job["manifest"], job["manifest_sha256"]),
        (job.get("document_list"), job.get("document_list_sha256")),
    ):
        if relative is not None and _sha256(_resolve(repo_root, relative)) != expected:
            raise RuntimeError(f"Job input hash mismatch: {relative}")
    if job.get("execution_bundle_plan") is not None:
        bundle = _bundle_plan_details(
            repo_root,
            job,
            contract["workloads"][job["workload_id"]],
            contract["scientific_config"],
        )
        if (
            bundle["plan_sha256"] != job["execution_bundle_plan_sha256"]
            or bundle["materialization_sha256"]
            != job["execution_bundle_materialization_sha256"]
        ):
            raise RuntimeError("Job execution bundle materialization differs.")
    run_dir = _resolve(repo_root, job["run_dir"])
    manifest_path = _manifest_path(repo_root, job)
    if resume and not run_dir.is_dir():
        raise RuntimeError("--resume requires an existing run directory.")
    if not resume and run_dir.exists():
        raise FileExistsError(f"Initial run directory already exists: {run_dir}")
    if resume and not manifest_path.is_file():
        raise RuntimeError("--resume requires an existing production run manifest.")
    if not resume and manifest_path.exists():
        raise FileExistsError(
            "Initial execution cannot reuse an existing production run manifest; "
            "use the explicit resume path when eligible."
        )
    if manifest_path.exists():
        manifest = _read_json(manifest_path)
        if manifest.get("result_status") == "PASS":
            raise RuntimeError("Completed jobs cannot be rerun or resumed.")
        expected_manifest = {
            "schema_version": RUN_SCHEMA,
            "plan_sha256": plan["plan_sha256"],
            "git_sha": plan["git_sha"],
            "branch": plan["branch"],
            "dirty_worktree": False,
            "cell_id": job["cell_id"],
            "workload_id": job["workload_id"],
            "corpus_freeze_id": contract["corpus"]["freeze_id"],
            "input_manifest_sha256": job["manifest_sha256"],
            "representation_manifest_sha256": job["manifest_sha256"],
            "grammar_sha256": contract["grammar"]["sha256"],
            "production_contract_sha256": plan["production_contract_sha256"],
            "workers": job["workers"],
            "run_id": job["run_id"],
            "metrics_id": job["metrics_id"],
            "host_id": host_id,
            "execution_bundle_plan": job.get("execution_bundle_plan"),
            "execution_bundle_plan_sha256": job.get(
                "execution_bundle_plan_sha256"
            ),
            "execution_bundle_materialization_sha256": job.get(
                "execution_bundle_materialization_sha256"
            ),
        }
        for name, value in expected_manifest.items():
            if manifest.get(name) != value:
                raise RuntimeError(f"Existing run manifest has invalid {name}.")
    else:
        manifest = {
            "schema_version": RUN_SCHEMA,
            "plan_sha256": plan["plan_sha256"],
            "git_sha": plan["git_sha"],
            "branch": plan["branch"],
            "dirty_worktree": False,
            "cell_id": job["cell_id"],
            "workload_id": job["workload_id"],
            "corpus_freeze_id": contract["corpus"]["freeze_id"],
            "input_manifest_sha256": job["manifest_sha256"],
            "representation_manifest_sha256": job["manifest_sha256"],
            "grammar_sha256": contract["grammar"]["sha256"],
            "production_contract_sha256": plan["production_contract_sha256"],
            "scientific_config": copy.deepcopy(contract["scientific_config"]),
            "engineering_config": {
                **copy.deepcopy(contract["engineering_config"]),
                "workers": job["workers"],
            },
            "workers": job["workers"],
            "run_id": job["run_id"],
            "metrics_id": job["metrics_id"],
            "host_id": host_id,
            "execution_bundle_plan": job.get("execution_bundle_plan"),
            "execution_bundle_plan_sha256": job.get(
                "execution_bundle_plan_sha256"
            ),
            "execution_bundle_materialization_sha256": job.get(
                "execution_bundle_materialization_sha256"
            ),
            "runtime_versions": runtime_versions(),
            "start_time": _utc_now(),
            "end_time": None,
            "resume_history": [],
            "result_status": "RUNNING",
            "final_audit": None,
        }
    attempt_number = len(manifest["resume_history"]) + 1
    metrics_dir = Path(job["control_dir"]) / f"attempt_{attempt_number:03d}"
    metrics_path = _resolve(repo_root, metrics_dir)
    if metrics_path.exists():
        raise FileExistsError(f"Metrics attempt already exists: {metrics_path}")
    training = _training_command(job, resume=resume)
    wrapper = [
        "python",
        "scripts/cloud/run_with_metrics.py",
        "--output-dir",
        metrics_dir.as_posix(),
        "--watch-dir",
        job["run_dir"],
        "--",
        *training,
    ]
    attempt = {
        "attempt": attempt_number,
        "resume": resume,
        "started_at": _utc_now(),
        "ended_at": None,
        "metrics_dir": metrics_dir.as_posix(),
        "command": wrapper,
        "return_code": None,
    }
    manifest["resume_history"].append(attempt)
    manifest["result_status"] = "RUNNING"
    _write_json(manifest_path, manifest, overwrite=manifest_path.exists())
    result = subprocess.run(wrapper, cwd=repo_root, check=False)
    attempt["ended_at"] = _utc_now()
    attempt["return_code"] = result.returncode
    manifest["end_time"] = attempt["ended_at"]
    manifest["result_status"] = "FAILED" if result.returncode else "AUDITING"
    _write_json(manifest_path, manifest, overwrite=True)
    if run_dir.is_dir():
        _write_json(
            run_dir / "production_run_manifest.json",
            manifest,
            overwrite=(run_dir / "production_run_manifest.json").exists(),
        )
    if result.returncode:
        return result.returncode
    for name in ("process_tree_summary.json", "process_tree_samples.csv"):
        shutil.copy2(metrics_path / name, manifest_path.parent / name)
    artifact_audit = _audit_artifacts(
        job,
        contract,
        repo_root=repo_root,
        metrics_summary=metrics_path / "process_tree_summary.json",
    )
    manifest["final_audit"] = artifact_audit
    manifest["result_status"] = "PASS" if artifact_audit["valid"] else "AUDIT_FAILED"
    _write_json(manifest_path, manifest, overwrite=True)
    _write_json(
        manifest_path.parent / "audit.json",
        artifact_audit,
        overwrite=(manifest_path.parent / "audit.json").exists(),
    )
    _write_json(
        run_dir / "audit.json",
        artifact_audit,
        overwrite=(run_dir / "audit.json").exists(),
    )
    _write_json(
        run_dir / "production_run_manifest.json",
        manifest,
        overwrite=True,
    )
    return 0 if artifact_audit["valid"] else 2


def _resource_row(audit: dict[str, Any], workers: int) -> dict[str, Any]:
    metrics = audit.get("artifact_audit", {}).get("metrics") or {}
    runtime_path = Path(audit.get("artifact_audit", {}).get("run_dir", "")) / "timing_metrics.json"
    runtime = _read_json(runtime_path) if runtime_path.is_file() else {}
    timings = runtime.get("timings_seconds", {})
    stall = float(timings.get("training_reducer_stall", 0.0)) + float(
        timings.get("inspection_reducer_stall", 0.0)
    )
    gauges = runtime.get("gauges", {})
    histograms = runtime.get("histograms", {})
    completion = audit.get("artifact_audit", {}).get("completion", {})
    return {
        "workers": workers,
        "wall_seconds": metrics.get("wall_seconds"),
        "peak_process_tree_rss_bytes": metrics.get("peak_process_tree_rss_bytes"),
        "peak_watched_run_bytes": metrics.get("peak_watched_run_bytes"),
        "sampled_process_tree_cpu_seconds": metrics.get("sampled_process_tree_cpu_seconds"),
        "sampled_process_tree_read_bytes": metrics.get("sampled_process_tree_read_bytes"),
        "sampled_process_tree_write_bytes": metrics.get("sampled_process_tree_write_bytes"),
        "canonical_reducer_stall_seconds": stall,
        "bundle_true_inflight": gauges.get("training_bundle_true_inflight"),
        "bundle_ready_shard": histograms.get(
            "training_bundle_ready_shards", {}
        ).get("max"),
        "completed_passes": completion.get("completed_passes"),
        "candidate_overflow": completion.get("overflowed_tokens"),
        "host_memory_bytes": metrics.get("host_memory_bytes"),
        "filesystem_free_bytes_end": metrics.get("filesystem_free_bytes_end"),
    }


def job_status(
    plan: dict[str, Any], job: dict[str, Any], contract: dict[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    """Read compact live/completed engineering state without mutating a run."""

    _validate_plan(plan, contract)
    run_dir = _resolve(repo_root, job["run_dir"])
    control_dir = _resolve(repo_root, job["control_dir"])
    checkpoint = (
        _read_json(run_dir / "checkpoint.json")
        if (run_dir / "checkpoint.json").is_file()
        else {}
    )
    manifest = (
        _read_json(control_dir / "run_manifest.json")
        if (control_dir / "run_manifest.json").is_file()
        else {}
    )
    sample: dict[str, Any] = {}
    attempts = manifest.get("resume_history", [])
    samples_path = (
        _resolve(repo_root, attempts[-1]["metrics_dir"]) / "process_tree_samples.csv"
        if attempts
        else control_dir / "process_tree_samples.csv"
    )
    if samples_path.is_file():
        with samples_path.open(encoding="utf-8", newline="") as handle:
            for sample in csv.DictReader(handle):
                pass
    runtime = (
        _read_json(run_dir / "timing_metrics.json")
        if (run_dir / "timing_metrics.json").is_file()
        else {}
    )
    gauges = runtime.get("gauges", {})
    histograms = runtime.get("histograms", {})
    timings = runtime.get("timings_seconds", {})
    reducer_stall = None
    if timings:
        reducer_stall = float(timings.get("training_reducer_stall", 0.0)) + float(
            timings.get("inspection_reducer_stall", 0.0)
        )
    return {
        "host": job["host_role"],
        "workers": job["workers"],
        "workload": job["workload_id"],
        "result_status": manifest.get("result_status", "NOT_STARTED"),
        "completed_passes": checkpoint.get("completed_passes", 0),
        "next_document_index": checkpoint.get("next_document_index", 0),
        "elapsed_seconds": (
            None if not sample.get("wall_seconds") else float(sample["wall_seconds"])
        ),
        "peak_rss_bytes": (
            None if not sample.get("peak_rss_bytes") else int(float(sample["peak_rss_bytes"]))
        ),
        "bundle_inflight": gauges.get("training_bundle_true_inflight"),
        "bundle_ready": histograms.get("training_bundle_ready_shards", {}).get("max"),
        "reducer_stall_seconds": reducer_stall,
    }


def build_round1_attestation(
    plan: dict[str, Any],
    job: dict[str, Any],
    contract: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    """Run the formal audit and reduce it to the Round 1 winner inputs."""

    _validate_plan(plan, contract)
    if plan.get("plan_type") != "round1" or job not in plan.get("jobs", []):
        raise ValueError("Round 1 attestation requires a job from the exact plan.")
    audit = audit_job(plan, job, contract, repo_root=repo_root)
    resources = _resource_row(audit, int(job["workers"]))
    return {
        "schema_version": ROUND1_ATTESTATION_SCHEMA,
        "job_id": job["job_id"],
        "host_role": job["host_role"],
        "workers": job["workers"],
        "valid": audit.get("valid") is True,
        "failures": list(audit.get("failures", [])),
        **resources,
        "git_sha": plan["git_sha"],
        "plan_identity": {
            "schema_version": plan["schema_version"],
            "plan_type": plan["plan_type"],
            "plan_sha256": plan["plan_sha256"],
            "git_sha": plan["git_sha"],
            "branch": plan["branch"],
        },
        "production_contract_identity": {
            "path": plan["contract_path"],
            "sha256": plan["production_contract_sha256"],
        },
    }


def round1_attestation_filename(job_id: str) -> str:
    return f"{job_id}.round1-attestation.json"


def select_round1_winner(
    rows: Iterable[dict[str, Any]], winner_rule: dict[str, Any]
) -> tuple[int, str, list[dict[str, Any]]]:
    ranking = sorted(rows, key=lambda row: (float(row["wall_seconds"]), row["workers"]))
    if len(ranking) != 6:
        raise RuntimeError("Round 1 winner selection requires six eligible jobs.")
    fastest = ranking[0]
    runner_up = ranking[1]
    advantage = (
        float(runner_up["wall_seconds"]) - float(fastest["wall_seconds"])
    ) / float(runner_up["wall_seconds"])
    minimum = float(winner_rule["minimum_direct_wall_advantage_fraction"])
    if advantage >= minimum:
        return int(fastest["workers"]), "direct_wall_winner", ranking
    practical = float(winner_rule["practical_tie_wall_fraction"])
    tied = [
        row
        for row in ranking
        if float(row["wall_seconds"]) <= float(fastest["wall_seconds"]) / (1.0 - practical)
    ]

    def tie_key(row: dict[str, Any]) -> tuple[float, ...]:
        values: list[float] = []
        for name in winner_rule["tie_break_order"]:
            value = row.get(name)
            values.append(float("inf") if value is None else float(value))
        return tuple(values)

    selected = min(tied, key=tie_key)
    return int(selected["workers"]), "practical_tie_resource_rule", ranking


def aggregate_round1_attestations(
    plan: dict[str, Any],
    contract: dict[str, Any],
    attestations: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Validate six compact remote attestations and select the local winner."""

    _validate_plan(plan, contract)
    if plan.get("plan_type") != "round1" or len(plan.get("jobs", [])) != 6:
        raise ValueError("Round 1 aggregation requires the exact six-job plan.")
    supplied = list(attestations)
    by_job = {str(item.get("job_id")): item for item in supplied}
    if len(supplied) != 6 or len(by_job) != 6:
        raise ValueError("Round 1 aggregation requires six unique attestations.")
    rows: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    resource_fields = (
        "wall_seconds",
        "peak_process_tree_rss_bytes",
        "peak_watched_run_bytes",
        "sampled_process_tree_cpu_seconds",
        "canonical_reducer_stall_seconds",
        "host_memory_bytes",
        "filesystem_free_bytes_end",
    )
    for job in plan["jobs"]:
        attestation = by_job.get(job["job_id"])
        if attestation is None:
            raise ValueError(f"Missing Round 1 attestation: {job['job_id']}")
        failures = list(attestation.get("failures", []))
        expected = {
            "schema_version": ROUND1_ATTESTATION_SCHEMA,
            "job_id": job["job_id"],
            "host_role": job["host_role"],
            "workers": job["workers"],
            "git_sha": plan["git_sha"],
            "plan_identity": {
                "schema_version": plan["schema_version"],
                "plan_type": plan["plan_type"],
                "plan_sha256": plan["plan_sha256"],
                "git_sha": plan["git_sha"],
                "branch": plan["branch"],
            },
            "production_contract_identity": {
                "path": plan["contract_path"],
                "sha256": plan["production_contract_sha256"],
            },
        }
        for name, value in expected.items():
            if attestation.get(name) != value:
                failures.append(f"attestation {name} differs")
        if attestation.get("valid") is not True:
            failures.append("formal remote audit did not pass")
        missing = [name for name in resource_fields if attestation.get(name) is None]
        if missing:
            failures.append(f"attestation resource fields are missing: {missing}")
        row = {
            "job_id": job["job_id"],
            "host_role": job["host_role"],
            "workers": job["workers"],
            "valid": not failures,
            "failures": failures,
            **{name: attestation.get(name) for name in resource_fields},
        }
        memory = row["peak_process_tree_rss_bytes"]
        host_memory = row["host_memory_bytes"]
        storage = row["peak_watched_run_bytes"]
        free_end = row["filesystem_free_bytes_end"]
        if memory is not None and host_memory is not None and (
            memory > host_memory * contract["gates"]["memory_max_host_fraction"]
        ):
            row["valid"] = False
            row["failures"].append("memory safety gate failed")
        if storage is not None and storage > contract["gates"]["storage_max_bytes"]:
            row["valid"] = False
            row["failures"].append("storage safety gate failed")
        if free_end is not None and free_end < contract["gates"]["storage_min_free_bytes_end"]:
            row["valid"] = False
            row["failures"].append("filesystem free-space safety gate failed")
        if row["valid"]:
            eligible.append(row)
        rows.append(row)
    result = {
        "schema_version": ROUND1_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "production_contract_sha256": plan["production_contract_sha256"],
        "ROUND1_STATUS": "FAIL",
        "WORKER_RANKING": [],
        "WINNER_WORKERS": None,
        "WINNER_REASON": None,
        "jobs": rows,
    }
    if len(eligible) == 6:
        winner, reason, ranking = select_round1_winner(
            eligible, contract["round1"]["winner_rule"]
        )
        result.update(
            {
                "ROUND1_STATUS": "PASS",
                "WORKER_RANKING": ranking,
                "WINNER_WORKERS": winner,
                "WINNER_REASON": reason,
            }
        )
    return result


def aggregate_round1(
    plan: dict[str, Any], contract: dict[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    _validate_plan(plan, contract)
    if plan["plan_type"] != "round1" or len(plan["jobs"]) != 6:
        raise ValueError("Round 1 aggregation requires the exact six-job plan.")
    attestations = [
        build_round1_attestation(
            plan, job, contract, repo_root=repo_root
        )
        for job in plan["jobs"]
    ]
    return aggregate_round1_attestations(plan, contract, attestations)


def round2_attestation_filename(job_id: str) -> str:
    return f"{job_id}.round2-attestation.json"


def build_round2_attestation(
    plan: dict[str, Any],
    job: dict[str, Any],
    contract: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    """Reduce one formal job audit to worker-selection engineering evidence."""

    _validate_plan(plan, contract)
    if plan.get("plan_type") != "round2" or job not in plan.get("jobs", []):
        raise ValueError("Round 2 attestation requires a job from the exact plan.")
    audit = audit_job(plan, job, contract, repo_root=repo_root)
    resources = _resource_row(audit, int(job["workers"]))
    return {
        "schema_version": ROUND2_ATTESTATION_SCHEMA,
        "job_id": job["job_id"],
        "host_role": job["host_role"],
        "workload": job["workload_id"],
        "workers": job["workers"],
        "valid": audit.get("valid") is True,
        "failures": list(audit.get("failures", [])),
        **resources,
        "git_sha": plan["git_sha"],
        "execution_bundle_plan": job["execution_bundle_plan"],
        "execution_bundle_plan_sha256": job["execution_bundle_plan_sha256"],
        "execution_bundle_materialization_sha256": job[
            "execution_bundle_materialization_sha256"
        ],
        "plan_identity": {
            "schema_version": plan["schema_version"],
            "plan_type": plan["plan_type"],
            "plan_sha256": plan["plan_sha256"],
            "git_sha": plan["git_sha"],
            "branch": plan["branch"],
        },
        "production_contract_identity": {
            "path": plan["contract_path"],
            "sha256": plan["production_contract_sha256"],
        },
    }


def _round2_workload_preference(
    rows: list[dict[str, Any]], practical_fraction: float
) -> tuple[int, str, list[dict[str, Any]]]:
    ranking = sorted(
        rows, key=lambda row: (float(row["wall_seconds"]), int(row["workers"]))
    )
    if not ranking:
        raise RuntimeError("Round 2 workload selection has no eligible candidates.")
    fastest = ranking[0]
    tied = [
        row
        for row in ranking
        if float(row["wall_seconds"])
        <= float(fastest["wall_seconds"]) / (1.0 - practical_fraction)
    ]
    if len(tied) == 1:
        return int(fastest["workers"]), "direct_wall_winner", ranking
    selected = min(
        tied,
        key=lambda row: (
            float(row["peak_process_tree_rss_bytes"]),
            float(row["canonical_reducer_stall_seconds"]),
            int(row["workers"]),
        ),
    )
    return int(selected["workers"]), "practical_tie_resource_rule", ranking


def aggregate_round2_attestations(
    plan: dict[str, Any],
    contract: dict[str, Any],
    attestations: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Select workers from representative/stress evidence or request w20."""

    _validate_plan(plan, contract)
    supplied = list(attestations)
    by_job = {str(item.get("job_id")): item for item in supplied}
    if plan.get("plan_type") != "round2" or len(supplied) != 6 or len(by_job) != 6:
        raise ValueError("Round 2 aggregation requires six unique attestations.")
    resource_fields = (
        "wall_seconds",
        "peak_process_tree_rss_bytes",
        "peak_watched_run_bytes",
        "sampled_process_tree_cpu_seconds",
        "canonical_reducer_stall_seconds",
        "bundle_true_inflight",
        "bundle_ready_shard",
        "completed_passes",
        "candidate_overflow",
        "host_memory_bytes",
        "filesystem_free_bytes_end",
    )
    rows: list[dict[str, Any]] = []
    for job in plan["jobs"]:
        item = by_job.get(job["job_id"])
        if item is None:
            raise ValueError(f"Missing Round 2 attestation: {job['job_id']}")
        failures = list(item.get("failures", []))
        expected = {
            "schema_version": ROUND2_ATTESTATION_SCHEMA,
            "job_id": job["job_id"],
            "host_role": job["host_role"],
            "workload": job["workload_id"],
            "workers": job["workers"],
            "git_sha": plan["git_sha"],
            "execution_bundle_plan": job["execution_bundle_plan"],
            "execution_bundle_plan_sha256": job["execution_bundle_plan_sha256"],
            "execution_bundle_materialization_sha256": job[
                "execution_bundle_materialization_sha256"
            ],
            "plan_identity": {
                "schema_version": plan["schema_version"],
                "plan_type": plan["plan_type"],
                "plan_sha256": plan["plan_sha256"],
                "git_sha": plan["git_sha"],
                "branch": plan["branch"],
            },
            "production_contract_identity": {
                "path": plan["contract_path"],
                "sha256": plan["production_contract_sha256"],
            },
        }
        for name, value in expected.items():
            if item.get(name) != value:
                failures.append(f"attestation {name} differs")
        if item.get("valid") is not True:
            failures.append("formal remote audit did not pass")
        missing = [name for name in resource_fields if item.get(name) is None]
        if missing:
            failures.append(f"attestation engineering fields are missing: {missing}")
        row = {
            "job_id": job["job_id"],
            "host_role": job["host_role"],
            "workload": job["workload_id"],
            "workers": job["workers"],
            **{name: item.get(name) for name in resource_fields},
            "failures": failures,
        }
        if not failures:
            if row["completed_passes"] != contract["passes"]:
                failures.append("completed-pass gate failed")
            if row["candidate_overflow"] != 0:
                failures.append("candidate-overflow gate failed")
            if row["peak_process_tree_rss_bytes"] > (
                row["host_memory_bytes"] * contract["gates"]["memory_max_host_fraction"]
            ):
                failures.append("memory safety gate failed")
            if (
                row["peak_watched_run_bytes"] > contract["gates"]["storage_max_bytes"]
                or row["filesystem_free_bytes_end"]
                < contract["gates"]["storage_min_free_bytes_end"]
            ):
                failures.append("storage safety gate failed")
        row["valid"] = not failures
        rows.append(row)

    candidate_rows = []
    for workers in ROUND2_PRIMARY_WORKERS:
        evidence = {
            row["workload"]: row
            for row in rows
            if int(row["workers"]) == workers
        }
        eligible = (
            set(evidence) == {"representative", "stress"}
            and all(row["valid"] for row in evidence.values())
        )
        candidate_rows.append(
            {
                "workers": workers,
                "eligible": eligible,
                "representative": evidence.get("representative"),
                "stress": evidence.get("stress"),
            }
        )
    eligible = [row for row in candidate_rows if row["eligible"]]
    result = {
        "schema_version": ROUND2_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "production_contract_sha256": plan["production_contract_sha256"],
        "ROUND2_STATUS": "FAIL",
        "WINNER_WORKERS": None,
        "WINNER_REASON": None,
        "W20_REQUIRED": "no",
        "candidate_ranking": candidate_rows,
        "jobs": rows,
    }
    if not eligible:
        result["WINNER_REASON"] = "no_worker_passed_both_workloads"
        return result
    practical = float(contract["round2"]["practical_tie_wall_fraction"])
    selections = {}
    for workload in ("representative", "stress"):
        selected, reason, ranking = _round2_workload_preference(
            [row[workload] for row in eligible], practical
        )
        selections[workload] = {
            "workers": selected,
            "reason": reason,
            "ranking": ranking,
        }
    result["workload_selections"] = selections
    selected_workers = {row["workers"] for row in selections.values()}
    if len(selected_workers) != 1:
        result.update(
            {
                "ROUND2_STATUS": "FAIL",
                "WINNER_REASON": "representative_and_stress_prefer_different_workers",
                "W20_REQUIRED": "no",
            }
        )
        return result
    winner = int(next(iter(selected_workers)))
    result.update(
        {
            "ROUND2_STATUS": "PASS",
            "WINNER_WORKERS": winner,
            "WINNER_REASON": (
                "representative_and_stress_agree_under_10pct_practical_tie_rule"
            ),
        }
    )
    return result


def aggregate_round2(
    plan: dict[str, Any], contract: dict[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    attestations = [
        build_round2_attestation(plan, job, contract, repo_root=repo_root)
        for job in plan["jobs"]
    ]
    return aggregate_round2_attestations(plan, contract, attestations)


def _script_neutral_bounded_gate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    by_cell = {row["cell_id"]: row for row in rows}
    pairs = (
        (
            "surface_word",
            "s1m2_m0_iast_surface_word",
            "s1m2_m0_devanagari_surface_word",
        ),
        (
            "legacy_joined",
            "s1m2_m0_iast_legacy_joined",
            "s1m2_m0_devanagari_legacy_joined",
        ),
        (
            "continuous",
            "s1m2_m0_prime_iast_continuous",
            "s1m2_m0_devanagari_continuous",
        ),
    )
    comparisons = []
    for condition, iast_id, devanagari_id in pairs:
        left = by_cell.get(iast_id, {})
        right = by_cell.get(devanagari_id, {})
        artifacts = {}
        for name in SCRIPT_NEUTRAL_ARTIFACTS:
            left_identity = left.get("scientific_artifacts", {}).get(name)
            right_identity = right.get("scientific_artifacts", {}).get(name)
            artifacts[name] = {
                "equal": left_identity is not None and left_identity == right_identity,
                "iast": left_identity,
                "devanagari": right_identity,
            }
        comparisons.append(
            {
                "condition": condition,
                "iast_cell_id": iast_id,
                "devanagari_cell_id": devanagari_id,
                "artifacts": artifacts,
                "valid": all(item["equal"] for item in artifacts.values()),
            }
        )
    return {
        "status": "PASS" if all(row["valid"] for row in comparisons) else "FAIL",
        "scope": (
            "bounded_same-canonical-content dispatcher/frontend check; "
            "not a representative scientific result"
        ),
        "compared_artifacts": list(SCRIPT_NEUTRAL_ARTIFACTS),
        "comparisons": comparisons,
    }


def run_bounded_validation(
    contract: dict[str, Any],
    *,
    contract_path: Path,
    output_root: Path,
    repo_root: Path,
) -> dict[str, Any]:
    identity = git_identity(repo_root)
    plan = build_bounded_plan(
        contract,
        contract_path=contract_path,
        output_root=output_root / "runs",
        metrics_root=output_root / "metrics",
        identity={**identity, "dirty_worktree": False},
    )
    if output_root.exists():
        raise FileExistsError(f"Refusing to overwrite bounded validation: {output_root}")
    rows = []
    for job in plan["jobs"]:
        result = run_training(
            _config_for_job(job, resume=False), repo_root=repo_root
        )
        audit = _audit_artifacts(
            job, contract, repo_root=repo_root, metrics_summary=None
        )
        rows.append(
            {
                "cell_id": job["cell_id"],
                "run_dir": result.run_dir.as_posix(),
                "valid": audit["valid"],
                "failures": audit["failures"],
                "scientific_artifacts": audit.get("scientific_artifacts", {}),
            }
        )
    script_neutral_gate = _script_neutral_bounded_gate(rows)
    payload = {
        "schema_version": BOUND_VALIDATION_SCHEMA,
        "git_sha": identity["git_sha"],
        "branch": identity["branch"],
        "dirty_worktree_at_start": identity["dirty_worktree"],
        "production_contract_sha256": _canonical_sha256(contract),
        "cell_count": len(rows),
        "status": (
            "PASS"
            if len(rows) == 6
            and all(row["valid"] for row in rows)
            and script_neutral_gate["status"] == "PASS"
            else "FAIL"
        ),
        "classification": "BOUNDED_INTERFACE_NOT_SCIENTIFIC_OR_REPRESENTATIVE",
        "script_neutral_production_path": script_neutral_gate,
        "cells": rows,
    }
    _write_json(output_root / "bounded_validation.json", payload)
    return payload


def _write_plan_commands(plan: dict[str, Any], plan_path: Path) -> None:
    for job in plan["jobs"]:
        job["launch_command"] = [
            "python", "-m", "sktlm.production.s1m2", "run",
            "--plan", plan_path.as_posix(), "--job-id", job["job_id"],
            "--host-id", job["host_role"],
        ]
        job["launch_command_shell"] = shlex.join(job["launch_command"])
        job["resume_command"] = [*job["launch_command"], "--resume"]
        job["resume_command_shell"] = shlex.join(job["resume_command"])
        job["audit_command"] = [
            "python", "-m", "sktlm.production.s1m2", "audit",
            "--plan", plan_path.as_posix(), "--job-id", job["job_id"],
        ]
        job["audit_command_shell"] = shlex.join(job["audit_command"])
    plan["plan_sha256"] = _canonical_sha256(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="S1M2 production control plane")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate-contract")
    for name in ("plan-round1", "plan-bounded"):
        item = commands.add_parser(name)
        item.add_argument("--output", required=True, type=Path)
        item.add_argument("--output-root", type=Path)
        item.add_argument("--metrics-root", type=Path)
    item = commands.add_parser("aggregate-round1")
    item.add_argument("--plan", required=True, type=Path)
    item.add_argument("--output", required=True, type=Path)
    item.add_argument("--attestation-dir", type=Path)
    item = commands.add_parser("attest-round1")
    item.add_argument("--plan", required=True, type=Path)
    item.add_argument("--job-id", required=True)
    item.add_argument("--output", required=True, type=Path)
    item = commands.add_parser("plan-round2")
    item.add_argument("--output", required=True, type=Path)
    item = commands.add_parser("aggregate-round2")
    item.add_argument("--plan", required=True, type=Path)
    item.add_argument("--output", required=True, type=Path)
    item.add_argument("--attestation-dir", type=Path)
    item = commands.add_parser("attest-round2")
    item.add_argument("--plan", required=True, type=Path)
    item.add_argument("--job-id", required=True)
    item.add_argument("--output", required=True, type=Path)
    item = commands.add_parser("build-round3-closure")
    item.add_argument("--round2-result", required=True, type=Path)
    item.add_argument("--output", required=True, type=Path)
    item = commands.add_parser("validate-round3-closure")
    item.add_argument("--round2-result", required=True, type=Path)
    item.add_argument("--closure", required=True, type=Path)
    item = commands.add_parser("plan-final")
    item.add_argument("--round2-result", required=True, type=Path)
    item.add_argument("--round3-closure", required=True, type=Path)
    item.add_argument("--output", required=True, type=Path)
    item = commands.add_parser("run")
    item.add_argument("--plan", required=True, type=Path)
    item.add_argument("--job-id", required=True)
    item.add_argument("--host-id", default=socket.gethostname())
    item.add_argument("--resume", action="store_true")
    item = commands.add_parser("audit")
    item.add_argument("--plan", required=True, type=Path)
    item.add_argument("--job-id", required=True)
    item.add_argument("--output", type=Path)
    item = commands.add_parser("status-job")
    item.add_argument("--plan", required=True, type=Path)
    item.add_argument("--job-id", required=True)
    item = commands.add_parser("validate-bounded")
    item.add_argument("--output-root", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    contract = load_contract(args.contract, repo_root=repo_root)
    if args.command == "validate-contract":
        print(json.dumps({"status": "PASS", "contract_sha256": _canonical_sha256(contract)}, indent=2))
        return
    output_payload: dict[str, Any]
    if args.command == "run":
        raise SystemExit(
            run_job(
                plan_path=args.plan,
                job_id=args.job_id,
                contract_path=args.contract,
                repo_root=repo_root,
                host_id=args.host_id,
                resume=args.resume,
            )
        )
    if args.command == "validate-bounded":
        result = run_bounded_validation(
            contract,
            contract_path=args.contract,
            output_root=_resolve(repo_root, args.output_root),
            repo_root=repo_root,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(0 if result["status"] == "PASS" else 1)
    if args.command == "audit":
        plan = _read_json(_resolve(repo_root, args.plan))
        _validate_plan(plan, contract)
        result = audit_job(
            plan,
            _job_from_plan(plan, args.job_id),
            contract,
            repo_root=repo_root,
        )
        if args.output:
            _write_json(_resolve(repo_root, args.output), result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(0 if result["valid"] else 1)
    if args.command == "status-job":
        plan = _read_json(_resolve(repo_root, args.plan))
        result = job_status(
            plan,
            _job_from_plan(plan, args.job_id),
            contract,
            repo_root=repo_root,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return
    if args.command == "validate-round3-closure":
        round2 = _read_json(_resolve(repo_root, args.round2_result))
        closure = _read_json(_resolve(repo_root, args.closure))
        validate_round3_closure(
            closure, contract, round2, repo_root=repo_root
        )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "closure_sha256": closure["closure_sha256"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    if args.command == "attest-round1":
        plan = _read_json(_resolve(repo_root, args.plan))
        _validate_plan(plan, contract)
        result = build_round1_attestation(
            plan,
            _job_from_plan(plan, args.job_id),
            contract,
            repo_root=repo_root,
        )
        _write_json(_resolve(repo_root, args.output), result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(0 if result["valid"] else 2)
    if args.command == "attest-round2":
        plan = _read_json(_resolve(repo_root, args.plan))
        _validate_plan(plan, contract)
        result = build_round2_attestation(
            plan,
            _job_from_plan(plan, args.job_id),
            contract,
            repo_root=repo_root,
        )
        _write_json(_resolve(repo_root, args.output), result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(0 if result["valid"] else 2)
    identity = git_identity(repo_root)
    if args.command == "plan-round1":
        output = args.output
        plan = build_round1_plan(
            contract,
            contract_path=args.contract,
            output_root=args.output_root or Path("artifacts/latent_benchmarks"),
            metrics_root=args.metrics_root or Path("artifacts/cloud_metrics"),
            identity=identity,
        )
        _write_plan_commands(plan, output)
        _write_json(_resolve(repo_root, output), plan)
        output_payload = plan
    elif args.command == "plan-bounded":
        output = args.output
        plan = build_bounded_plan(
            contract,
            contract_path=args.contract,
            output_root=args.output_root or Path("artifacts/s1m2_prevm_validation/runs"),
            metrics_root=args.metrics_root or Path("artifacts/s1m2_prevm_validation/metrics"),
            identity=identity,
        )
        _write_plan_commands(plan, output)
        _write_json(_resolve(repo_root, output), plan)
        output_payload = plan
    elif args.command == "aggregate-round1":
        plan = _read_json(_resolve(repo_root, args.plan))
        if args.attestation_dir is None:
            result = aggregate_round1(plan, contract, repo_root=repo_root)
        else:
            directory = _resolve(repo_root, args.attestation_dir)
            attestations = [
                _read_json(directory / round1_attestation_filename(job["job_id"]))
                for job in plan["jobs"]
            ]
            result = aggregate_round1_attestations(plan, contract, attestations)
        _write_json(_resolve(repo_root, args.output), result)
        output_payload = result
    elif args.command == "plan-round2":
        output = args.output
        plan = build_round2_plan(
            contract,
            contract_path=args.contract,
            repo_root=repo_root,
            identity=identity,
        )
        _write_plan_commands(plan, output)
        _write_json(_resolve(repo_root, output), plan)
        output_payload = plan
    elif args.command == "aggregate-round2":
        plan = _read_json(_resolve(repo_root, args.plan))
        if args.attestation_dir is None:
            result = aggregate_round2(plan, contract, repo_root=repo_root)
        else:
            directory = _resolve(repo_root, args.attestation_dir)
            attestations = [
                _read_json(directory / round2_attestation_filename(job["job_id"]))
                for job in plan["jobs"]
            ]
            result = aggregate_round2_attestations(plan, contract, attestations)
        _write_json(_resolve(repo_root, args.output), result)
        output_payload = result
    elif args.command == "build-round3-closure":
        output = args.output
        closure = build_round3_closure(
            contract,
            args.round2_result,
            repo_root=repo_root,
        )
        _write_json(_resolve(repo_root, output), closure)
        output_payload = closure
    elif args.command == "plan-final":
        output = args.output
        result = _read_json(_resolve(repo_root, args.round2_result))
        closure = _read_json(_resolve(repo_root, args.round3_closure))
        plan = build_final_plan(
            contract,
            result,
            closure,
            contract_path=args.contract,
            identity=identity,
            repo_root=repo_root,
        )
        _write_plan_commands(plan, output)
        _validate_plan(plan, contract)
        _write_json(_resolve(repo_root, output), plan)
        output_payload = plan
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(output_payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
