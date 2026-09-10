#!/usr/bin/env python3
"""
Bounded local probe for S1M2 overflow cases.

For a small set of known Full-corpus offenders:
1. reproduce the production raw count at ceiling=512;
2. rebuild the same segment with a diagnostic ceiling (default 4096);
3. retain all internal nodes;
4. stream through every valid LazyLexicalSpan;
5. record candidate-build time, span-enumeration time, span count,
   node count, theoretical node-pair count, and process peak RSS.

No inference.
No EM.
No learner/state access.
No scientific artifact mutation.

Each case runs in a fresh subprocess so RSS/timing are isolated.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.lazy_candidates import build_lazy_candidate_graph
from sktlm.latent.training import (
    S1M2_MODEL,
    TrainingConfig,
    load_documents,
)


DEFAULT_MANIFEST = Path("data/manifests/representations.csv")
DEFAULT_OFFENDERS = Path(
    "artifacts/s1m2_candidate_pressure/"
    "full_m0_devanagari_continuous/offenders.tsv"
)
DEFAULT_OUTPUT = Path(
    "artifacts/s1m2_candidate_pressure/overflow_span_probe"
)

# Approximate pressure points requested for the local probe.
TARGET_RAWS = (520, 750, 1000, 1400, 1841, 2484)


def resolve(root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (root / path).resolve()


def _memory_bytes_psutil() -> tuple[int | None, int | None]:
    """
    Return (current_rss, peak_rss) using psutil where available.

    On Windows, psutil's memory_info() commonly exposes peak_wset.
    If peak_wset is unavailable, current RSS is still useful as a fallback.
    """
    try:
        import psutil  # type: ignore
    except ImportError:
        return None, None

    try:
        info = psutil.Process(os.getpid()).memory_info()
        current = int(info.rss)
        peak_value = getattr(info, "peak_wset", None)
        peak = int(peak_value) if peak_value is not None else current
        return current, peak
    except (OSError, AttributeError, ValueError):
        return None, None


def _memory_bytes_windows_api() -> tuple[int | None, int | None]:
    """
    Windows fallback using GetProcessMemoryInfo.

    Returns:
        (WorkingSetSize, PeakWorkingSetSize)
    """
    if os.name != "nt":
        return None, None

    try:
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
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
                ("PrivateUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)

        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []

        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
            wintypes.DWORD,
        ]

        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)

        process = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(
            process,
            ctypes.byref(counters),
            counters.cb,
        )
        if not ok:
            return None, None

        return (
            int(counters.WorkingSetSize),
            int(counters.PeakWorkingSetSize),
        )
    except (OSError, AttributeError, ValueError):
        return None, None


def _memory_bytes_procfs() -> tuple[int | None, int | None]:
    """Linux / WSL fallback using /proc/self/status."""
    status = Path("/proc/self/status")
    if not status.is_file():
        return None, None

    current = None
    peak = None

    try:
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                current = int(line.split()[1]) * 1024
            elif line.startswith("VmHWM:"):
                peak = int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None, None

    return current, peak


def memory_bytes() -> tuple[int | None, int | None]:
    """
    Return (current_rss, peak_rss) where available.

    Priority:
    1. psutil
    2. Windows GetProcessMemoryInfo
    3. Linux/WSL /proc/self/status
    """
    current, peak = _memory_bytes_psutil()
    if current is not None or peak is not None:
        return current, peak

    if os.name == "nt":
        current, peak = _memory_bytes_windows_api()
        if current is not None or peak is not None:
            return current, peak

    return _memory_bytes_procfs()


def mib(value: int | None) -> float | None:
    if value is None:
        return None
    return value / (1024 * 1024)


def format_mib(value: float | None) -> str:
    if value is None:
        return "unavailable"
    return f"{value:.1f} MiB"


def read_offenders(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    if not rows:
        raise RuntimeError(f"No offender rows found in {path}")

    return rows


def select_cases(
    rows: list[dict[str, str]],
    targets: tuple[int, ...],
) -> list[dict[str, Any]]:
    """
    Pick the closest unique offender to each target raw count.
    """
    selected: list[dict[str, Any]] = []
    used: set[tuple[str, int, int]] = set()

    for target in targets:
        candidates = []

        for row in rows:
            key = (
                row["relative_path"],
                int(row["line_number"]),
                int(row["segment_index"]),
            )
            if key in used:
                continue

            raw = int(row["segment_raw_internal_matches"])

            candidates.append(
                (
                    abs(raw - target),
                    -raw,
                    row["relative_path"],
                    int(row["line_number"]),
                    int(row["segment_index"]),
                    row,
                )
            )

        if not candidates:
            break

        candidates.sort(key=lambda item: item[:-1])
        row = candidates[0][-1]

        key = (
            row["relative_path"],
            int(row["line_number"]),
            int(row["segment_index"]),
        )
        used.add(key)

        selected.append(
            {
                "target_raw": target,
                "relative_path": row["relative_path"],
                "line_number": int(row["line_number"]),
                "segment_index": int(row["segment_index"]),
                "expected_raw": int(
                    row["segment_raw_internal_matches"]
                ),
                "expected_phonemes": int(row["phonemes"]),
            }
        )

    return selected


def load_exact_segment(
    *,
    repo_root: Path,
    manifest: Path,
    relative_path: str,
    line_number: int,
    segment_index: int,
    script: str,
    condition: str,
    max_segment_tokens: int,
):
    documents = load_documents(
        manifest,
        repo_root=repo_root,
        max_documents=None,
        document_list=None,
        script=script,
        condition=condition,
    )

    by_path = {
        document.relative_path: document
        for document in documents
    }

    if relative_path not in by_path:
        raise RuntimeError(
            f"Document absent from production selection: {relative_path}"
        )

    document = by_path[relative_path]

    target_line = None
    with document.path.open("r", encoding="utf-8") as handle:
        for current_line, line in enumerate(handle, 1):
            if current_line == line_number:
                target_line = line.rstrip("\r\n")
                break

    if target_line is None:
        raise RuntimeError(
            f"Missing line {line_number} in {relative_path}"
        )

    segments = list(
        iter_observed_segments(
            target_line,
            max_tokens=max_segment_tokens,
            script=script,
        )
    )

    if segment_index >= len(segments):
        raise RuntimeError(
            f"segment_index={segment_index} out of range; "
            f"line has {len(segments)} segments"
        )

    return segments[segment_index]


def graph_stats(graph) -> dict[str, Any]:
    lattices = [
        factor.lattice
        for factor in graph.factors
        if factor.lattice is not None
    ]

    raw = sum(
        lattice.raw_internal_matches
        for lattice in lattices
    )
    retained = sum(
        lattice.retained_internal_matches
        for lattice in lattices
    )
    nodes = sum(
        len(lattice.nodes)
        for lattice in lattices
    )

    pair_upper_bound = sum(
        len(lattice.nodes) * (len(lattice.nodes) - 1) // 2
        for lattice in lattices
    )

    return {
        "lattices": len(lattices),
        "raw_internal_matches": raw,
        "retained_internal_matches": retained,
        "nodes": nodes,
        "max_nodes_one_lattice": max(
            (len(lattice.nodes) for lattice in lattices),
            default=0,
        ),
        "theoretical_node_pairs": pair_upper_bound,
        "overflowed_tokens": graph.overflowed_tokens,
    }


def worker(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    manifest = resolve(repo_root, args.manifest)

    segment = load_exact_segment(
        repo_root=repo_root,
        manifest=manifest,
        relative_path=args.relative_path,
        line_number=args.line_number,
        segment_index=args.segment_index,
        script=args.script,
        condition=args.condition,
        max_segment_tokens=args.max_segment_tokens,
    )

    grammar = StructuredSandhiGrammar.from_default_inventory()

    baseline_current, baseline_peak = memory_bytes()

    # First reproduce the frozen production 512 result.
    config_512 = TrainingConfig(
        manifest=manifest,
        model=S1M2_MODEL,
        script=args.script,
        condition=args.condition,
        passes=1,
        workers=1,
        max_internal_matches=512,
        max_segment_tokens=args.max_segment_tokens,
    )

    started = time.perf_counter()
    graph_512 = build_lazy_candidate_graph(
        segment,
        grammar,
        config_512.candidate_config,
    )
    build_512_seconds = time.perf_counter() - started
    stats_512 = graph_stats(graph_512)

    if stats_512["raw_internal_matches"] != args.expected_raw:
        raise RuntimeError(
            "Production reproduction failed: "
            f"expected raw={args.expected_raw}, "
            f"got {stats_512['raw_internal_matches']}"
        )

    # Rebuild with diagnostic exact-retention ceiling.
    config_probe = TrainingConfig(
        manifest=manifest,
        model=S1M2_MODEL,
        script=args.script,
        condition=args.condition,
        passes=1,
        workers=1,
        max_internal_matches=args.probe_ceiling,
        max_segment_tokens=args.max_segment_tokens,
    )

    started = time.perf_counter()
    graph_probe = build_lazy_candidate_graph(
        segment,
        grammar,
        config_probe.candidate_config,
    )
    build_probe_seconds = time.perf_counter() - started
    stats_probe = graph_stats(graph_probe)

    if stats_probe["raw_internal_matches"] != args.expected_raw:
        raise RuntimeError(
            "Probe changed raw candidate membership: "
            f"expected={args.expected_raw}, "
            f"got={stats_probe['raw_internal_matches']}"
        )

    if stats_probe["overflowed_tokens"]:
        raise RuntimeError(
            f"probe ceiling {args.probe_ceiling} still overflows"
        )

    # Count every actual production LazyLexicalSpan.
    # This intentionally streams and retains none of the spans.
    started = time.perf_counter()

    valid_spans = 0
    per_lattice_spans: list[int] = []

    for factor in graph_probe.factors:
        lattice = factor.lattice
        if lattice is None:
            continue

        count = 0
        for _span in lattice.iter_spans():
            count += 1

        per_lattice_spans.append(count)
        valid_spans += count

    span_seconds = time.perf_counter() - started

    current_rss, peak_rss = memory_bytes()

    phonemes = sum(
        len(token.phonemes)
        for token in segment.tokens
    )

    peak_minus_baseline_current = None
    if (
        peak_rss is not None
        and baseline_current is not None
        and peak_rss >= baseline_current
    ):
        peak_minus_baseline_current = peak_rss - baseline_current

    result = {
        "status": "PASS",
        "relative_path": args.relative_path,
        "line_number": args.line_number,
        "segment_index": args.segment_index,
        "expected_raw": args.expected_raw,
        "characters": len(segment.written),
        "tokens": len(segment.tokens),
        "phonemes": phonemes,
        "production_512": {
            **stats_512,
            "build_seconds": build_512_seconds,
        },
        "probe": {
            "ceiling": args.probe_ceiling,
            **stats_probe,
            "build_seconds": build_probe_seconds,
            "valid_lexical_spans": valid_spans,
            "valid_spans_per_lattice": per_lattice_spans,
            "span_enumeration_seconds": span_seconds,
            "spans_per_second": (
                valid_spans / span_seconds
                if span_seconds > 0
                else None
            ),
        },
        "memory": {
            "baseline_current_rss_mib": mib(baseline_current),
            "baseline_peak_rss_mib": mib(baseline_peak),
            "final_current_rss_mib": mib(current_rss),
            "process_peak_rss_mib": mib(peak_rss),
            "peak_minus_baseline_current_mib": mib(
                peak_minus_baseline_current
            ),
        },
    }

    # Worker stdout must contain JSON only, because the parent process parses it.
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    parser.add_argument(
        "--offenders",
        type=Path,
        default=DEFAULT_OFFENDERS,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--script",
        default="devanagari",
    )
    parser.add_argument(
        "--condition",
        default="continuous",
    )
    parser.add_argument(
        "--max-segment-tokens",
        type=int,
        default=128,
    )
    parser.add_argument(
        "--probe-ceiling",
        type=int,
        default=4096,
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Hard wall-clock timeout per isolated case.",
    )

    # Internal worker mode.
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--relative-path")
    parser.add_argument("--line-number", type=int)
    parser.add_argument("--segment-index", type=int)
    parser.add_argument("--expected-raw", type=int)

    args = parser.parse_args()

    if args.worker:
        required = {
            "--relative-path": args.relative_path,
            "--line-number": args.line_number,
            "--segment-index": args.segment_index,
            "--expected-raw": args.expected_raw,
        }
        missing = [
            name
            for name, value in required.items()
            if value is None
        ]
        if missing:
            raise ValueError(
                "Worker mode is missing required arguments: "
                + ", ".join(missing)
            )
        return worker(args)

    if args.probe_ceiling < 1:
        raise ValueError("--probe-ceiling must be >= 1")
    if args.timeout_seconds < 1:
        raise ValueError("--timeout-seconds must be >= 1")

    repo_root = args.repo_root.resolve()
    offenders = resolve(repo_root, args.offenders)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_offenders(offenders)
    cases = select_cases(rows, TARGET_RAWS)

    print("Selected cases:")
    for case in cases:
        print(
            f"  target~{case['target_raw']:4d} "
            f"raw={case['expected_raw']:4d} "
            f"{case['relative_path']}:"
            f"{case['line_number']}:"
            f"{case['segment_index']}"
        )

    print()

    results: list[dict[str, Any]] = []

    # Ascending pressure: if a smaller case times out, stop before
    # pushing even larger cases through the same path.
    cases.sort(key=lambda case: case["expected_raw"])

    for index, case in enumerate(cases, 1):
        print(
            f"[{index}/{len(cases)}] "
            f"raw={case['expected_raw']} "
            f"{case['relative_path']}:"
            f"{case['line_number']}:"
            f"{case['segment_index']}",
            flush=True,
        )

        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--repo-root",
            str(repo_root),
            "--manifest",
            str(args.manifest),
            "--script",
            args.script,
            "--condition",
            args.condition,
            "--max-segment-tokens",
            str(args.max_segment_tokens),
            "--probe-ceiling",
            str(args.probe_ceiling),
            "--relative-path",
            case["relative_path"],
            "--line-number",
            str(case["line_number"]),
            "--segment-index",
            str(case["segment_index"]),
            "--expected-raw",
            str(case["expected_raw"]),
        ]

        try:
            completed = subprocess.run(
                command,
                cwd=repo_root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=args.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            result = {
                **case,
                "status": "TIMEOUT",
                "timeout_seconds": args.timeout_seconds,
            }
            results.append(result)

            print(
                f"  TIMEOUT after {args.timeout_seconds}s; "
                "stopping before larger cases."
            )
            break

        if completed.returncode != 0:
            result = {
                **case,
                "status": "ERROR",
                "stderr": completed.stderr.strip(),
                "stdout": completed.stdout.strip(),
            }
            results.append(result)

            print("  ERROR")
            if completed.stderr.strip():
                print(completed.stderr.strip())
            if completed.stdout.strip():
                print(completed.stdout.strip())
            break

        stdout = completed.stdout.strip()
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as error:
            result = {
                **case,
                "status": "ERROR",
                "stderr": completed.stderr.strip(),
                "stdout": stdout,
                "parse_error": str(error),
            }
            results.append(result)

            print("  ERROR: worker output was not valid JSON")
            if stdout:
                print(stdout)
            break

        result["target_raw"] = case["target_raw"]
        results.append(result)

        probe = result["probe"]
        memory = result["memory"]

        peak_rss_text = format_mib(
            memory.get("process_peak_rss_mib")
        )

        print(
            "  PASS "
            f"nodes={probe['nodes']} "
            f"pairs<={probe['theoretical_node_pairs']} "
            f"valid_spans={probe['valid_lexical_spans']} "
            f"build={probe['build_seconds']:.3f}s "
            f"span_enum={probe['span_enumeration_seconds']:.3f}s "
            f"peak_rss={peak_rss_text}"
        )

    summary = {
        "schema_version": "sktlm-s1m2-overflow-span-probe/v1",
        "probe_ceiling": args.probe_ceiling,
        "timeout_seconds_per_case": args.timeout_seconds,
        "targets": list(TARGET_RAWS),
        "results": results,
    }

    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    fields = [
        "target_raw",
        "expected_raw",
        "status",
        "relative_path",
        "line_number",
        "segment_index",
        "phonemes",
        "nodes",
        "theoretical_node_pairs",
        "valid_lexical_spans",
        "build_seconds",
        "span_enumeration_seconds",
        "process_peak_rss_mib",
        "peak_minus_baseline_current_mib",
    ]

    results_path = output_dir / "results.tsv"
    with results_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()

        for result in results:
            probe = result.get("probe", {})
            memory = result.get("memory", {})

            writer.writerow(
                {
                    "target_raw": result.get("target_raw"),
                    "expected_raw": result.get("expected_raw"),
                    "status": result.get("status"),
                    "relative_path": result.get("relative_path"),
                    "line_number": result.get("line_number"),
                    "segment_index": result.get("segment_index"),
                    "phonemes": result.get("phonemes"),
                    "nodes": probe.get("nodes"),
                    "theoretical_node_pairs": probe.get(
                        "theoretical_node_pairs"
                    ),
                    "valid_lexical_spans": probe.get(
                        "valid_lexical_spans"
                    ),
                    "build_seconds": probe.get("build_seconds"),
                    "span_enumeration_seconds": probe.get(
                        "span_enumeration_seconds"
                    ),
                    "process_peak_rss_mib": memory.get(
                        "process_peak_rss_mib"
                    ),
                    "peak_minus_baseline_current_mib": memory.get(
                        "peak_minus_baseline_current_mib"
                    ),
                }
            )

    print()
    print(f"Results: {summary_path}")
    print(f"Table:   {results_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
