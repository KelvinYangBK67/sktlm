from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "cloud" / "run_with_metrics.py"
SPEC = importlib.util.spec_from_file_location("sktlm_run_with_metrics", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
run_with_metrics = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_with_metrics
SPEC.loader.exec_module(run_with_metrics)


def test_memory_status_reports_available_and_used_swap(monkeypatch) -> None:
    payload = "\n".join(
        (
            "MemTotal:       1000 kB",
            "MemAvailable:    600 kB",
            "SwapTotal:       400 kB",
            "SwapFree:        250 kB",
        )
    )

    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: payload)

    assert run_with_metrics.memory_status() == {
        "mem_available_bytes": 600 * 1024,
        "swap_used_bytes": 150 * 1024,
    }


def test_watched_storage_reports_streaming_training_shards(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "shards" / "pass_0001" / "bundles"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "document_00000000.bundle_000000.segments.jsonl").write_bytes(
        b"segment"
    )
    (bundle_dir / "document_00000000.bundle_000000.host-support.tsv").write_bytes(
        b"host-support"
    )
    (bundle_dir / "document_00000000.bundle_000001.host-support.bin").write_bytes(
        b"packed"
    )
    (bundle_dir / "document_00000000.bundle_000000.complete.json").write_bytes(
        b"marker"
    )

    storage = run_with_metrics.watched_storage(tmp_path)

    assert storage["training_shard_bytes"] == len(b"segmenthost-supportpackedmarker")
    assert storage["training_host_support_shard_bytes"] == len(b"host-supportpacked")
    assert storage["training_bundle_marker_count"] == 1
