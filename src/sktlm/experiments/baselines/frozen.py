"""Bounded-memory access to the manifest-addressed frozen M₀ representations."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from sktlm.experiments.baselines.matrix import (
    FROZEN_M0_ID,
    FORMAL_SCRIPTS,
    FORMAL_SPACINGS,
    BaselineMatrixSettings,
)
from sktlm.representations.canonical import RepresentedSegment


@dataclass(frozen=True, slots=True)
class FrozenDocument:
    relative_path: str
    document_id: str
    split: str
    source: str
    layer: str


@dataclass(frozen=True, slots=True)
class FrozenRepresentationFile:
    relative_path: str
    script: str
    spacing: str
    path: Path
    sha256: str


@dataclass(frozen=True, slots=True)
class FrozenRepresentationCatalog:
    freeze_id: str
    documents: dict[str, FrozenDocument]
    files_by_condition: dict[tuple[str, str], tuple[FrozenRepresentationFile, ...]]

    @property
    def document_count(self) -> int:
        return len(self.documents)

    @property
    def representation_file_count(self) -> int:
        return sum(len(files) for files in self.files_by_condition.values())

    def iter_segments(
        self,
        script: str,
        spacing: str,
        *,
        splits: set[str] | None = None,
        max_segments: int | None = None,
    ) -> Iterator[RepresentedSegment]:
        """Yield frozen physical-line segments while loading only one file at a time."""
        try:
            representation_files = self.files_by_condition[(script, spacing)]
        except KeyError as exc:
            raise ValueError(
                f"unknown frozen representation condition: {script}/{spacing}"
            ) from exc

        emitted = 0
        for representation in representation_files:
            document = self.documents[representation.relative_path]
            if splits is not None and document.split not in splits:
                continue
            text = representation.path.read_text(encoding="utf-8")
            for line_number, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                yield RepresentedSegment(
                    document_id=document.document_id,
                    segment_id=f"{document.document_id}:l{line_number:08d}",
                    split=document.split,
                    text=line,
                    source=document.source,
                    layer=document.layer,
                    script=script,
                    spacing=spacing,
                )
                emitted += 1
                if max_segments is not None and emitted >= max_segments:
                    return


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _resolve_repo_path(path_text: str, repo_root: Path) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else repo_root / path


def load_frozen_catalog(
    settings: BaselineMatrixSettings,
    *,
    repo_root: Path = Path("."),
    expected_documents: int = 240,
    check_paths: bool = True,
) -> FrozenRepresentationCatalog:
    """Validate manifest membership and return direct frozen representation access."""
    canonical_rows = _read_csv(_resolve_repo_path(str(settings.canonical_manifest), repo_root))
    if len(canonical_rows) != expected_documents:
        raise ValueError(
            "canonical manifest must contain "
            f"{expected_documents} documents, found {len(canonical_rows)}"
        )

    canonical_freeze_ids = {row.get("freeze_id", "") for row in canonical_rows}
    if canonical_freeze_ids != {settings.freeze_id}:
        raise ValueError(f"canonical manifest freeze IDs do not match {settings.freeze_id}")

    documents: dict[str, FrozenDocument] = {}
    canonical_order: list[str] = []
    for row in canonical_rows:
        relative_path = row["freeze_input_path"].replace("\\", "/")
        if relative_path in documents:
            raise ValueError(f"duplicate canonical document: {relative_path}")
        canonical_order.append(relative_path)
        documents[relative_path] = FrozenDocument(
            relative_path=relative_path,
            document_id=row["document_id"],
            split=row["split"],
            source=row["source"],
            layer=row["layer"],
        )

    representation_rows = _read_csv(
        _resolve_repo_path(str(settings.representation_manifest), repo_root)
    )
    representation_freeze_ids = {row.get("freeze_id", "") for row in representation_rows}
    if representation_freeze_ids != {settings.freeze_id}:
        raise ValueError(f"representation manifest freeze IDs do not match {settings.freeze_id}")

    grouped: dict[tuple[str, str], dict[str, FrozenRepresentationFile]] = {
        (script, spacing): {}
        for script in FORMAL_SCRIPTS
        for spacing in FORMAL_SPACINGS
    }
    for row in representation_rows:
        key = (row["script"], row["condition"])
        if key not in grouped:
            raise ValueError(f"non-formal representation condition in manifest: {key}")
        relative_path = row["relative_path"].replace("\\", "/")
        if relative_path in grouped[key]:
            raise ValueError(f"duplicate representation row for {key}: {relative_path}")
        path = _resolve_repo_path(row["representation_path"], repo_root)
        if check_paths and not path.is_file():
            raise FileNotFoundError(path)
        grouped[key][relative_path] = FrozenRepresentationFile(
            relative_path=relative_path,
            script=key[0],
            spacing=key[1],
            path=path,
            sha256=row["representation_hash"],
        )

    expected_membership = set(documents)
    files_by_condition: dict[tuple[str, str], tuple[FrozenRepresentationFile, ...]] = {}
    for key, rows_by_relative in grouped.items():
        membership = set(rows_by_relative)
        if membership != expected_membership:
            missing = sorted(expected_membership - membership)
            extra = sorted(membership - expected_membership)
            raise ValueError(
                f"representation membership mismatch for {key}: "
                f"missing={missing}, extra={extra}"
            )
        files_by_condition[key] = tuple(rows_by_relative[path] for path in canonical_order)

    expected_representation_files = expected_documents * len(FORMAL_SCRIPTS) * len(FORMAL_SPACINGS)
    actual_representation_files = sum(len(files) for files in files_by_condition.values())
    if actual_representation_files != expected_representation_files:
        raise ValueError(
            "formal representation file count mismatch: "
            f"expected {expected_representation_files}, found {actual_representation_files}"
        )

    return FrozenRepresentationCatalog(
        freeze_id=settings.freeze_id,
        documents=documents,
        files_by_condition=files_by_condition,
    )
