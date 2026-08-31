#!/usr/bin/env python3
"""Run one manual Linux job while sampling aggregate process-tree resources."""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    if args.interval <= 0:
        parser.error("--interval must be positive")
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

    previous: dict[tuple[int, int], tuple[int, int, int]] = {}
    cumulative_cpu_ticks = 0
    cumulative_read_bytes = 0
    cumulative_write_bytes = 0
    peak_rss_bytes = 0
    peak_processes = 0
    started = time.monotonic()
    previous_sample_time = started

    fieldnames = (
        "wall_seconds",
        "process_count",
        "rss_bytes",
        "peak_rss_bytes",
        "cumulative_cpu_seconds",
        "cpu_percent_one_core",
        "cpu_percent_capacity",
        "cumulative_read_bytes",
        "cumulative_write_bytes",
        "load_average_1m",
    )
    with samples_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        while True:
            now = time.monotonic()
            samples = process_tree(process.pid, page_size)
            rss_bytes = sum(item.rss_bytes for item in samples)
            peak_rss_bytes = max(peak_rss_bytes, rss_bytes)
            peak_processes = max(peak_processes, len(samples))
            delta_cpu_ticks = 0
            for item in samples:
                current = (item.cpu_ticks, item.read_bytes, item.write_bytes)
                old = previous.get(item.identity, (0, 0, 0))
                delta_cpu_ticks += max(0, current[0] - old[0])
                cumulative_read_bytes += max(0, current[1] - old[1])
                cumulative_write_bytes += max(0, current[2] - old[2])
                previous[item.identity] = current
            cumulative_cpu_ticks += delta_cpu_ticks
            elapsed = max(now - previous_sample_time, 1e-9)
            cpu_percent_one_core = (
                delta_cpu_ticks / clock_ticks / elapsed * 100.0
            )
            writer.writerow(
                {
                    "wall_seconds": now - started,
                    "process_count": len(samples),
                    "rss_bytes": rss_bytes,
                    "peak_rss_bytes": peak_rss_bytes,
                    "cumulative_cpu_seconds": cumulative_cpu_ticks / clock_ticks,
                    "cpu_percent_one_core": cpu_percent_one_core,
                    "cpu_percent_capacity": cpu_percent_one_core / logical_cpus,
                    "cumulative_read_bytes": cumulative_read_bytes,
                    "cumulative_write_bytes": cumulative_write_bytes,
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
    summary = {
        "command": args.command,
        "return_code": return_code,
        "forwarded_signal": forwarded_signal,
        "wall_seconds": finished - started,
        "sample_interval_seconds": args.interval,
        "logical_cpu_count": logical_cpus,
        "peak_process_count": peak_processes,
        "peak_process_tree_rss_bytes": peak_rss_bytes,
        "sampled_process_tree_cpu_seconds": cumulative_cpu_ticks / clock_ticks,
        "sampled_process_tree_read_bytes": cumulative_read_bytes,
        "sampled_process_tree_write_bytes": cumulative_write_bytes,
        "caveat": (
            "One-second /proc sampling can undercount processes that start and "
            "exit between samples; RSS is the simultaneous sum for observed "
            "members of the command's process tree."
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
