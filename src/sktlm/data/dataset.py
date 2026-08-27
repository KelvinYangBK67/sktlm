"""Canonical manifest loading with text-level splits fixed before tokenization."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterable, Sequence
from pathlib import Path

from sktlm.data.representations.canonical import CanonicalSegment, RepresentedSegment
from sktlm.data.representations.script import RepresentationConfig, derive_representations
from sktlm.data.splits import DEFAULT_SPLIT_SEED, assign_split, make_document_id


def file_sha256(path: Path) -> str:
    """Return a streaming SHA-256 fingerprint for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(path: Path) -> list[dict[str, str]]:
    """Read manifest rows without imposing a newer schema on legacy files."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _source_relative_path(row: dict[str, str]) -> str:
    explicit = row.get("relative_path") or row.get("relative")
    if explicit:
        return explicit.replace("\\", "/")
    path = row["path"].replace("\\", "/")
    for marker in ("/gretil_devanagari/", "/gretil_raw/", "/ambuda-text/"):
        if marker in f"/{path}":
            return f"/{path}".split(marker, 1)[1]
    return Path(path).name


def _resolve_path(path_text: str, manifest_path: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute() or path.exists():
        return path
    candidate = manifest_path.parent / path
    return candidate if candidate.exists() else path


def canonical_source_for_row(row: dict[str, str], manifest_path: Path) -> tuple[Path, str]:
    """Resolve the least manipulated available text and its current script."""
    if row.get("canonical_path"):
        return _resolve_path(row["canonical_path"], manifest_path), row.get("canonical_script", "devanagari")

    processed_path = _resolve_path(row["path"], manifest_path)
    explicit_script = row.get("canonical_script")
    if explicit_script:
        return processed_path, explicit_script

    if row.get("source") == "gretil":
        raw_text = str(processed_path).replace("gretil_devanagari", "gretil_raw")
        raw_path = Path(raw_text)
        if raw_path.exists():
            return raw_path, "iast"
    return processed_path, "devanagari"


def load_canonical_segments(
    manifest_path: Path,
    splits: set[str] | None = None,
    *,
    split_seed: str = DEFAULT_SPLIT_SEED,
    max_segments: int | None = None,
) -> list[CanonicalSegment]:
    """Load stable non-empty physical-line segments from selected document splits."""
    segments: list[CanonicalSegment] = []
    for row in read_manifest(manifest_path):
        relative = _source_relative_path(row)
        document_id = row.get("document_id") or make_document_id(row["source"], relative)
        split = row.get("split") or assign_split(document_id, seed=split_seed)
        if splits is not None and split not in splits:
            continue
        source_path, canonical_script = canonical_source_for_row(row, manifest_path)
        text = source_path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            segments.append(
                CanonicalSegment(
                    document_id=document_id,
                    segment_id=f"{document_id}:l{line_number:08d}",
                    split=split,
                    canonical_text=line,
                    source=row["source"],
                    layer=row["layer"],
                    canonical_script=canonical_script,
                )
            )
            if max_segments is not None and len(segments) >= max_segments:
                return segments
    return segments


def represent_segments(
    segments: Sequence[CanonicalSegment],
    config: RepresentationConfig,
) -> list[RepresentedSegment]:
    """Transform all selected identities without changing membership or order."""
    return derive_representations(list(segments), config)


def segment_id_hash(segments: Iterable[CanonicalSegment | RepresentedSegment]) -> str:
    """Fingerprint ordered segment identity and split membership."""
    digest = hashlib.sha256()
    for segment in segments:
        digest.update(f"{segment.split}\t{segment.segment_id}\n".encode("utf-8"))
    return digest.hexdigest()


def segment_ids_by_split(
    segments: Iterable[CanonicalSegment | RepresentedSegment],
) -> dict[str, tuple[str, ...]]:
    """Return ordered segment IDs grouped by their pre-tokenization split."""
    grouped: dict[str, list[str]] = {}
    for segment in segments:
        grouped.setdefault(segment.split, []).append(segment.segment_id)
    return {split: tuple(ids) for split, ids in grouped.items()}


def assert_same_segment_ids(
    left: Sequence[CanonicalSegment | RepresentedSegment],
    right: Sequence[CanonicalSegment | RepresentedSegment],
) -> None:
    """Fail explicitly if two conditions do not contain identical text identities."""
    if segment_ids_by_split(left) != segment_ids_by_split(right):
        raise ValueError("representation conditions do not contain the same segment IDs by split")
