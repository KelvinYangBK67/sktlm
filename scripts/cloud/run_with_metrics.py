#!/usr/bin/env python3
"""Run one manual Linux job while sampling aggregate process-tree resources."""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProcessSample:
    pid: int
    start_ticks: int
    parent_pid: int
    cpu_ticks: int
    rss_bytes: int
    read_bytes: int
    write_bytes: int
    io_wait_ticks: int

    @property
    def identity(self) -> tuple[int, int]:
        return self.pid, self.start_ticks


def read_process(pid: int, page_size: int) -> ProcessSample | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields = stat[stat.rfind(")") + 2 :].split()
        parent_pid = int(fields[1])
        cpu_ticks = int(fields[11]) + int(fields[12])
        start_ticks = int(fields[19])
        rss_bytes = int(fields[21]) * page_size
        io_wait_ticks = int(fields[39]) if len(fields) > 39 else 0
        io_values: dict[str, int] = {}
        for line in Path(f"/proc/{pid}/io").read_text(encoding="utf-8").splitlines():
            key, value = line.split(":", 1)
            io_values[key] = int(value)
    except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
        return None
    return ProcessSample(
        pid=pid,
        start_ticks=start_ticks,
        parent_pid=parent_pid,
        cpu_ticks=cpu_ticks,
        rss_bytes=rss_bytes,
        read_bytes=io_values.get("read_bytes", 0),
        write_bytes=io_values.get("write_bytes", 0),
        io_wait_ticks=io_wait_ticks,
    )


def process_tree(root_pid: int, page_size: int) -> tuple[ProcessSample, ...]:
    processes: dict[int, ProcessSample] = {}
    children: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        sample = read_process(int(entry.name), page_size)
        if sample is None:
            continue
        processes[sample.pid] = sample
        children.setdefault(sample.parent_pid, []).append(sample.pid)
    selected: list[ProcessSample] = []
    pending = [root_pid]
    seen: set[int] = set()
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        sample = processes.get(pid)
        if sample is not None:
            selected.append(sample)
        pending.extend(children.get(pid, ()))
    return tuple(selected)


def watched_storage(path: Path) -> dict[str, int]:
    """Measure the bounded production run tree by operational category."""

    values = {
        "run_bytes": 0,
        "sqlite_bytes": 0,
        "sqlite_wal_bytes": 0,
        "sqlite_shm_bytes": 0,
        "topology_bytes": 0,
        "training_shard_bytes": 0,
        "training_host_support_shard_bytes": 0,
        "training_bundle_marker_count": 0,
        "inspection_shard_bytes": 0,
        "completed_artifact_bytes": 0,
    }
    if not path.exists():
        return values
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        try:
            size = item.stat().st_size
        except FileNotFoundError:
            continue
        values["run_bytes"] += size
        relative = item.relative_to(path)
        if item.name == "learner.sqlite":
            values["sqlite_bytes"] += size
        elif item.name == "learner.sqlite-wal":
            values["sqlite_wal_bytes"] += size
        elif item.name == "learner.sqlite-shm":
            values["sqlite_shm_bytes"] += size
        elif relative.parts and relative.parts[0] == "topology":
            values["topology_bytes"] += size
        elif relative.parts[:2] == ("shards", "inspection"):
            values["inspection_shard_bytes"] += size
        elif relative.parts and relative.parts[0] == "shards":
            values["training_shard_bytes"] += size
            if item.name.endswith(".host-support.tsv"):
                values["training_host_support_shard_bytes"] += size
            if item.name.endswith(".complete.json") and "bundles" in relative.parts:
                values["training_bundle_marker_count"] += 1
        elif not (relative.parts and relative.parts[0] == "shards"):
            values["completed_artifact_bytes"] += size
    return values


def filesystem_usage(path: Path):
    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return shutil.disk_usage(candidate)


