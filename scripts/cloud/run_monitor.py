#!/usr/bin/env python3
"""Generic read-only live monitor for plan-driven cloud experiment runs.

The monitor is deliberately stage-agnostic: it does not know about S1M2, S2,
or any specific scientific model.  It reads job identity and paths from a plan,
queries the host profile named by each job, and reports runtime/resource state.

Minimum useful job fields:
    host_role
    run_dir

Common optional fields used when present:
    job_id, run_id, workload_id, cell_id, script, condition, workers, passes
    control_dir
    document_list, manifest
    execution_bundle_plan, execution_bundle_plan_sha256

Examples
--------
One host, refresh every 60 s:
    python scripts/cloud/run_monitor.py --plan artifacts/.../plan.json core-04

Several hosts:
    python scripts/cloud/run_monitor.py --plan artifacts/.../plan.json core-04 core-05

A workload:
    python scripts/cloud/run_monitor.py --plan artifacts/.../plan.json stress

Everything in the plan:
    python scripts/cloud/run_monitor.py --plan artifacts/.../plan.json all

One shot:
    python scripts/cloud/run_monitor.py --plan artifacts/.../plan.json --once core-04

List plan jobs without SSH:
    python scripts/cloud/run_monitor.py --plan artifacts/.../plan.json --list

This tool is read-only.  It never launches, resumes, stops, audits, or mutates
a run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path(".sktlm-bridge.toml")
DEFAULT_INTERVAL = 60.0

BAD_STATES = {
    "SSHERR",
    "BADJSON",
    "LOCALERR",
    "FAILED",
    "AUDITFAIL",
    "STALE",
    "BADMANIFEST",
    "NO_MANIFEST",
    "PLANERR",
}

REMOTE = r"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

repo = Path(sys.argv[1])
plan_rel = Path(sys.argv[2])
job_key = sys.argv[3]
expected_head = sys.argv[4]
expected_plan_sha = sys.argv[5]

def canonical_sha256(payload):
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

plan_path = repo / plan_rel
plan = json.loads(plan_path.read_text(encoding="utf-8"))

if expected_plan_sha:
    actual_plan_sha = canonical_sha256(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )
    if plan.get("plan_sha256") != expected_plan_sha or actual_plan_sha != expected_plan_sha:
        raise RuntimeError("plan SHA-256 mismatch")

if expected_head and plan.get("git_sha") != expected_head:
    raise RuntimeError("plan git identity mismatch")

jobs = plan.get("jobs")
if not isinstance(jobs, list):
    raise RuntimeError("plan has no jobs list")

def identity(item):
    return str(item.get("job_id") or item.get("run_id") or "")

matches = [item for item in jobs if identity(item) == job_key]
if len(matches) != 1:
    raise RuntimeError(f"expected one job {job_key!r}, found {len(matches)}")
job = matches[0]

run_dir = repo / str(job["run_dir"])
control_rel = job.get("control_dir")
control_dir = repo / str(control_rel) if control_rel else None

manifest_candidates = []
if control_dir is not None:
    manifest_candidates.append(control_dir / "run_manifest.json")
manifest_candidates.extend(
    [
        run_dir / "production_run_manifest.json",
        run_dir / "run_manifest.json",
    ]
)
manifest_path = next((p for p in manifest_candidates if p.is_file()), None)

out = {
    "state": "UNKNOWN",
    "manifest_status": None,
    "return_code": None,
    "completed_passes": None,
    "active_pass": None,
    "next_document_index": None,
    "documents": None,
    "progress_source": None,
    "progress_mode": "documents",
    "bundle_plan_sha256": None,
    "bundle_count_per_pass": None,
    "bundle_pressure_per_pass": None,
    "pass_bundle_completed": None,
    "pass_pressure_completed": None,
    "training_bundle_completed": None,
    "training_bundle_total": None,
    "training_pressure_completed": None,
    "training_pressure_total": None,
    "live_bundle_markers": None,
    "bundle_progress_error": None,
    "wall": None,
    "cores_5m": None,
    "cores_15m": None,
    "rss": None,
    "peak": None,
    "proc": None,
    "load1": None,
    "mem_avail": None,
    "disk_free": None,
    "live_pid": None,
    "metrics_dir": None,
    "sample_age": None,
    "head_ok": None,
}

# Exact deployed Git identity when the plan binds one.
if expected_head:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout.strip()
    out["head_ok"] = head == expected_head

# Generic process identity:
# accept an exact --job-id JOB or --run-id RUN argv pair.  This avoids binding
# the monitor to any stage-specific Python module.
job_id = str(job.get("job_id") or "")
run_id = str(job.get("run_id") or "")

def contains_pair(argv, flag, value):
    if not value:
        return False
    try:
        i = argv.index(flag)
    except ValueError:
        return False
    return i + 1 < len(argv) and argv[i + 1] == value

def find_live_pid():
    own_pid = os.getpid()
    try:
        entries = list(Path("/proc").iterdir())
    except Exception:
        return None

    candidates = []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == own_pid:
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except (OSError, PermissionError):
            continue
        if not raw:
            continue
        argv = [
            part.decode("utf-8", errors="replace")
            for part in raw.split(b"\0")
            if part
        ]
        if contains_pair(argv, "--job-id", job_id) or contains_pair(argv, "--run-id", run_id):
            candidates.append(pid)
    return min(candidates) if candidates else None

pid = find_live_pid()
out["live_pid"] = pid

manifest = None
metrics_dir = None
if manifest_path is not None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        status = manifest.get("result_status") or manifest.get("status")
        out["manifest_status"] = status

        history = manifest.get("resume_history") or manifest.get("attempts") or []
        if isinstance(history, list) and history:
            latest = history[-1] if isinstance(history[-1], dict) else {}
            metrics_rel = latest.get("metrics_dir")
            if metrics_rel:
                metrics_dir = repo / str(metrics_rel)
                out["metrics_dir"] = str(metrics_dir)
            out["return_code"] = latest.get("return_code")

        if status == "PASS":
            out["state"] = "PASS"
        elif status == "AUDIT_FAILED":
            out["state"] = "AUDITFAIL"
        elif status == "FAILED":
            out["state"] = "FAILED"
        elif status == "AUDITING":
            out["state"] = "AUDITING" if pid else "AUDIT?"
        elif status == "RUNNING":
            out["state"] = "RUNNING" if pid else "STALE"
        elif status:
            out["state"] = str(status)
        else:
            out["state"] = "RUNNING" if pid else "UNKNOWN"
    except Exception as exc:
        out["state"] = "BADMANIFEST"
        out["manifest_error"] = repr(exc)
else:
    out["state"] = "RUNNING" if pid else "NO_MANIFEST"

# Resolve a document denominator from a document list or a representation
# manifest.  If neither is available, DOC/ETA remain unavailable rather than
# guessing.
def count_document_list(path):
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                count += 1
    return count

def count_manifest_documents(path, script, condition):
    documents = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if script and row.get("script") != script:
                continue
            if condition and row.get("condition") != condition:
                continue
            relative = row.get("relative_path")
            if relative:
                documents.add(relative)
    return len(documents)

document_list_rel = job.get("document_list")
if document_list_rel:
    try:
        out["documents"] = count_document_list(repo / str(document_list_rel))
    except Exception:
        pass

if out["documents"] is None and job.get("manifest"):
    try:
        out["documents"] = count_manifest_documents(
            repo / str(job["manifest"]),
            str(job.get("script") or ""),
            str(job.get("condition") or ""),
        )
    except Exception:
        pass

# Optional bundle-aware progress.  This relies only on the common execution
# bundle materialization files and generic marker fields, not on a stage/model
# schema name.
bundle_rows = []
bundles_by_document = {}
document_pressure = []
document_bundle_count = []

execution_bundle_plan = job.get("execution_bundle_plan")
if execution_bundle_plan:
    out["progress_mode"] = "pressure"
    try:
        bundle_root = repo / str(execution_bundle_plan)
        documents_tsv = bundle_root / "documents.tsv"
        bundle_summary_path = bundle_root / "summary.json"
        bundles_jsonl = bundle_root / "bundles.jsonl"

        with documents_tsv.open("r", encoding="utf-8", newline="") as handle:
            document_rows = list(csv.DictReader(handle, delimiter="\t"))

        out["documents"] = len(document_rows)
        document_pressure = [int(row["pressure"]) for row in document_rows]
        document_bundle_count = [int(row["bundles"]) for row in document_rows]

        summary_payload = json.loads(bundle_summary_path.read_text(encoding="utf-8"))
        expected_bundle_sha = job.get("execution_bundle_plan_sha256")
        actual_bundle_sha = summary_payload.get("plan_sha256")

        if expected_bundle_sha and actual_bundle_sha != expected_bundle_sha:
            raise RuntimeError("execution bundle plan SHA mismatch")
        out["bundle_plan_sha256"] = actual_bundle_sha

        with bundles_jsonl.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                item = {
                    "document_index": int(payload["document_index"]),
                    "bundle_index": int(payload["bundle_index"]),
                    "first_segment_ordinal": int(payload["first_segment_ordinal"]),
                    "last_segment_ordinal_exclusive": int(
                        payload["last_segment_ordinal_exclusive"]
                    ),
                    "segment_count": int(payload["segment_count"]),
                    "pressure": int(payload["pressure"]),
                }
                bundle_rows.append(item)
                bundles_by_document.setdefault(item["document_index"], []).append(item)

        bundle_count = len(bundle_rows)
        bundle_pressure = sum(item["pressure"] for item in bundle_rows)

        declared_count = summary_payload.get("actual_bundle_count")
        if declared_count is not None and bundle_count != int(declared_count):
            raise RuntimeError("execution bundle count mismatch")
        if (
            sum(document_bundle_count) != bundle_count
            or sum(document_pressure) != bundle_pressure
        ):
            raise RuntimeError("documents.tsv and bundles.jsonl disagree")

        out["bundle_count_per_pass"] = bundle_count
        out["bundle_pressure_per_pass"] = bundle_pressure
    except Exception as exc:
        out["bundle_progress_error"] = "bundle-plan: " + repr(exc)

# Process-tree metrics: scan only the most recent ~16 minutes into memory even
# if the CSV has been running for many hours.
if metrics_dir is not None:
    samples = metrics_dir / "process_tree_samples.csv"
    summary = metrics_dir / "process_tree_summary.json"

    if samples.is_file():
        try:
            recent = deque()
            last = None

            def num(row, name):
                try:
                    return float(row[name])
                except Exception:
                    return None

            with samples.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    wall = num(row, "wall_seconds")
                    if wall is None:
                        continue
                    last = row
                    recent.append(row)
                    cutoff = wall - 16 * 60
                    while len(recent) > 1:
                        first_wall = num(recent[0], "wall_seconds")
                        if first_wall is None or first_wall < cutoff:
                            recent.popleft()
                        else:
                            break

            if last is not None:
                out["wall"] = num(last, "wall_seconds")
                out["rss"] = num(last, "rss_bytes")
                out["peak"] = num(last, "peak_rss_bytes")
                proc_value = num(last, "process_count")
                out["proc"] = None if proc_value is None else int(proc_value)
                out["load1"] = num(last, "load_average_1m")

                recent_rows = list(recent)

                def rolling_cores(window_seconds):
                    end_wall = num(recent_rows[-1], "wall_seconds")
                    end_cpu = num(recent_rows[-1], "cumulative_cpu_seconds")
                    if end_wall is None or end_cpu is None:
                        return None
                    target = max(0.0, end_wall - window_seconds)
                    start_row = recent_rows[0]
                    for candidate in recent_rows:
                        candidate_wall = num(candidate, "wall_seconds")
                        if candidate_wall is None:
                            continue
                        if candidate_wall <= target:
                            start_row = candidate
                        else:
                            break
                    start_wall = num(start_row, "wall_seconds")
                    start_cpu = num(start_row, "cumulative_cpu_seconds")
                    if (
                        start_wall is None
                        or start_cpu is None
                        or end_wall <= start_wall
                    ):
                        return None
                    delta_cpu = end_cpu - start_cpu
                    if delta_cpu < 0:
                        return None
                    return delta_cpu / (end_wall - start_wall)

                out["cores_5m"] = rolling_cores(5 * 60)
                out["cores_15m"] = rolling_cores(15 * 60)
                try:
                    out["sample_age"] = max(
                        0.0,
                        time.time() - samples.stat().st_mtime,
                    )
                except OSError:
                    pass
        except Exception:
            pass

    if summary.is_file():
        try:
            payload = json.loads(summary.read_text(encoding="utf-8"))
            if out["return_code"] is None:
                out["return_code"] = payload.get("return_code")
            if out["wall"] is None:
                out["wall"] = payload.get("wall_seconds")
            if out["peak"] is None:
                out["peak"] = payload.get("peak_process_tree_rss_bytes")
        except Exception:
            pass

# Prefer the conventional checkpoint, with a shallow fallback for compatible
# future stages.
checkpoint = None
checkpoint_path = run_dir / "checkpoint.json"

if checkpoint_path.is_file():
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        out["progress_source"] = str(checkpoint_path)
    except Exception:
        checkpoint = None

if checkpoint is None and run_dir.is_dir():
    candidates = []
    for path in run_dir.glob("*.json"):
        if any(key in path.name.lower() for key in ("checkpoint", "state", "progress")):
            try:
                candidates.append((path.stat().st_mtime, path))
            except OSError:
                pass
    for _mtime, path in sorted(candidates, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("completed_passes"), int):
            checkpoint = payload
            out["progress_source"] = str(path)
            break

if isinstance(checkpoint, dict):
    completed_passes = checkpoint.get("completed_passes")
    next_document_index = checkpoint.get("next_document_index")
    active_pass = checkpoint.get("active_pass")
    if isinstance(completed_passes, int):
        out["completed_passes"] = completed_passes
    if isinstance(next_document_index, int):
        out["next_document_index"] = next_document_index
    if isinstance(active_pass, int):
        out["active_pass"] = active_pass

# Bundle progress for any stage that preserves the current common bundle
# layout.  Marker schema strings are intentionally ignored; identity is checked
# through plan/pass/document/bundle coordinates and segment ranges.
try:
    passes = int(job.get("passes") or 0)
    completed_passes = out.get("completed_passes")
    next_document_index = out.get("next_document_index")

    if (
        execution_bundle_plan
        and passes > 0
        and out.get("bundle_progress_error") is None
        and isinstance(completed_passes, int)
        and isinstance(next_document_index, int)
        and isinstance(out.get("bundle_count_per_pass"), int)
        and isinstance(out.get("bundle_pressure_per_pass"), int)
    ):
        bundle_count_per_pass = int(out["bundle_count_per_pass"])
        pressure_per_pass = int(out["bundle_pressure_per_pass"])
        completed_passes = min(passes, max(0, completed_passes))

        training_bundle_completed = completed_passes * bundle_count_per_pass
        training_pressure_completed = completed_passes * pressure_per_pass
        pass_bundle_completed = 0
        pass_pressure_completed = 0
        live_bundle_markers = 0

        if completed_passes < passes:
            current_pass = out.get("active_pass")
            if not isinstance(current_pass, int):
                current_pass = completed_passes + 1

            committed_documents = min(
                max(0, next_document_index),
                len(document_pressure),
            )
            pass_bundle_completed = sum(
                document_bundle_count[:committed_documents]
            )
            pass_pressure_completed = sum(
                document_pressure[:committed_documents]
            )

            marker_root = (
                run_dir
                / "shards"
                / f"pass_{current_pass:04d}"
                / "bundles"
            )
            counted = set()

            if marker_root.is_dir():
                for marker in marker_root.glob(
                    "document_*.bundle_*.complete.json"
                ):
                    try:
                        payload = json.loads(marker.read_text(encoding="utf-8"))
                        marker_plan_sha = payload.get("plan_sha256")
                        expected_marker_sha = out.get("bundle_plan_sha256")
                        if (
                            expected_marker_sha
                            and marker_plan_sha
                            and marker_plan_sha != expected_marker_sha
                        ):
                            continue
                        if int(payload.get("pass_index", -1)) != current_pass:
                            continue

                        document_index = int(payload.get("document_index", -1))
                        bundle_index = int(payload.get("bundle_index", -1))
                        if document_index < committed_documents:
                            continue

                        key = (document_index, bundle_index)
                        if key in counted:
                            continue

                        planned = next(
                            (
                                item
                                for item in bundles_by_document.get(document_index, [])
                                if item["bundle_index"] == bundle_index
                            ),
                            None,
                        )
                        if planned is None:
                            continue

                        if (
                            int(payload.get("first_segment_ordinal", -1))
                            != planned["first_segment_ordinal"]
                            or int(payload.get("last_segment_ordinal_exclusive", -1))
                            != planned["last_segment_ordinal_exclusive"]
                            or int(payload.get("segment_count", -1))
                            != planned["segment_count"]
                        ):
                            continue

                        segment_name = payload.get("segment_shard")
                        if (
                            isinstance(segment_name, str)
                            and not (marker.parent / segment_name).is_file()
                        ):
                            continue

                        counted.add(key)
                        pass_bundle_completed += 1
                        pass_pressure_completed += planned["pressure"]
                        live_bundle_markers += 1
                    except Exception:
                        continue

            pass_bundle_completed = min(
                bundle_count_per_pass,
                pass_bundle_completed,
            )
            pass_pressure_completed = min(
                pressure_per_pass,
                pass_pressure_completed,
            )
            training_bundle_completed += pass_bundle_completed
            training_pressure_completed += pass_pressure_completed

        out["pass_bundle_completed"] = pass_bundle_completed
        out["pass_pressure_completed"] = pass_pressure_completed
        out["training_bundle_completed"] = training_bundle_completed
        out["training_bundle_total"] = passes * bundle_count_per_pass
        out["training_pressure_completed"] = training_pressure_completed
        out["training_pressure_total"] = passes * pressure_per_pass
        out["live_bundle_markers"] = live_bundle_markers

except Exception as exc:
    out["bundle_progress_error"] = "bundle-progress: " + repr(exc)

try:
    with open("/proc/meminfo", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("MemAvailable:"):
                out["mem_avail"] = int(line.split()[1]) * 1024
                break
except Exception:
    pass

try:
    out["disk_free"] = shutil.disk_usage(repo).free
except Exception:
    pass

print(json.dumps(out, separators=(",", ":")))
"""


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def discover_repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        root = explicit.resolve()
        if not (root / ".git").exists():
            raise RuntimeError(f"--repo-root is not a Git repository: {root}")
        return root

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()

    fallback = Path(__file__).resolve().parents[2]
    if (fallback / ".git").exists():
        return fallback

    raise RuntimeError(
        "could not locate repository root; run inside the repo or pass --repo-root"
    )


