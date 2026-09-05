"""Deterministic performance harness for the exact latent-lexicon workflow."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import os
import platform
import pstats
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

from sktlm.latent.training import S1M1_MODEL, S1M2_MODEL, TrainingConfig, run_training


LEGACY_BENCHMARK_LISTS = {
    "smoke": Path("configs/benchmarks/latent_smoke_documents.txt"),
    "medium": Path("configs/benchmarks/latent_medium_documents.txt"),
}
S1M2_BENCHMARK_CONFIG = Path("configs/benchmarks/s1m2_continuous_runtime.json")


@dataclass(frozen=True, slots=True)
class BenchmarkSpec:
    model: str
    manifest: Path
    script: str
    condition: str
    document_list: Path
    workload: str
    max_lines_per_document: int | None = None
    manifest_sha256: str | None = None
    document_list_sha256: str | None = None

    def payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["manifest"] = self.manifest.as_posix()
        payload["document_list"] = self.document_list.as_posix()
        return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checked_file(repo_root: Path, path: Path, expected_sha256: str) -> None:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    actual = _sha256(resolved)
    if actual != expected_sha256:
        raise RuntimeError(
            f"Benchmark input SHA-256 mismatch for {path}: "
            f"expected {expected_sha256}, got {actual}"
        )


def _load_benchmark_spec(benchmark: str, repo_root: Path) -> BenchmarkSpec:
    if benchmark in LEGACY_BENCHMARK_LISTS:
        return BenchmarkSpec(
            model=S1M1_MODEL,
            manifest=Path("data/manifests/representations.csv"),
            script="iast",
            condition="surface_word",
            document_list=LEGACY_BENCHMARK_LISTS[benchmark],
            workload=benchmark,
        )

    contract_path = (
        S1M2_BENCHMARK_CONFIG
        if S1M2_BENCHMARK_CONFIG.is_absolute()
        else repo_root / S1M2_BENCHMARK_CONFIG
    )
    raw = json.loads(contract_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "sktlm-s1m2-continuous-runtime/v1":
        raise ValueError("Unsupported S1M2 continuous benchmark schema.")
    try:
        item = raw["benchmarks"][benchmark]
    except KeyError as error:
        raise ValueError(f"unknown benchmark: {benchmark}") from error
    spec = BenchmarkSpec(
        model=str(item["model"]),
        manifest=Path(item["manifest"]),
        manifest_sha256=str(item["manifest_sha256"]),
        script=str(item["script"]),
        condition=str(item["condition"]),
        document_list=Path(item["document_list"]),
        document_list_sha256=str(item["document_list_sha256"]),
        max_lines_per_document=(
            None
            if item.get("max_lines_per_document") is None
            else int(item["max_lines_per_document"])
        ),
        workload=str(item["workload"]),
    )
    if spec.model != S1M2_MODEL or spec.condition != "continuous":
        raise ValueError("S1M2 continuous benchmarks require the exact S1M2 model.")
    if spec.script not in {"iast_m0_prime", "devanagari"}:
        raise ValueError("Invalid S1M2 continuous frontend in benchmark contract.")
    if spec.max_lines_per_document is not None and spec.max_lines_per_document < 1:
        raise ValueError("max_lines_per_document must be positive when present.")
    assert spec.manifest_sha256 is not None
    assert spec.document_list_sha256 is not None
    _checked_file(repo_root, spec.manifest, spec.manifest_sha256)
    _checked_file(repo_root, spec.document_list, spec.document_list_sha256)
    return spec


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
    workers: int,
    profile: bool,
    repo_root: Path,
) -> dict[str, Any]:
    spec = _load_benchmark_spec(benchmark, repo_root)
    config = TrainingConfig(
        manifest=spec.manifest,
        document_list=spec.document_list,
        output_root=output_root,
        run_id=run_id,
        model=spec.model,
        script=spec.script,
        condition=spec.condition,
        passes=passes,
        workers=workers,
        max_lines_per_document=spec.max_lines_per_document,
        equivalence_diagnostics=spec.model == S1M1_MODEL,
    )
    profiler = cProfile.Profile() if profile else None
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    if profiler is None:
        result = run_training(config, repo_root=repo_root)
    else:
        result = profiler.runcall(run_training, config, repo_root=repo_root)
    runtime_timings = result.runtime.get('timings_seconds', {})
    cpu_seconds = (
        time.process_time()
        - cpu_start
        + float(runtime_timings.get('training_worker_cpu', 0.0))
        + float(runtime_timings.get('inspection_worker_cpu', 0.0))
    )
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
        "benchmark_contract": spec.payload(),
        "document_list": spec.document_list.as_posix(),
        "manifest": spec.manifest.as_posix(),
        "model": spec.model,
        "script": spec.script,
        "condition": spec.condition,
        "workload": spec.workload,
        "max_lines_per_document": spec.max_lines_per_document,
        "passes": passes,
        "workers": workers,
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
    parser.add_argument(
        "--benchmark",
        required=True,
        help="legacy smoke/medium or an ID in the S1M2 runtime contract",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/latent_benchmarks"),
    )
    parser.add_argument("--passes", type=int, default=1)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument("--profile", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    metrics = run_benchmark(
        benchmark=args.benchmark,
        run_id=args.run_id,
        output_root=args.output_root,
        passes=args.passes,
        workers=args.workers,
        profile=args.profile,
        repo_root=Path(".").resolve(),
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
