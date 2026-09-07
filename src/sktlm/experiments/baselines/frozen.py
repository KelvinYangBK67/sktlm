"""Bounded-memory access to the manifest-addressed frozen M₀ representations."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from sktlm.corpus.dataset import file_sha256
from sktlm.experiments.baselines.full_m0 import (
    FULL_M0_CONDITION_MANIFEST_VERSION,
    FROZEN_M0_CANONICAL_MANIFEST_SHA256,
    FROZEN_M0_REPRESENTATION_MANIFEST_SHA256,
    M0_PRIME_DERIVATION_ID,
    M0_PRIME_MANIFEST_SCHEMA,
    M0_PRIME_SCRIPT,
    M0_PRIME_SPACING,
    FullM0MatrixSettings,
    MatrixSettings,
)
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


_M0_PRIME_REQUIRED_FIELDS = {
    "schema_version",
    "derivation_id",
    "freeze_id",
    "relative_path",
    "document_id",
    "split",
    "canonical_hash",
    "script",
    "condition",
    "representation_path",
    "representation_hash",
    "byte_count",
    "source_script",
    "source_condition",
    "source_representation_path",
    "source_representation_hash",
}


def _canonical_rows_by_relative(
    canonical_manifest: Path,
) -> tuple[list[str], dict[str, dict[str, str]]]:
    rows = _read_csv(canonical_manifest)
    order = [row["freeze_input_path"].replace("\\", "/") for row in rows]
    if len(order) != len(set(order)):
        raise ValueError("canonical manifest contains duplicate freeze_input_path values")
    return order, dict(zip(order, rows))


def _load_m0_prime_files(
    settings: FullM0MatrixSettings,
    frozen: FrozenRepresentationCatalog,
    *,
    repo_root: Path,
    expected_documents: int,
    check_paths: bool,
) -> tuple[FrozenRepresentationFile, ...]:
    """Validate the pinned M0-prime downstream interface without importing latent code."""
    manifest_path = _resolve_repo_path(settings.m0_prime.manifest.as_posix(), repo_root)
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"formal M0-prime manifest is not provisioned: {manifest_path}"
        )
    actual_manifest_hash = file_sha256(manifest_path)
    if actual_manifest_hash != settings.m0_prime.manifest_sha256:
        raise ValueError(
            "M0-prime manifest SHA-256 mismatch: "
            f"expected {settings.m0_prime.manifest_sha256}, found {actual_manifest_hash}"
        )
    if settings.m0_prime.formal:
        canonical_path = _resolve_repo_path(settings.canonical_manifest.as_posix(), repo_root)
        m0_manifest_path = _resolve_repo_path(
            settings.m0_representation_manifest.as_posix(), repo_root
        )
        if file_sha256(canonical_path) != FROZEN_M0_CANONICAL_MANIFEST_SHA256:
            raise ValueError("formal M0-prime canonical-manifest identity mismatch")
        if file_sha256(m0_manifest_path) != FROZEN_M0_REPRESENTATION_MANIFEST_SHA256:
            raise ValueError("formal M0-prime source representation-manifest identity mismatch")
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    missing_fields = _M0_PRIME_REQUIRED_FIELDS - fields
    if missing_fields:
        raise ValueError(f"M0-prime manifest fields are missing: {sorted(missing_fields)}")
    if len(rows) != expected_documents:
        raise ValueError(
            f"M0-prime manifest must contain {expected_documents} documents, found {len(rows)}"
        )
    relative_order = [row["relative_path"].replace("\\", "/") for row in rows]
    if relative_order != sorted(relative_order):
        raise ValueError("M0-prime manifest document order differs from the formal derivation")
    if len(relative_order) != len(set(relative_order)):
        raise ValueError("M0-prime manifest contains duplicate documents")

    canonical_path = _resolve_repo_path(settings.canonical_manifest.as_posix(), repo_root)
    canonical_order, canonical_by_relative = _canonical_rows_by_relative(canonical_path)
    if set(relative_order) != set(canonical_order):
        missing = sorted(set(canonical_order) - set(relative_order))
        extra = sorted(set(relative_order) - set(canonical_order))
        raise ValueError(
            f"M0-prime/canonical membership mismatch: missing={missing}, extra={extra}"
        )

    source_by_relative = {
        item.relative_path: item
        for item in frozen.files_by_condition[("devanagari", "continuous")]
    }
    payload_root = _resolve_repo_path(settings.m0_prime.payload_root.as_posix(), repo_root).resolve()
    files_by_relative: dict[str, FrozenRepresentationFile] = {}
    for row in rows:
        relative = row["relative_path"].replace("\\", "/")
        canonical = canonical_by_relative[relative]
        if row["schema_version"] != M0_PRIME_MANIFEST_SCHEMA:
            raise ValueError(f"M0-prime manifest schema mismatch: {relative}")
        if row["derivation_id"] != M0_PRIME_DERIVATION_ID:
            raise ValueError(f"M0-prime derivation ID mismatch: {relative}")
        if row["freeze_id"] != settings.freeze_id:
            raise ValueError(f"M0-prime freeze identity mismatch: {relative}")
        if row["document_id"] != canonical["document_id"] or row["split"] != canonical["split"]:
            raise ValueError(f"M0-prime document ID/split mismatch: {relative}")
        if row["canonical_hash"] != canonical["canonical_hash"]:
            raise ValueError(f"M0-prime canonical hash mismatch: {relative}")
        if row["script"] != M0_PRIME_SCRIPT or row["condition"] != M0_PRIME_SPACING:
            raise ValueError(f"M0-prime representation identity mismatch: {relative}")
        if row["source_script"] != "devanagari" or row["source_condition"] != "continuous":
            raise ValueError(f"M0-prime source identity mismatch: {relative}")
        source = source_by_relative[relative]
        if row["source_representation_hash"] != source.sha256:
            raise ValueError(f"M0-prime source representation hash mismatch: {relative}")
        declared_source = _resolve_repo_path(row["source_representation_path"], repo_root).resolve()
        if declared_source != source.path.resolve():
            raise ValueError(f"M0-prime source representation path mismatch: {relative}")
        if check_paths and file_sha256(source.path) != source.sha256:
            raise ValueError(f"M0-prime frozen source file SHA-256 mismatch: {relative}")

        path = _resolve_repo_path(row["representation_path"], repo_root).resolve()
        expected_path = (payload_root / relative).resolve()
        if path != expected_path or not path.is_relative_to(payload_root):
            raise ValueError(f"M0-prime representation path escapes its payload root: {relative}")
        if check_paths:
            if not path.is_file():
                raise FileNotFoundError(path)
            if path.stat().st_size != int(row["byte_count"]):
                raise ValueError(f"M0-prime representation byte count mismatch: {relative}")
            if file_sha256(path) != row["representation_hash"]:
                raise ValueError(f"M0-prime representation SHA-256 mismatch: {relative}")
        files_by_relative[relative] = FrozenRepresentationFile(
            relative_path=relative,
            script=M0_PRIME_SCRIPT,
            spacing=M0_PRIME_SPACING,
            path=path,
            sha256=row["representation_hash"],
        )
    return tuple(files_by_relative[relative] for relative in canonical_order)


def load_full_m0_catalog(
    settings: FullM0MatrixSettings,
    *,
    repo_root: Path = Path("."),
    expected_documents: int = 240,
    check_paths: bool = True,
) -> FrozenRepresentationCatalog:
    """Expose exactly five valid M0 conditions plus corrected M0-prime continuous."""
    frozen = load_frozen_catalog(
        settings,
        repo_root=repo_root,
        expected_documents=expected_documents,
        check_paths=check_paths,
    )
    selected = {
        key: files
        for key, files in frozen.files_by_condition.items()
        if key != ("iast", "continuous")
    }
    selected[(M0_PRIME_SCRIPT, M0_PRIME_SPACING)] = _load_m0_prime_files(
        settings,
        frozen,
        repo_root=repo_root,
        expected_documents=expected_documents,
        check_paths=check_paths,
    )
    if len(selected) != 6:
        raise ValueError(f"full-M0 catalog must expose six conditions, found {len(selected)}")
    expected_files = expected_documents * 6
    actual_files = sum(len(files) for files in selected.values())
    if actual_files != expected_files:
        raise ValueError(
            f"full-M0 catalog must expose {expected_files} files, found {actual_files}"
        )
    return FrozenRepresentationCatalog(
        freeze_id=frozen.freeze_id,
        documents=frozen.documents,
        files_by_condition=selected,
    )


def load_catalog(
    settings: MatrixSettings,
    *,
    repo_root: Path = Path("."),
    expected_documents: int = 240,
    check_paths: bool = True,
) -> FrozenRepresentationCatalog:
    if settings.condition_manifest_version == FULL_M0_CONDITION_MANIFEST_VERSION:
        return load_full_m0_catalog(
            settings,
            repo_root=repo_root,
            expected_documents=expected_documents,
            check_paths=check_paths,
        )
    return load_frozen_catalog(
        settings,
        repo_root=repo_root,
        expected_documents=expected_documents,
        check_paths=check_paths,
    )