def resolve_repo_file(repo_root: Path, value: Path, *, label: str) -> tuple[Path, str]:
    path = value if value.is_absolute() else repo_root / value
    path = path.resolve()
    try:
        relative = path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"{label} must be inside the repository: {path}") from exc
    if not path.is_file():
        raise RuntimeError(f"{label} does not exist: {path}")
    return path, relative


def validate_plan(plan: dict[str, Any]) -> None:
    jobs = plan.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise RuntimeError("plan contains no jobs")

    if plan.get("plan_sha256") is not None:
        expected = str(plan["plan_sha256"])
        actual = canonical_sha256(
            {key: value for key, value in plan.items() if key != "plan_sha256"}
        )
        if expected != actual:
            raise RuntimeError("plan_sha256 does not match canonical plan payload")

    if plan.get("git_sha") is not None:
        git_sha = str(plan["git_sha"])
        if len(git_sha) != 40 or any(c not in "0123456789abcdef" for c in git_sha):
            raise RuntimeError("plan git_sha is not a valid full SHA-1")

    identities = []
    for job in jobs:
        if not isinstance(job, dict):
            raise RuntimeError("plan jobs must be objects")
        key = str(job.get("job_id") or job.get("run_id") or "")
        if not key:
            raise RuntimeError("every job needs job_id or run_id")
        if not job.get("host_role"):
            raise RuntimeError(f"job has no host_role: {key}")
        if not job.get("run_dir"):
            raise RuntimeError(f"job has no run_dir: {key}")
        identities.append(key)

    if len(identities) != len(set(identities)):
        raise RuntimeError("job_id/run_id identities are not unique")


