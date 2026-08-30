"""Deterministic performance harness for the exact latent-lexicon workflow."""

from __future__ import annotations

import argparse
import cProfile
import json
import os
import platform
import pstats
import sqlite3
import sys
import time
from importlib import metadata
from pathlib import Path
from typing import Any

from sktlm.latent.training import TrainingConfig, run_training


BENCHMARK_LISTS = {
    "smoke": Path("configs/benchmarks/latent_smoke_documents.txt"),
    "medium": Path("configs/benchmarks/latent_medium_documents.txt"),
}


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not-installed"


def _peak_rss_bytes() -> int | None:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            psapi = ctypes.WinDLL('psapi', use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = (
                wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                wintypes.DWORD,
            )
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            handle = kernel32.GetCurrentProcess()
            if psapi.GetProcessMemoryInfo(
                handle,
                ctypes.byref(counters),
                counters.cb,
            ):
                return int(counters.PeakWorkingSetSize)
        except (AttributeError, OSError):
            return None
        return None
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value if sys.platform == "darwin" else value * 1024
    except (ImportError, OSError):
        return None


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _software() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "sqlite": sqlite3.sqlite_version,
        "numpy": _package_version("numpy"),
        "sentencepiece": _package_version("sentencepiece"),
        "torch": _package_version("torch"),
        "sktlm": _package_version("sktlm"),
    }


def run_benchmark(
    *,
    benchmark: str,
    run_id: str,
    output_root: Path,
    passes: int,
    profile: bool,
    repo_root: Path,
) -> dict[str, Any]:
    document_list = BENCHMARK_LISTS[benchmark]
    config = TrainingConfig(
        manifest=Path("data/manifests/representations.csv"),
        document_list=document_list,
        output_root=output_root,
        run_id=run_id,
        passes=passes,
        equivalence_diagnostics=True,
    )
    profiler = cProfile.Profile() if profile else None
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    if profiler is None:
        result = run_training(config, repo_root=repo_root)
    else:
        result = profiler.runcall(run_training, config, repo_root=repo_root)
    cpu_seconds = time.process_time() - cpu_start
    wall_seconds = time.perf_counter() - wall_start
    training_characters = sum(
        int(item["characters"]) for item in result.history
    )
    inspection_characters = int(result.summary["characters"])
    character_visits = training_characters + inspection_characters
    training_segments = sum(int(item["segments"]) for item in result.history)
    inspection_segments = int(result.summary["segments"])
    segment_visits = training_segments + inspection_segments
    metrics = {
        'runtime': result.runtime,
        "schema_version": 1,
        "benchmark": benchmark,
        "document_list": document_list.as_posix(),
        "passes": passes,
        "workers": 1,
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "training_characters": training_characters,
        "inspection_characters": inspection_characters,
        "character_visits": character_visits,
        "training_segments": training_segments,
        "inspection_segments": inspection_segments,
        "segment_visits": segment_visits,
        "chars_per_second": character_visits / max(wall_seconds, 1e-12),
        "segments_per_second": segment_visits / max(wall_seconds, 1e-12),
        "peak_rss_bytes": _peak_rss_bytes(),
        "artifact_bytes": _directory_bytes(result.run_dir),
        "software": _software(),
    }
    (result.run_dir / "benchmark_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    if profiler is not None:
        profiler.dump_stats(result.run_dir / "profile.pstats")
        with (result.run_dir / "profile_top.txt").open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            stats = pstats.Stats(profiler, stream=handle)
            stats.strip_dirs().sort_stats("cumulative").print_stats(80)
    return metrics


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a deterministic exact latent-lexicon performance benchmark."
    )
    parser.add_argument("--benchmark", choices=tuple(BENCHMARK_LISTS), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/latent_benchmarks"),
    )
    parser.add_argument("--passes", type=int, default=1)
    parser.add_argument("--profile", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    metrics = run_benchmark(
        benchmark=args.benchmark,
        run_id=args.run_id,
        output_root=args.output_root,
        passes=args.passes,
        profile=args.profile,
        repo_root=Path(".").resolve(),
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
