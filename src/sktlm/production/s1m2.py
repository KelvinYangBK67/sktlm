"""S1M2 pre-VM plans, execution manifests, audits, and readiness gates.

This module is an engineering control plane.  It resolves the frozen six-cell
contract into the existing exact trainer and Linux process-tree metrics wrapper;
it contains no candidate, scoring, inference, or update logic.
"""

from __future__ import annotations

import argparse
import copy
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

from sktlm.latent.training import S1M2_MODEL, TrainingConfig, run_training


CONTRACT_PATH = Path("configs/production/s1m2_six_cell.json")
CONTRACT_SCHEMA = "sktlm-s1m2-production-contract/v1"
PLAN_SCHEMA = "sktlm-s1m2-production-plan/v1"
RUN_SCHEMA = "sktlm-s1m2-run-manifest/v1"
ROUND1_SCHEMA = "sktlm-s1m2-round1-result/v1"
ROUND2_SCHEMA = "sktlm-s1m2-round2-result/v1"
BOUND_VALIDATION_SCHEMA = "sktlm-s1m2-bounded-validation/v1"
SCRIPT_NEUTRAL_ARTIFACTS = (
    "piece_inventory.tsv",
    "lexical_diagnostics.tsv",
    "rule_usage.tsv",
)
ROUND1_WORKERS = (4, 8, 12, 16, 20, 24)
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
    if verify_files:
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
) -> dict[str, Any]:
    cell = _cell(contract, cell_id)
    workload = contract["workloads"][workload_id]
    manifest, manifest_hash = _manifest_details(contract, cell)
    short_cell = cell_id.removeprefix("s1m2_")
    worker_suffix = f"_w{workers}" if plan_type == "round1" else ""
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
        "host_role": (
            "local-validation" if plan_type == "bounded" else "s1m2-vm-01"
        ),
        "resolved_config": resolved_config,
        "resume_policy": copy.deepcopy(contract["resume_policy"]),
    }
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
        )
        for workers in settings["workers"]
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
        "only engineering worker count differs."
    )
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


def build_round2_plan(
    contract: dict[str, Any],
    round1: dict[str, Any],
    *,
    contract_path: Path = CONTRACT_PATH,
    output_root: Path = Path("artifacts/latent_benchmarks"),
    metrics_root: Path = Path("artifacts/cloud_metrics"),
    identity: dict[str, Any],
) -> dict[str, Any]:
    if round1.get("schema_version") != ROUND1_SCHEMA:
        raise ValueError("Unsupported Round 1 result schema.")
    if round1.get("ROUND1_STATUS") != "PASS":
        raise RuntimeError("Round 2 cannot be prepared before Round 1 passes.")
    if round1.get("production_contract_sha256") != _canonical_sha256(contract):
        raise ValueError("Round 1 result does not bind the production contract.")
    if len(round1.get("jobs", ())) != 6 or not all(
        row.get("valid") is True for row in round1["jobs"]
    ):
        raise ValueError("Round 1 result does not contain six valid jobs.")
    if len(round1.get("WORKER_RANKING", ())) != 6:
        raise ValueError("Round 1 result does not contain a six-worker ranking.")
    if {
        int(row.get("workers", -1)) for row in round1["jobs"]
    } != set(ROUND1_WORKERS) or {
        int(row.get("workers", -1)) for row in round1["WORKER_RANKING"]
    } != set(ROUND1_WORKERS):
        raise ValueError("Round 1 result worker identities differ from the matrix.")
    if len(str(round1.get("plan_sha256", ""))) != 64:
        raise ValueError("Round 1 result has no valid plan identity.")
    winner = int(round1["WINNER_WORKERS"])
    if winner not in ROUND1_WORKERS:
        raise ValueError("Round 1 winner is not in the frozen worker matrix.")
    jobs = [
        _job(
            contract,
            plan_type="round2",
            cell_id=cell_id,
            workload_id=workload_id,
            workers=winner,
            output_root=output_root,
            metrics_root=metrics_root,
        )
        for cell_id, workload_id in contract["round2"]["jobs"]
    ]
    plan = _base_plan(
        contract,
        contract_path=contract_path,
        plan_type="round2",
        jobs=jobs,
        identity=identity,
    )
    plan["winner_workers_source"] = {
        "round1_result_sha256": _canonical_sha256(round1),
        "workers": winner,
    }
    plan["plan_sha256"] = _canonical_sha256(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )
    return plan