def load_plan(repo_root: Path, plan_arg: Path) -> tuple[dict[str, Any], Path, str]:
    path, relative = resolve_repo_file(repo_root, plan_arg, label="plan")
    plan = json.loads(path.read_text(encoding="utf-8"))
    validate_plan(plan)
    return plan, path, relative


def job_key(job: dict[str, Any]) -> str:
    return str(job.get("job_id") or job.get("run_id"))


def select_jobs(plan: dict[str, Any], selectors: list[str]) -> list[dict[str, Any]]:
    jobs = list(plan["jobs"])
    if not selectors or "all" in selectors:
        return jobs

    selected: set[str] = set()
    unmatched: list[str] = []

    for selector in selectors:
        matched = [
            job
            for job in jobs
            if selector
            in {
                str(job.get("host_role", "")),
                str(job.get("job_id", "")),
                str(job.get("run_id", "")),
                str(job.get("workload_id", "")),
                str(job.get("cell_id", "")),
                str(job.get("stage", "")),
                str(job.get("phase", "")),
            }
        ]
        if not matched:
            unmatched.append(selector)
        else:
            selected.update(job_key(job) for job in matched)

    if unmatched:
        available = sorted(
            {
                str(job.get(field, ""))
                for job in jobs
                for field in (
                    "host_role",
                    "workload_id",
                    "stage",
                    "phase",
                )
                if job.get(field)
            }
        )
        raise RuntimeError(
            "selector(s) not present in plan: "
            + ", ".join(unmatched)
            + "; available selectors include: "
            + ", ".join(available)
        )

    return [job for job in jobs if job_key(job) in selected]


