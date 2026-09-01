from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sktlm.review.packet import (
    REQUIRED_ROLES,
    ReviewPacketError,
    build_packet,
    verify_packet,
    verify_raw_review_metadata,
)

COMMIT = "a" * 40
REPOSITORY_COMMIT = "b" * 40


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _spec(repo: Path, *, reverse: bool = False) -> Path:
    files = []
    for role in sorted(REQUIRED_ROLES):
        source = repo / "sources" / f"{role}.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"source for {role}\n", encoding="utf-8")
        files.append({
            "role": role,
            "path": source.relative_to(repo).as_posix(),
            "packet_path": f"files/{role}.txt",
        })
    if reverse:
        files.reverse()
    payload = {
        "schema_version": "sktlm-review-packet-spec/v1",
        "milestone_id": "s1m1",
        "scientific_commit": COMMIT,
        "files": files,
    }
    path = repo / ("spec-reverse.json" if reverse else "spec.json")
    _json(path, payload)
    return path


def _build(repo: Path, spec: Path, output: Path) -> dict[str, object]:
    return build_packet(
        spec,
        output,
        repo_root=repo,
        repository_commit=REPOSITORY_COMMIT,
        require_clean=False,
        require_tracked=False,
    )


def test_packet_hash_and_manifest_order_are_stable(tmp_path: Path) -> None:
    first_spec = _spec(tmp_path)
    first = _build(tmp_path, first_spec, tmp_path / "packet-a")
    reverse_spec = _spec(tmp_path, reverse=True)
    second = _build(tmp_path, reverse_spec, tmp_path / "packet-b")
    assert first["packet_sha256"] == second["packet_sha256"]
    assert first["files"] == sorted(
        first["files"], key=lambda row: (row["role"], row["packet_path"], row["source_path"])
    )
    assert verify_packet(tmp_path / "packet-a", repo_root=tmp_path)["valid"] is True


def test_modified_prompt_and_method_change_packet_identity(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    first = _build(tmp_path, spec, tmp_path / "packet-a")
    prompt = tmp_path / "sources" / "reviewer_prompt.txt"
    prompt.write_text("changed prompt\n", encoding="utf-8")
    second = _build(tmp_path, spec, tmp_path / "packet-b")
    assert first["reviewer_prompt_sha256"] != second["reviewer_prompt_sha256"]
    assert first["packet_sha256"] != second["packet_sha256"]
    method = tmp_path / "sources" / "reviewer_method.txt"
    method.write_text("changed method\n", encoding="utf-8")
    third = _build(tmp_path, spec, tmp_path / "packet-c")
    assert second["reviewer_method_sha256"] != third["reviewer_method_sha256"]
    assert second["packet_sha256"] != third["packet_sha256"]


def test_missing_source_and_existing_output_fail_closed(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    (tmp_path / "sources" / "limitations.txt").unlink()
    with pytest.raises(ReviewPacketError, match="source file is missing"):
        _build(tmp_path, spec, tmp_path / "packet")
    _spec(tmp_path)
    (tmp_path / "packet").mkdir()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        _build(tmp_path, spec, tmp_path / "packet")


def test_windows_style_relative_path_escapes_fail_closed(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    payload = json.loads(spec.read_text(encoding="utf-8"))
    payload["files"][0]["packet_path"] = "..\\escaped.txt"
    _json(spec, payload)
    with pytest.raises(ReviewPacketError, match="unsafe packet_path"):
        _build(tmp_path, spec, tmp_path / "packet")

    spec = _spec(tmp_path)
    manifest = _build(tmp_path, spec, tmp_path / "packet")
    reviewer = tmp_path / "reviews" / "reviewer_01"
    reviewer.mkdir(parents=True)
    metadata = {
        "schema_version": "sktlm-raw-review-metadata/v1",
        "reviewer_id": "reviewer_01",
        "packet_sha256": manifest["packet_sha256"],
        "reviewer_prompt_sha256": manifest["reviewer_prompt_sha256"],
        "reviewer_method_sha256": manifest["reviewer_method_sha256"],
        "raw_review_path": "..\\escaped.md",
        "raw_response_sha256": "0" * 64,
    }
    metadata_path = reviewer / "metadata.json"
    _json(metadata_path, metadata)
    result = verify_raw_review_metadata(metadata_path, tmp_path / "packet")
    assert result["valid"] is False
    assert any("unsafe raw_review_path" in error for error in result["errors"])

def test_missing_or_changed_packet_file_fails_verification(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    _build(tmp_path, spec, tmp_path / "packet")
    prompt_copy = tmp_path / "packet" / "files" / "reviewer_prompt.txt"
    prompt_copy.write_text("tampered\n", encoding="utf-8")
    result = verify_packet(tmp_path / "packet")
    assert result["valid"] is False
    assert any("identity mismatch" in error for error in result["errors"])
    prompt_copy.unlink()
    result = verify_packet(tmp_path / "packet")
    assert result["valid"] is False
    assert any("file is missing" in error for error in result["errors"])


def test_changed_source_is_detected_against_frozen_packet(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    _build(tmp_path, spec, tmp_path / "packet")
    (tmp_path / "sources" / "reviewer_prompt.txt").write_text(
        "changed after freeze\n", encoding="utf-8"
    )
    result = verify_packet(tmp_path / "packet", repo_root=tmp_path)
    assert result["valid"] is False
    assert any("source changed after freeze" in error for error in result["errors"])


def test_raw_review_metadata_must_reference_exact_packet(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    manifest = _build(tmp_path, spec, tmp_path / "packet")
    reviewer = tmp_path / "reviews" / "reviewer_01"
    reviewer.mkdir(parents=True)
    raw = reviewer / "raw_review.md"
    raw.write_text("unaltered raw response\n", encoding="utf-8")
    metadata = {
        "schema_version": "sktlm-raw-review-metadata/v1",
        "reviewer_id": "reviewer_01",
        "packet_sha256": manifest["packet_sha256"],
        "reviewer_prompt_sha256": manifest["reviewer_prompt_sha256"],
        "reviewer_method_sha256": manifest["reviewer_method_sha256"],
        "raw_review_path": "raw_review.md",
        "raw_response_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "model": "unknown",
        "provider": "unknown",
        "model_version": "unknown",
        "timestamp": "unknown",
    }
    metadata_path = reviewer / "metadata.json"
    _json(metadata_path, metadata)
    assert verify_raw_review_metadata(metadata_path, tmp_path / "packet")["valid"] is True
    metadata["packet_sha256"] = "0" * 64
    _json(metadata_path, metadata)
    result = verify_raw_review_metadata(metadata_path, tmp_path / "packet")
    assert result["valid"] is False
    assert any("packet_sha256 does not match" in error for error in result["errors"])