"""Deterministic experiment IDs, fingerprints, and provenance artifacts."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from sktlm.data.dataset import file_sha256, segment_id_hash
from sktlm.data.representations.canonical import CanonicalSegment


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def make_run_id(config: dict[str, Any]) -> str:
    """Return an explicit run_id or a deterministic config-derived ID."""
    return str(config.get("run_id") or f"run_{payload_sha256(config)[:12]}")


def current_git_commit(repo_root: Path) -> str:
    """Return HEAD or an explicit unavailable marker; never fabricate provenance."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or "unavailable: empty git rev-parse output"
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"unavailable: {type(exc).__name__}"


def build_data_fingerprint(
    manifest_path: Path,
    segments: list[CanonicalSegment],
    representation: dict[str, str],
    seed: int,
) -> dict[str, Any]:
    """Fingerprint manifest bytes, selected IDs/splits, and representation config."""
    split_counts = Counter(segment.split for segment in segments)
    payload: dict[str, Any] = {
        "manifest_path": str(manifest_path.as_posix()),
        "manifest_sha256": file_sha256(manifest_path),
        "segment_id_split_sha256": segment_id_hash(segments),
        "segment_count": len(segments),
        "split_counts": dict(sorted(split_counts.items())),
        "representation": representation,
        "seed": seed,
    }
    payload["fingerprint_sha256"] = payload_sha256(payload)
    return payload


def build_tokenizer_fingerprint(config: dict[str, Any], runtime_payload: dict[str, Any]) -> dict[str, Any]:
    payload = {"config": config, "runtime": runtime_payload}
    payload["fingerprint_sha256"] = payload_sha256(payload)
    return payload


def write_run_artifacts(
    output_root: Path,
    config: dict[str, Any],
    metrics: dict[str, Any],
    data_fingerprint: dict[str, Any],
    tokenizer_fingerprint: dict[str, Any],
    predictions: list[dict[str, Any]],
    logs: list[str],
    repo_root: Path,
) -> Path:
    """Write the required provenance bundle for one deterministic run."""
    run_id = make_run_id(config)
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "data_fingerprint.json").write_text(
        json.dumps(data_fingerprint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "tokenizer_fingerprint.json").write_text(
        json.dumps(tokenizer_fingerprint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "git_commit.txt").write_text(current_git_commit(repo_root) + "\n", encoding="utf-8")
    with (run_dir / "predictions.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction, ensure_ascii=False, sort_keys=True) + "\n")
    (run_dir / "logs.txt").write_text("\n".join(logs) + "\n", encoding="utf-8")
    return run_dir
