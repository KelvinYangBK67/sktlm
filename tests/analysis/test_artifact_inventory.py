from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import sktlm.analysis.artifact_inventory as inventory


def _manifest(tmp_path: Path) -> Path:
    (tmp_path / "source.tsv").write_text("key\tmass\na\t1\nb\t2\n", encoding="utf-8")
    (tmp_path / "compact.tsv").write_text("key\tmass\na\t1\nb\t2\n", encoding="utf-8")
    (tmp_path / "keep.json").write_text("{}\n", encoding="utf-8")
    payload = {
        "schema_version": inventory.SCHEMA_VERSION, "inventory_id": "tiny",
        "base_dir": ".", "retained_evidence": {
            "provenance": ["keep.json"], "config": ["keep.json"]},
        "artifacts": [
            {"path": "source.tsv", "artifact_role": "large-derived",
             "regenerability": "REGENERABLE", "replacement_compact_artifact": "compact.tsv",
             "retention_required": False,
             "consistency_checks": [{"kind": "row_count"}, {"kind": "numeric_sum", "source_column": "mass"}]},
            {"path": "keep.json", "artifact_role": "provenance",
             "regenerability": "NOT_REGENERABLE", "retention_required": True},
        ],
    }
    path = tmp_path / "inventory-input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_tiny_inventory_has_streamed_hashes_sorted_rows_and_ready_gate(tmp_path: Path) -> None:
    result = inventory.build_inventory(_manifest(tmp_path))
    assert [row["relative_path"] for row in result["artifacts"]] == ["keep.json", "source.tsv"]
    source = result["artifacts"][1]
    assert source["sha256"] == hashlib.sha256((tmp_path / "source.tsv").read_bytes()).hexdigest()
    assert source["deletion_status"] == "SAFE_TO_DELETE_REGENERABLE"
    assert result["deletion_gate"] == "READY"


def test_atomic_interruption_leaves_no_final_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = inventory.build_inventory(_manifest(tmp_path))
    output = tmp_path / "result"
    monkeypatch.setattr(inventory.os, "replace", lambda source, target: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        inventory.write_inventory(result, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".result.*"))


def test_inventory_expected_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["artifacts"][0]["expected_sha256"] = "0" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        inventory.build_inventory(manifest)