def memory_status() -> dict[str, int | None]:
    """Read physical availability and swap use from one procfs snapshot."""

    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            fields = raw.split()
            if fields:
                values[key] = int(fields[0]) * 1024
    except (FileNotFoundError, PermissionError, ValueError):
        return {"mem_available_bytes": None, "swap_used_bytes": None}
    swap_total = values.get("SwapTotal")
    swap_free = values.get("SwapFree")
    return {
        "mem_available_bytes": values.get("MemAvailable"),
        "swap_used_bytes": (
            None
            if swap_total is None or swap_free is None
            else max(0, swap_total - swap_free)
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--filesystem-interval", type=float, default=5.0)
    parser.add_argument("--storage-interval", type=float, default=30.0)
    parser.add_argument(
        "--watch-dir",
        type=Path,
        help="Run directory whose storage high-water marks should be sampled.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    if args.interval <= 0:
        parser.error("--interval must be positive")
    if args.filesystem_interval <= 0:
        parser.error("--filesystem-interval must be positive")
    if args.storage_interval <= 0:
        parser.error("--storage-interval must be positive")
    if sys.platform != "linux" or not Path("/proc").is_dir():
        parser.error("this process-tree monitor requires Linux /proc")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = args.output_dir / "process_tree_samples.csv"
    summary_path = args.output_dir / "process_tree_summary.json"
    if samples_path.exists() or summary_path.exists():
        parser.error(f"refusing to overwrite metrics in {args.output_dir}")

    page_size = os.sysconf("SC_PAGE_SIZE")
    clock_ticks = os.sysconf("SC_CLK_TCK")
    logical_cpus = os.cpu_count() or 1
    process = subprocess.Popen(args.command, start_new_session=True)
    forwarded_signal: int | None = None

    def forward(signum: int, _frame: object) -> None:
        nonlocal forwarded_signal
        forwarded_signal = signum
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGINT, forward)
    signal.signal(signal.SIGTERM, forward)

    previous: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    cumulative_cpu_ticks = 0
    cumulative_read_bytes = 0
    cumulative_write_bytes = 0
    peak_rss_bytes = 0
    peak_main_rss_bytes = 0
    peak_worker_rss_bytes = 0
    peak_processes = 0
    peak_process_breakdown: list[dict[str, int]] = []
    cumulative_io_wait_ticks = 0
    storage_peaks: dict[str, int] = {}
    started = time.monotonic()
    previous_sample_time = started
    next_filesystem_sample = started
    next_storage_sample = started
    filesystem_before = (
        filesystem_usage(args.watch_dir) if args.watch_dir is not None else None
    )
    filesystem_free_min = (
        None if filesystem_before is None else filesystem_before.free
    )
    filesystem_used_peak = (
        None if filesystem_before is None else filesystem_before.used
    )
    last_filesystem_sample = filesystem_before
    last_storage = watched_storage(Path("__sktlm_metrics_no_watch__"))
    mem_available_min: int | None = None
    swap_used_peak: int | None = None

    fieldnames = (
        "wall_seconds",
        "process_count",
        "rss_bytes",
        "peak_rss_bytes",
        "main_process_rss_bytes",
        "sum_worker_rss_bytes",
        "max_single_worker_rss_bytes",
        "cumulative_cpu_seconds",
        "cpu_percent_one_core",
        "cpu_percent_capacity",
        "cumulative_read_bytes",
        "cumulative_write_bytes",
        "cumulative_io_wait_seconds",
        "watched_run_bytes",
        "sqlite_bytes",
        "sqlite_wal_bytes",
        "topology_bytes",
        "training_shard_bytes",
        "training_host_support_shard_bytes",
        "training_bundle_marker_count",
        "inspection_shard_bytes",
        "filesystem_free_bytes",
        "filesystem_used_bytes",
        "mem_available_bytes",
        "swap_used_bytes",
        "load_average_1m",
    )
    with samples_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        while True:
            now = time.monotonic()
            samples = process_tree(process.pid, page_size)
            rss_bytes = sum(item.rss_bytes for item in samples)
            root_sample = next((item for item in samples if item.pid == process.pid), None)
            main_rss_bytes = 0 if root_sample is None else root_sample.rss_bytes
            worker_samples = tuple(
                item for item in samples if item.pid != process.pid
            )
            sum_worker_rss_bytes = sum(item.rss_bytes for item in worker_samples)
            max_single_worker_rss_bytes = max(
                (item.rss_bytes for item in worker_samples), default=0
            )
            if rss_bytes > peak_rss_bytes:
                peak_rss_bytes = rss_bytes
                peak_process_breakdown = [
                    {
                        "pid": item.pid,
                        "parent_pid": item.parent_pid,
                        "rss_bytes": item.rss_bytes,
                        "cpu_ticks": item.cpu_ticks,
                    }
                    for item in sorted(samples, key=lambda item: item.pid)
                ]
            if root_sample is not None:
                peak_main_rss_bytes = max(peak_main_rss_bytes, root_sample.rss_bytes)
            peak_worker_rss_bytes = max(
                peak_worker_rss_bytes,
                max_single_worker_rss_bytes,
            )
            peak_processes = max(peak_processes, len(samples))
            delta_cpu_ticks = 0
            for item in samples:
                current = (
                    item.cpu_ticks,
                    item.read_bytes,
                    item.write_bytes,
                    item.io_wait_ticks,
                )
                old = previous.get(item.identity, (0, 0, 0, 0))
                delta_cpu_ticks += max(0, current[0] - old[0])
                cumulative_read_bytes += max(0, current[1] - old[1])
                cumulative_write_bytes += max(0, current[2] - old[2])
                cumulative_io_wait_ticks += max(0, current[3] - old[3])
                previous[item.identity] = current
            cumulative_cpu_ticks += delta_cpu_ticks
            elapsed = max(now - previous_sample_time, 1e-9)
            cpu_percent_one_core = (
                delta_cpu_ticks / clock_ticks / elapsed * 100.0
            )
            if now >= next_storage_sample:
                last_storage = (
                    watched_storage(args.watch_dir)
                    if args.watch_dir is not None
                    else watched_storage(Path("__sktlm_metrics_no_watch__"))
                )
                next_storage_sample = now + args.storage_interval
            storage = last_storage
            for key, value in storage.items():
                storage_peaks[key] = max(storage_peaks.get(key, 0), value)
            if now >= next_filesystem_sample:
                last_filesystem_sample = (
                    filesystem_usage(args.watch_dir)
                    if args.watch_dir is not None
                    else None
                )
                next_filesystem_sample = now + args.filesystem_interval
            filesystem_sample = last_filesystem_sample
            if filesystem_sample is not None:
                filesystem_free_min = min(
                    filesystem_free_min, filesystem_sample.free
                )
                filesystem_used_peak = max(
                    filesystem_used_peak, filesystem_sample.used
                )
            memory = memory_status()
            mem_available = memory["mem_available_bytes"]
            swap_used = memory["swap_used_bytes"]
            if mem_available is not None:
                mem_available_min = (
                    mem_available
                    if mem_available_min is None
                    else min(mem_available_min, mem_available)
                )
            if swap_used is not None:
                swap_used_peak = (
                    swap_used
                    if swap_used_peak is None
                    else max(swap_used_peak, swap_used)
                )
            writer.writerow(
                {
                    "wall_seconds": now - started,
                    "process_count": len(samples),
                    "rss_bytes": rss_bytes,
                    "peak_rss_bytes": peak_rss_bytes,
                    "main_process_rss_bytes": main_rss_bytes,
                    "sum_worker_rss_bytes": sum_worker_rss_bytes,
                    "max_single_worker_rss_bytes": max_single_worker_rss_bytes,
                    "cumulative_cpu_seconds": cumulative_cpu_ticks / clock_ticks,
                    "cpu_percent_one_core": cpu_percent_one_core,
                    "cpu_percent_capacity": cpu_percent_one_core / logical_cpus,
                    "cumulative_read_bytes": cumulative_read_bytes,
                    "cumulative_write_bytes": cumulative_write_bytes,
                    "cumulative_io_wait_seconds": cumulative_io_wait_ticks / clock_ticks,
                    "watched_run_bytes": storage["run_bytes"],
                    "sqlite_bytes": storage["sqlite_bytes"],
                    "sqlite_wal_bytes": storage["sqlite_wal_bytes"],
                    "topology_bytes": storage["topology_bytes"],
                    "training_shard_bytes": storage["training_shard_bytes"],
                    "training_host_support_shard_bytes": storage[
                        "training_host_support_shard_bytes"
                    ],
                    "training_bundle_marker_count": storage[
                        "training_bundle_marker_count"
                    ],
                    "inspection_shard_bytes": storage["inspection_shard_bytes"],
                    "filesystem_free_bytes": (
                        None if filesystem_sample is None else filesystem_sample.free
                    ),
                    "filesystem_used_bytes": (
                        None if filesystem_sample is None else filesystem_sample.used
                    ),
                    "mem_available_bytes": mem_available,
                    "swap_used_bytes": swap_used,
                    "load_average_1m": os.getloadavg()[0],
                }
            )
            handle.flush()
            previous_sample_time = now
            if process.poll() is not None:
                break
            time.sleep(args.interval)

    return_code = process.wait()
    finished = time.monotonic()
    if args.watch_dir is not None:
        final_storage = watched_storage(args.watch_dir)
        for key, value in final_storage.items():
            storage_peaks[key] = max(storage_peaks.get(key, 0), value)
    filesystem_end = (
        filesystem_usage(args.watch_dir) if args.watch_dir is not None else None
    )
    host_memory_bytes = None
    try:
        host_memory_bytes = os.sysconf("SC_PHYS_PAGES") * page_size
    except (AttributeError, OSError, ValueError):
        pass
    summary = {
        "command": args.command,
        "return_code": return_code,
        "forwarded_signal": forwarded_signal,
        "wall_seconds": finished - started,
        "sample_interval_seconds": args.interval,
        "filesystem_sample_interval_seconds": args.filesystem_interval,
        "storage_sample_interval_seconds": args.storage_interval,
        "logical_cpu_count": logical_cpus,
        "peak_process_count": peak_processes,
        "peak_process_tree_rss_bytes": peak_rss_bytes,
        "peak_main_process_rss_bytes": peak_main_rss_bytes,
        "peak_worker_rss_bytes": peak_worker_rss_bytes,
        "peak_sample_process_breakdown": peak_process_breakdown,
        "host_memory_bytes": host_memory_bytes,
        "minimum_mem_available_bytes": mem_available_min,
        "peak_swap_used_bytes": swap_used_peak,
        "sampled_process_tree_cpu_seconds": cumulative_cpu_ticks / clock_ticks,
        "mean_process_tree_cpu_capacity_fraction": (
            cumulative_cpu_ticks
            / clock_ticks
            / max(finished - started, 1e-9)
            / logical_cpus
        ),
        "sampled_process_tree_read_bytes": cumulative_read_bytes,
        "sampled_process_tree_write_bytes": cumulative_write_bytes,
        "sampled_process_tree_io_wait_seconds": cumulative_io_wait_ticks / clock_ticks,
        "watch_dir": None if args.watch_dir is None else str(args.watch_dir),
        "peak_watched_run_bytes": storage_peaks.get("run_bytes"),
        "peak_sqlite_bytes": storage_peaks.get("sqlite_bytes"),
        "peak_sqlite_wal_bytes": storage_peaks.get("sqlite_wal_bytes"),
        "peak_sqlite_shm_bytes": storage_peaks.get("sqlite_shm_bytes"),
        "peak_topology_archive_bytes": storage_peaks.get("topology_bytes"),
        "peak_training_shard_bytes": storage_peaks.get("training_shard_bytes"),
        "peak_training_host_support_shard_bytes": storage_peaks.get(
            "training_host_support_shard_bytes"
        ),
        "peak_training_bundle_marker_count": storage_peaks.get(
            "training_bundle_marker_count"
        ),
        "peak_pending_inspection_shard_bytes": storage_peaks.get(
            "inspection_shard_bytes"
        ),
        "completed_artifact_bytes": storage_peaks.get("completed_artifact_bytes"),
        "filesystem_total_bytes": (
            None if filesystem_before is None else filesystem_before.total
        ),
        "filesystem_free_bytes_before": (
            None if filesystem_before is None else filesystem_before.free
        ),
        "filesystem_used_bytes_before": (
            None if filesystem_before is None else filesystem_before.used
        ),
        "filesystem_free_bytes_min": filesystem_free_min,
        "peak_filesystem_used_bytes": filesystem_used_peak,
        "filesystem_free_bytes_end": (
            None if filesystem_end is None else filesystem_end.free
        ),
        "filesystem_used_bytes_end": (
            None if filesystem_end is None else filesystem_end.used
        ),
        "caveat": (
            "Procfs sampling can undercount processes that start and exit between "
            "samples; process-tree RSS is a simultaneous sum that may double-count "
            "shared pages and is not the sole physical-memory truth."
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    if return_code < 0:
        raise SystemExit(128 - return_code)
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