def load_bridge(repo_root: Path):
    src = repo_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    path = repo_root / "scripts/cloud/sktlm_bridge.py"
    if not path.is_file():
        raise RuntimeError(f"cloud bridge is missing: {path}")

    spec = importlib.util.spec_from_file_location("_run_monitor_bridge", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load cloud bridge: {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_label(job: dict[str, Any]) -> str:
    script_short = {
        "iast": "iast",
        "iast_m0_prime": "iast'",
        "devanagari": "deva",
    }.get(str(job.get("script")), str(job.get("script", "-")))

    condition_short = {
        "surface_word": "surface",
        "legacy_joined": "legacy",
        "continuous": "conti",
    }.get(str(job.get("condition")), str(job.get("condition", "-")))

    if job.get("script") or job.get("condition"):
        return f"{script_short}/{condition_short}"
    return str(job.get("label") or job.get("cell_id") or "-")


def task_label(job: dict[str, Any]) -> str:
    value = str(
        job.get("workload_id")
        or job.get("stage")
        or job.get("phase")
        or "-"
    )
    return {
        "representative": "repre",
        "stress": "stress",
        "full": "full",
        "worker_calibration": "calib",
        "bounded_interface": "bounded",
    }.get(value, value[:10])


def fmt_time(sec: Any) -> str:
    if sec is None:
        return "-"
    try:
        sec = max(0, int(float(sec)))
    except Exception:
        return "-"
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h >= 100:
        return f"{h}h"
    return f"{h:02d}:{m:02d}:{s:02d}"


def fmt_gib(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) / 1024**3:.2f}G"
    except Exception:
        return "-"


def fmt_cores(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f}c"
    except Exception:
        return "-"


def progress_and_eta(
    job: dict[str, Any],
    live: dict[str, Any],
) -> tuple[str, str, str, float | None, float | None, str]:
    try:
        passes = int(job.get("passes") or 0)
    except Exception:
        passes = 0

    documents = live.get("documents")
    completed_passes = live.get("completed_passes")
    active_pass = live.get("active_pass")
    next_document_index = live.get("next_document_index")
    wall = live.get("wall")

    pass_text = "-"
    doc_text = "-"
    bundle_text = "-"
    frac: float | None = None
    eta: float | None = None
    mode = str(live.get("progress_mode") or "documents")

    if (
        passes > 0
        and isinstance(completed_passes, int)
        and isinstance(next_document_index, int)
    ):
        if completed_passes >= passes:
            pass_text = f"{passes}/{passes}"
            if isinstance(documents, int):
                doc_text = f"{documents}/{documents}"
        else:
            current_pass = (
                active_pass
                if isinstance(active_pass, int)
                else completed_passes + 1
            )
            pass_text = f"{current_pass}/{passes}"
            if isinstance(documents, int):
                doc_text = f"{next_document_index}/{documents}"
            else:
                doc_text = f"{next_document_index}/?"

    bundle_done = live.get("training_bundle_completed")
    bundle_total = live.get("training_bundle_total")
    pressure_done = live.get("training_pressure_completed")
    pressure_total = live.get("training_pressure_total")

    if (
        isinstance(bundle_done, int)
        and isinstance(bundle_total, int)
        and bundle_total > 0
    ):
        bundle_text = f"{bundle_done}/{bundle_total}"

    if (
        mode == "pressure"
        and isinstance(pressure_done, int)
        and isinstance(pressure_total, int)
        and pressure_total > 0
    ):
        frac = min(1.0, max(0.0, pressure_done / pressure_total))
    elif (
        passes > 0
        and isinstance(completed_passes, int)
        and isinstance(next_document_index, int)
        and isinstance(documents, int)
        and documents > 0
    ):
        completed_passes = min(passes, max(0, completed_passes))
        done = completed_passes * documents
        if completed_passes < passes:
            done += min(documents, max(0, next_document_index))
        total = passes * documents
        frac = min(1.0, max(0.0, done / total))
        mode = "documents"
    else:
        mode = "none"

    if (
        live.get("state") == "RUNNING"
        and frac is not None
        and wall is not None
        and frac >= 0.005
        and frac < 1.0
    ):
        eta = float(wall) * (1.0 / frac - 1.0)

    if live.get("state") == "PASS":
        frac = 1.0
        eta = 0.0

    return pass_text, doc_text, bundle_text, frac, eta, mode


def query_job(
    *,
    job: dict[str, Any],
    bridge: Any,
    runner: Any,
    config_path: Path,
    remote_plan_rel: str,
    expected_head: str,
    expected_plan_sha: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    role = str(job["host_role"])

    if role == "local-validation":
        return job, {
            "state": "LOCALONLY",
            "error": "local-validation jobs have no remote host profile",
        }

    try:
        cfg = bridge.load_config(
            config_path,
            explicit=True,
            host_profile=role,
        )
        if cfg.host_role is not None and cfg.host_role != role:
            raise RuntimeError(
                f"bridge profile {role} resolves to role {cfg.host_role}"
            )
        if not cfg.remote_repo:
            raise RuntimeError(f"bridge profile {role} has no remote_repo")

        cmd = (
            "python3 -c "
            + shlex.quote(REMOTE)
            + " "
            + shlex.quote(cfg.remote_repo)
            + " "
            + shlex.quote(remote_plan_rel)
            + " "
            + shlex.quote(job_key(job))
            + " "
            + shlex.quote(expected_head)
            + " "
            + shlex.quote(expected_plan_sha)
        )

        result = bridge.run_ssh(cfg, cmd, runner)

        if result.returncode:
            return job, {
                "state": "SSHERR",
                "error": (result.stderr or result.stdout).strip(),
            }

        try:
            return job, json.loads(result.stdout)
        except Exception:
            return job, {
                "state": "BADJSON",
                "error": result.stdout.strip(),
            }

    except Exception as exc:
        return job, {
            "state": "LOCALERR",
            "error": repr(exc),
        }


def render_table(
    *,
    plan: dict[str, Any],
    plan_rel: str,
    jobs: list[dict[str, Any]],
    results: list[tuple[dict[str, Any], dict[str, Any]]],
) -> bool:
    print(
        f"PLAN: type={plan.get('plan_type', plan.get('stage', '-'))} "
        f"path={plan_rel} "
        f"sha={str(plan.get('plan_sha256', '-'))[:12]} "
        f"git={str(plan.get('git_sha', '-'))[:12]} "
        f"selected={len(jobs)}/{len(plan.get('jobs', []))}"
    )
    print()

    header = (
        f"{'HOST':9s} "
        f"{'TASK':10s} "
        f"{'LOAD':13s} "
        f"{'W':>3s} "
        f"{'STATE':12s} "
        f"{'PASS':>7s} "
        f"{'DOC':>9s} "
        f"{'BUNDLE':>13s} "
        f"{'WORK':>7s} "
        f"{'ELAPSED':>9s} "
        f"{'ETA':>9s} "
        f"{'CPU5M':>7s} "
        f"{'CPU15M':>7s} "
        f"{'RSS':>7s} "
        f"{'PEAK':>7s} "
        f"{'PROC':>5s} "
        f"{'LOAD1':>6s} "
        f"{'MEMAVL':>8s} "
        f"{'DISK':>8s}"
    )
    print(header)
    print("-" * len(header))

    problem = False
    modes: set[str] = set()

    for job, live in results:
        raw_state = str(live.get("state", "?"))
        if raw_state in BAD_STATES:
            problem = True

        pass_text, doc_text, bundle_text, frac, eta, mode = progress_and_eta(
            job,
            live,
        )
        modes.add(mode)

        prog = f"{frac * 100:5.1f}%" if frac is not None else "-"
        proc = str(live["proc"]) if live.get("proc") is not None else "-"
        load1 = (
            f"{float(live['load1']):.2f}"
            if live.get("load1") is not None
            else "-"
        )

        display_state = raw_state
        if raw_state == "FAILED" and live.get("return_code") is not None:
            display_state = f"FAILED/{live['return_code']}"

        print(
            f"{str(job.get('host_role', '-')):9.9s} "
            f"{task_label(job):10.10s} "
            f"{load_label(job):13.13s} "
            f"{str(job.get('workers', '-')):>3s} "
            f"{display_state:12.12s} "
            f"{pass_text:>7s} "
            f"{doc_text:>9s} "
            f"{bundle_text:>13s} "
            f"{prog:>7s} "
            f"{fmt_time(live.get('wall')):>9s} "
            f"{fmt_time(eta):>9s} "
            f"{fmt_cores(live.get('cores_5m')):>7s} "
            f"{fmt_cores(live.get('cores_15m')):>7s} "
            f"{fmt_gib(live.get('rss')):>7s} "
            f"{fmt_gib(live.get('peak')):>7s} "
            f"{proc:>5s} "
            f"{load1:>6s} "
            f"{fmt_gib(live.get('mem_avail')):>8s} "
            f"{fmt_gib(live.get('disk_free')):>8s}"
        )

        if raw_state in {"SSHERR", "BADJSON", "LOCALERR", "LOCALONLY"}:
            if raw_state != "LOCALONLY":
                problem = True
            print("  ERROR:", live.get("error", ""))

        if live.get("bundle_progress_error"):
            problem = True
            print("  WARNING:", live["bundle_progress_error"])

        if live.get("head_ok") is False:
            problem = True
            print("  WARNING: remote HEAD differs from plan git_sha")

        sample_age = live.get("sample_age")
        if (
            live.get("state") == "RUNNING"
            and sample_age is not None
            and float(sample_age) > 120
        ):
            problem = True
            print(
                "  WARNING: metrics sample is stale "
                f"({int(float(sample_age))}s old)"
            )

    print("-" * len(header))

    if modes == {"pressure"}:
        note = (
            "WORK = pressure-weighted bundle progress; "
            "ETA = cumulative pressure-throughput projection."
        )
    elif modes == {"documents"}:
        note = (
            "WORK = document-count fallback progress; "
            "ETA = cumulative document-throughput projection."
        )
    elif modes == {"none"}:
        note = "WORK/ETA unavailable because this plan exposes no compatible progress denominator."
    else:
        note = (
            "WORK uses bundle pressure when available, document fallback when "
            "available, otherwise remains unavailable."
        )

    print(
        "NOTE: DOC = durable committed documents in the active pass; "
        "BUNDLE = completed training bundles when the common bundle layout exists; "
        + note
    )

    running = sum(1 for _, live in results if live.get("state") == "RUNNING")
    passed = sum(1 for _, live in results if live.get("state") == "PASS")
    failed = sum(
        1
        for _, live in results
        if live.get("state") in {"FAILED", "AUDITFAIL", "STALE"}
    )

    print(
        f"SUMMARY: running={running} passed={passed} failed={failed} "
        f"selected={len(results)} health={'CHECK' if problem else 'OK'}"
    )
    return problem


def render_json(
    *,
    plan: dict[str, Any],
    plan_rel: str,
    results: list[tuple[dict[str, Any], dict[str, Any]]],
) -> bool:
    rows = []
    problem = False

    for job, live in results:
        state = str(live.get("state", "?"))
        if state in BAD_STATES:
            problem = True

        pass_text, doc_text, bundle_text, frac, eta, mode = progress_and_eta(
            job,
            live,
        )
        rows.append(
            {
                "job": job,
                "live": live,
                "derived": {
                    "pass": pass_text,
                    "document": doc_text,
                    "bundle": bundle_text,
                    "progress_fraction": frac,
                    "eta_seconds": eta,
                    "progress_mode": mode,
                },
            }
        )

    print(
        json.dumps(
            {
                "plan": {
                    "path": plan_rel,
                    "plan_type": plan.get("plan_type"),
                    "stage": plan.get("stage"),
                    "plan_sha256": plan.get("plan_sha256"),
                    "git_sha": plan.get("git_sha"),
                },
                "jobs": rows,
                "health": "CHECK" if problem else "OK",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return problem


def list_jobs(plan: dict[str, Any], plan_rel: str) -> None:
    print(
        f"PLAN type={plan.get('plan_type', plan.get('stage', '-'))} "
        f"path={plan_rel} sha={str(plan.get('plan_sha256', '-'))[:12]}"
    )
    print(
        f"{'HOST':12s} {'TASK':20s} {'LOAD':16s} "
        f"{'W':>3s} ID"
    )
    print("-" * 110)
    for job in plan["jobs"]:
        print(
            f"{str(job.get('host_role', '-')):12.12s} "
            f"{str(job.get('workload_id') or job.get('stage') or job.get('phase') or '-'):20.20s} "
            f"{load_label(job):16.16s} "
            f"{str(job.get('workers', '-')):>3s} "
            f"{job_key(job)}"
        )


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generic read-only monitor for plan-driven cloud experiment runs. "
            "Selectors may be host roles, IDs, workloads, stages, phases, cells, or 'all'."
        )
    )
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="bridge TOML (default: .sktlm-bridge.toml)",
    )
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help="refresh interval in seconds (default: 60)",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-clear", action="store_true")
    parser.add_argument("--json", action="store_true", help="implies --once")
    parser.add_argument(
        "--list",
        action="store_true",
        help="list plan jobs without contacting hosts",
    )
    parser.add_argument("selectors", nargs="*")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)

    if args.interval <= 0:
        raise SystemExit("--interval must be positive")

    repo_root = discover_repo_root(args.repo_root)
    plan, _plan_path, plan_rel = load_plan(repo_root, args.plan)

    if args.list:
        list_jobs(plan, plan_rel)
        return 0

    jobs = select_jobs(plan, list(args.selectors))
    if not jobs:
        raise RuntimeError("no jobs selected")

    config_path = args.config
    if not config_path.is_absolute():
        config_path = repo_root / config_path
    config_path = config_path.resolve()
    if not config_path.is_file():
        raise RuntimeError(f"bridge config does not exist: {config_path}")

    bridge = load_bridge(repo_root)
    runner = bridge.SystemRunner()

    expected_head = str(plan.get("git_sha") or "")
    expected_plan_sha = str(plan.get("plan_sha256") or "")
    once = bool(args.once or args.json)

    while True:
        started = time.monotonic()

        with ThreadPoolExecutor(
            max_workers=max(1, min(len(jobs), 16))
        ) as pool:
            futures = [
                pool.submit(
                    query_job,
                    job=job,
                    bridge=bridge,
                    runner=runner,
                    config_path=config_path,
                    remote_plan_rel=plan_rel,
                    expected_head=expected_head,
                    expected_plan_sha=expected_plan_sha,
                )
                for job in jobs
            ]
            results = [future.result() for future in futures]

        order = {job_key(job): index for index, job in enumerate(jobs)}
        results.sort(key=lambda item: order[job_key(item[0])])

        if not once and not args.no_clear and sys.stdout.isatty():
            print("\033[2J\033[H", end="")

        if args.json:
            problem = render_json(
                plan=plan,
                plan_rel=plan_rel,
                results=results,
            )
        else:
            print(time.strftime("%Y-%m-%d %H:%M:%S %z"))
            problem = render_table(
                plan=plan,
                plan_rel=plan_rel,
                jobs=jobs,
                results=results,
            )

        if once:
            return 1 if problem else 0

        delay = max(0.0, float(args.interval) - (time.monotonic() - started))
        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"run_monitor: {exc}", file=sys.stderr)
        raise SystemExit(2)