def build_final_plan(
    contract: dict[str, Any],
    round2: dict[str, Any],
    *,
    contract_path: Path = CONTRACT_PATH,
    output_root: Path = Path("artifacts/latent_benchmarks"),
    metrics_root: Path = Path("artifacts/cloud_metrics"),
    identity: dict[str, Any],
) -> dict[str, Any]:
    if round2.get("schema_version") != ROUND2_SCHEMA:
        raise ValueError("Unsupported Round 2 result schema.")
    if round2.get("ROUND2_STATUS") != "PASS":
        raise RuntimeError("Full six-cell launch cannot be prepared before Round 2 passes.")
    if round2.get("production_contract_sha256") != _canonical_sha256(contract):
        raise ValueError("Round 2 result does not bind the production contract.")
    if len(round2.get("jobs", ())) != 6 or not all(
        row.get("valid") is True for row in round2["jobs"]
    ):
        raise ValueError("Round 2 result does not contain six valid jobs.")
    winner = int(round2["WINNER_WORKERS"])
    if winner not in ROUND1_WORKERS:
        raise ValueError("Round 2 winner is not in the frozen worker matrix.")
    required_gates = (
        "CONTINUOUS_RUNTIME_TARGET",
        "PRODUCTION_MEMORY_GATE",
        "PRODUCTION_STORAGE_GATE",
        "PRODUCTION_RESUME_GATE",
        "PRODUCTION_PROVENANCE_GATE",
        "S1M2_SIX_CELL_INTERFACE_GATE",
    )
    if any(round2.get(name) != "PASS" for name in required_gates):
        raise RuntimeError("Full six-cell launch requires every Round 2 gate to pass.")
    if {int(row.get("workers", -1)) for row in round2["jobs"]} != {winner}:
        raise ValueError("Round 2 job workers differ from WINNER_WORKERS.")
    if len(str(round2.get("plan_sha256", ""))) != 64:
        raise ValueError("Round 2 result has no valid plan identity.")
    jobs = [
        _job(
            contract,
            plan_type="full",
            cell_id=cell["cell_id"],
            workload_id="full",
            workers=winner,
            output_root=output_root,
            metrics_root=metrics_root,
        )
        for cell in contract["cells"]
    ]
    for index, job in enumerate(jobs, 1):
        job["host_role"] = f"core-{index:02d}"
    plan = _base_plan(
        contract,
        contract_path=contract_path,
        plan_type="full",
        jobs=jobs,
        identity=identity,
    )
    plan.update(
        {
            "winner_workers_source": {
                "round2_result_sha256": _canonical_sha256(round2),
                "workers": winner,
            },
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
    elif plan_type == "round2":
        if actual_cells != [tuple(item) for item in contract["round2"]["jobs"]]:
            raise ValueError("Round 2 plan differs from the frozen matrix.")
    elif plan_type in {"bounded", "full"}:
        workload_id = "bounded_interface" if plan_type == "bounded" else "full"
        expected_cells = [(cell["cell_id"], workload_id) for cell in contract["cells"]]
        if actual_cells != expected_cells:
            raise ValueError(f"{plan_type} plan differs from the six-cell contract.")
    else:
        raise ValueError(f"Unsupported production plan type: {plan_type}")
    if plan_type != "round1":
        workers = {job.get("workers") for job in jobs}
        if len(workers) != 1 or not workers <= set(ROUND1_WORKERS) | {1}:
            raise ValueError("Production plan has an invalid worker assignment.")
        if plan_type == "bounded" and workers != {1}:
            raise ValueError("Bounded validation must use one worker.")
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
    if storage.get("status") != "COMPACT":
        failures.append("completed S1M2 SQLite state is not compact")
    topology = storage.get("compiled_topology", {})
    if topology.get("mutable_scores_or_posteriors_stored") is not False:
        failures.append("topology archive claims mutable scientific state")
    if not tuple(run_dir.glob(contract["artifact_contract"]["topology_glob"])):
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
    for relative, expected in (
        (job["manifest"], job["manifest_sha256"]),
        (job.get("document_list"), job.get("document_list_sha256")),
    ):
        if relative is not None and _sha256(_resolve(repo_root, relative)) != expected:
            raise RuntimeError(f"Job input hash mismatch: {relative}")
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
    return {
        "workers": workers,
        "wall_seconds": metrics.get("wall_seconds"),
        "peak_process_tree_rss_bytes": metrics.get("peak_process_tree_rss_bytes"),
        "peak_watched_run_bytes": metrics.get("peak_watched_run_bytes"),
        "sampled_process_tree_cpu_seconds": metrics.get("sampled_process_tree_cpu_seconds"),
        "sampled_process_tree_read_bytes": metrics.get("sampled_process_tree_read_bytes"),
        "sampled_process_tree_write_bytes": metrics.get("sampled_process_tree_write_bytes"),
        "canonical_reducer_stall_seconds": stall,
        "host_memory_bytes": metrics.get("host_memory_bytes"),
        "filesystem_free_bytes_end": metrics.get("filesystem_free_bytes_end"),
    }


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


def aggregate_round1(
    plan: dict[str, Any], contract: dict[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    _validate_plan(plan, contract)
    if plan["plan_type"] != "round1" or len(plan["jobs"]) != 6:
        raise ValueError("Round 1 aggregation requires the exact six-job plan.")
    audits = []
    eligible = []
    for job in plan["jobs"]:
        audit = audit_job(plan, job, contract, repo_root=repo_root)
        row = {
            "job_id": job["job_id"],
            "workers": job["workers"],
            "valid": audit["valid"],
            "failures": audit["failures"],
        }
        if audit["valid"]:
            resources = _resource_row(audit, job["workers"])
            row.update(resources)
            memory = resources["peak_process_tree_rss_bytes"]
            host_memory = resources["host_memory_bytes"]
            storage = resources["peak_watched_run_bytes"]
            free_end = resources["filesystem_free_bytes_end"]
            if memory is None or host_memory is None:
                row["valid"] = False
                row["failures"].append("aggregate process-tree/host memory is missing")
            elif memory > host_memory * contract["gates"]["memory_max_host_fraction"]:
                row["valid"] = False
                row["failures"].append("memory safety gate failed")
            if storage is None:
                row["valid"] = False
                row["failures"].append("peak watched storage is missing")
            elif storage > contract["gates"]["storage_max_bytes"]:
                row["valid"] = False
                row["failures"].append("storage safety gate failed")
            if free_end is None:
                row["valid"] = False
                row["failures"].append("filesystem free-space telemetry is missing")
            elif free_end < contract["gates"]["storage_min_free_bytes_end"]:
                row["valid"] = False
                row["failures"].append("filesystem free-space safety gate failed")
        if row["valid"]:
            eligible.append(row)
        audits.append(row)
    result = {
        "schema_version": ROUND1_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "production_contract_sha256": plan["production_contract_sha256"],
        "ROUND1_STATUS": "FAIL",
        "WORKER_RANKING": [],
        "WINNER_WORKERS": None,
        "WINNER_REASON": None,
        "jobs": audits,
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


def evaluate_round2(
    plan: dict[str, Any], contract: dict[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    _validate_plan(plan, contract)
    expected = [tuple(item) for item in contract["round2"]["jobs"]]
    actual = [(job["cell_id"], job["workload_id"]) for job in plan["jobs"]]
    workers = {int(job["workers"]) for job in plan["jobs"]}
    interface_ok = actual == expected and len(workers) == 1
    rows = []
    audit_ok = True
    memory_ok = True
    storage_ok = True
    runtime_ok = True
    provenance_ok = True
    representative_scale = (
        contract["workloads"]["full"]["phonemes"]
        / contract["workloads"]["representative"]["phonemes"]
    )
    projections: dict[str, float] = {}
    for job in plan["jobs"]:
        audit = audit_job(plan, job, contract, repo_root=repo_root)
        audit_ok &= audit["valid"]
        provenance_ok &= audit["valid"] and not any(
            "provenance" in failure or "manifest" in failure
            for failure in audit["failures"]
        )
        row = {"job_id": job["job_id"], "valid": audit["valid"], "failures": audit["failures"]}
        if audit["valid"]:
            resources = _resource_row(audit, job["workers"])
            row.update(resources)
            peak = resources["peak_process_tree_rss_bytes"]
            host = resources["host_memory_bytes"]
            memory_ok &= peak is not None and host is not None and peak <= host * contract["gates"]["memory_max_host_fraction"]
            peak_storage = resources["peak_watched_run_bytes"]
            free_end = resources["filesystem_free_bytes_end"]
            storage_ok &= (
                peak_storage is not None
                and peak_storage <= contract["gates"]["storage_max_bytes"]
                and free_end is not None
                and free_end >= contract["gates"]["storage_min_free_bytes_end"]
            )
            if job["workload_id"] == "representative":
                wall_projection = float(resources["wall_seconds"]) * representative_scale
                storage_projection = float(peak_storage) * representative_scale
                projections[job["cell_id"]] = wall_projection
                runtime_ok &= wall_projection <= contract["gates"]["continuous_runtime_target_seconds_full_projection"]
                storage_ok &= storage_projection <= contract["gates"]["storage_max_bytes"]
                row["full_wall_projection_seconds"] = wall_projection
                row["full_peak_storage_projection_bytes"] = storage_projection
        rows.append(row)
    gates = {
        "CONTINUOUS_RUNTIME_TARGET": "PASS" if runtime_ok and len(projections) == 2 else "FAIL",
        "PRODUCTION_MEMORY_GATE": "PASS" if memory_ok and audit_ok else "FAIL",
        "PRODUCTION_STORAGE_GATE": "PASS" if storage_ok and audit_ok else "FAIL",
        "PRODUCTION_RESUME_GATE": "PASS" if contract["resume_policy"]["mode"] == "explicit_only" and audit_ok else "FAIL",
        "PRODUCTION_PROVENANCE_GATE": "PASS" if provenance_ok and audit_ok else "FAIL",
        "S1M2_SIX_CELL_INTERFACE_GATE": "PASS" if interface_ok and audit_ok else "FAIL",
    }
    status = "PASS" if all(value == "PASS" for value in gates.values()) else "FAIL"
    return {
        "schema_version": ROUND2_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "production_contract_sha256": plan["production_contract_sha256"],
        "WINNER_WORKERS": next(iter(workers)) if len(workers) == 1 else None,
        "full_runtime_projections_seconds": projections,
        **gates,
        "ROUND2_STATUS": status,
        "jobs": rows,
    }


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
    item = commands.add_parser("plan-round2")
    item.add_argument("--round1-result", required=True, type=Path)
    item.add_argument("--output", required=True, type=Path)
    item = commands.add_parser("evaluate-round2")
    item.add_argument("--plan", required=True, type=Path)
    item.add_argument("--output", required=True, type=Path)
    item = commands.add_parser("plan-final")
    item.add_argument("--round2-result", required=True, type=Path)
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
        result = aggregate_round1(plan, contract, repo_root=repo_root)
        _write_json(_resolve(repo_root, args.output), result)
        output_payload = result
    elif args.command == "plan-round2":
        output = args.output
        result = _read_json(_resolve(repo_root, args.round1_result))
        plan = build_round2_plan(
            contract, result, contract_path=args.contract, identity=identity
        )
        _write_plan_commands(plan, output)
        _write_json(_resolve(repo_root, output), plan)
        output_payload = plan
    elif args.command == "evaluate-round2":
        plan = _read_json(_resolve(repo_root, args.plan))
        result = evaluate_round2(plan, contract, repo_root=repo_root)
        _write_json(_resolve(repo_root, args.output), result)
        output_payload = result
    elif args.command == "plan-final":
        output = args.output
        result = _read_json(_resolve(repo_root, args.round2_result))
        plan = build_final_plan(
            contract, result, contract_path=args.contract, identity=identity
        )
        _write_plan_commands(plan, output)
        _write_json(_resolve(repo_root, output), plan)
        output_payload = plan
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(output_payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
