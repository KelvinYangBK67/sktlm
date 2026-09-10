"""Validated execution-only bundle plans for S1M2 training."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


PLANNER_IMPLEMENTATION = "sktlm-s1m2-execution-bundle-planner/v1"
SCAN_SCHEMA = "sktlm-s1m2-execution-bundle-scan/v1"
PLAN_SCHEMA = "sktlm-s1m2-execution-bundle-plan/v1"
BUNDLE_SCHEMA = "sktlm-s1m2-execution-bundle/v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ExecutionBundle:
    document_index: int
    relative_path: str
    bundle_index: int
    first_segment_ordinal: int
    last_segment_ordinal_exclusive: int
    first_line_number: int
    first_segment_index: int
    last_line_number: int
    last_segment_index: int
    segment_count: int
    phonemes: int
    pressure: int

    @property
    def key(self) -> tuple[int, int]:
        return self.document_index, self.bundle_index


@dataclass(frozen=True, slots=True)
class ExecutionBundlePlan:
    root: Path
    scan_signature_sha256: str
    plan_sha256: str
    materialization_sha256: str
    planner_implementation: str
    representation_set_sha256: str
    segment_sequence_sha256: str
    bundles: tuple[ExecutionBundle, ...]
    by_document: tuple[tuple[ExecutionBundle, ...], ...]

    def checkpoint_payload(self) -> dict[str, Any]:
        return {
            "schema_version": PLAN_SCHEMA,
            "plan_sha256": self.plan_sha256,
            "materialization_sha256": self.materialization_sha256,
            "scan_signature_sha256": self.scan_signature_sha256,
            "planner_implementation": self.planner_implementation,
            "representation_set_sha256": self.representation_set_sha256,
            "segment_sequence_sha256": self.segment_sequence_sha256,
        }

    def provenance_payload(self) -> dict[str, Any]:
        return {
            **self.checkpoint_payload(),
            "plan_root": self.root.as_posix(),
            "bundle_count": len(self.bundles),
        }


def _plan_digest(
    bundles: Sequence[ExecutionBundle],
    *,
    scan_signature: str,
    target_pressure: int,
    max_segments_per_bundle: int,
) -> str:
    digest = hashlib.sha256()
    digest.update(
        f"{scan_signature}\n{target_pressure}\n{max_segments_per_bundle}\n".encode(
            "ascii"
        )
    )
    for bundle in bundles:
        digest.update(
            (
                f"{bundle.document_index}\t{bundle.relative_path}\t"
                f"{bundle.bundle_index}\t{bundle.first_segment_ordinal}\t"
                f"{bundle.last_segment_ordinal_exclusive}\t"
                f"{bundle.segment_count}\t{bundle.phonemes}\t"
                f"{bundle.pressure}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest()


def _require_sha256(value: object, label: str) -> str:
    text = str(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"Invalid {label} in execution bundle plan.")
    return text


def load_execution_bundle_plan(
    path: Path,
    *,
    repo_root: Path,
    manifest: Path,
    documents: Sequence[Any],
    script: str,
    condition: str,
    max_segment_tokens: int,
    max_lines_per_document: int | None,
    document_list: Path | None = None,
) -> ExecutionBundlePlan:
    """Load and fail closed on a stale, incomplete, or reordered plan."""

    root = path if path.is_absolute() else repo_root / path
    root = root.resolve()
    if root.is_file() and root.name == "summary.json":
        root = root.parent
    summary_path = root / "summary.json"
    bundles_path = root / "bundles.jsonl"
    documents_path = root / "documents.tsv"
    colocated_scan = root / "scan_summary.json"
    scan_path = colocated_scan if colocated_scan.is_file() else root.parent / "scan_summary.json"
    for required in (summary_path, bundles_path, documents_path, scan_path):
        if not required.is_file():
            raise FileNotFoundError(required)

    materialization = hashlib.sha256()
    for materialized in (scan_path, summary_path, bundles_path, documents_path):
        materialization.update(materialized.name.encode("utf-8"))
        materialization.update(b"\0")
        materialization.update(materialized.read_bytes())
        materialization.update(b"\0")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    if summary.get("schema_version") != PLAN_SCHEMA:
        raise ValueError("Unsupported execution bundle plan schema.")
    if scan.get("schema_version") != SCAN_SCHEMA:
        raise ValueError("Unsupported execution bundle scan schema.")
    planner = str(
        summary.get(
            "planner_implementation",
            scan.get("planner_implementation", PLANNER_IMPLEMENTATION),
        )
    )
    if planner != PLANNER_IMPLEMENTATION:
        raise ValueError("Unsupported execution bundle planner implementation.")

    scan_signature = _require_sha256(
        summary.get("scan_signature_sha256"), "scan signature"
    )
    if scan.get("scan_signature_sha256") != scan_signature:
        raise ValueError("Execution bundle scan signature mismatch.")
    plan_sha = _require_sha256(summary.get("plan_sha256"), "plan SHA-256")
    representation_sha = _require_sha256(
        scan.get("representation_set_sha256"), "representation identity"
    )
    segment_sha = _require_sha256(
        scan.get("segment_sequence_sha256"), "segment sequence identity"
    )
    if scan.get("manifest_sha256") != _sha256(manifest):
        raise ValueError("Execution bundle plan manifest mismatch.")
    recorded_document_list = scan.get("document_list")
    recorded_document_list_sha = scan.get("document_list_sha256")
    if document_list is None:
        if recorded_document_list is not None or recorded_document_list_sha is not None:
            raise ValueError("Execution bundle plan unexpectedly binds a document list.")
    else:
        resolved_document_list = (
            document_list if document_list.is_absolute() else repo_root / document_list
        )
        if (
            recorded_document_list != document_list.as_posix()
            or recorded_document_list_sha != _sha256(resolved_document_list)
        ):
            raise ValueError("Execution bundle plan document-list identity mismatch.")
    config_path = Path(str(scan.get("config", "")))
    if config_path and not config_path.is_absolute():
        config_path = repo_root / config_path
    if not config_path.is_file() or scan.get("config_sha256") != _sha256(config_path):
        raise ValueError("Execution bundle planner config mismatch.")
    for payload in (scan, summary):
        if payload.get("script") != script or payload.get("condition") != condition:
            raise ValueError("Execution bundle representation mismatch.")
        if int(payload.get("max_segment_tokens", -1)) != max_segment_tokens:
            raise ValueError("Execution bundle max_segment_tokens mismatch.")
        if payload.get("max_lines_per_document") != max_lines_per_document:
            raise ValueError("Execution bundle line limit mismatch.")
    if scan.get("segment_atomicity") != "complete_existing_ObservedSegment_never_split":
        raise ValueError("Execution bundle segment atomicity is not recognized.")
    if scan.get("cross_document_bundles") is not False:
        raise ValueError("Cross-document execution bundles are forbidden.")

    bundles: list[ExecutionBundle] = []
    for line_number, line in enumerate(
        bundles_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        payload = json.loads(line)
        if payload.get("schema_version") != BUNDLE_SCHEMA:
            raise ValueError(f"Invalid bundle schema at line {line_number}.")
        bundle = ExecutionBundle(
            document_index=int(payload["document_index"]),
            relative_path=str(payload["relative_path"]),
            bundle_index=int(payload["bundle_index"]),
            first_segment_ordinal=int(payload["first_segment_ordinal"]),
            last_segment_ordinal_exclusive=int(
                payload["last_segment_ordinal_exclusive"]
            ),
            first_line_number=int(payload["first_line_number"]),
            first_segment_index=int(payload["first_segment_index"]),
            last_line_number=int(payload["last_line_number"]),
            last_segment_index=int(payload["last_segment_index"]),
            segment_count=int(payload["segment_count"]),
            phonemes=int(payload["phonemes"]),
            pressure=int(payload["pressure"]),
        )
        if (
            bundle.document_index < 0
            or bundle.bundle_index < 0
            or bundle.first_segment_ordinal < 0
            or bundle.last_segment_ordinal_exclusive <= bundle.first_segment_ordinal
            or bundle.segment_count
            != bundle.last_segment_ordinal_exclusive - bundle.first_segment_ordinal
            or bundle.first_line_number < 1
            or bundle.first_segment_index < 0
            or bundle.last_line_number < bundle.first_line_number
            or bundle.last_segment_index < 0
            or bundle.phonemes < 1
            or bundle.pressure < 1
        ):
            raise ValueError(f"Invalid execution bundle values at line {line_number}.")
        bundles.append(bundle)

    if len(bundles) != int(summary.get("actual_bundle_count", -1)):
        raise ValueError("Execution bundle count mismatch.")
    if _plan_digest(
        bundles,
        scan_signature=scan_signature,
        target_pressure=int(summary["target_pressure"]),
        max_segments_per_bundle=int(summary["max_segments_per_bundle"]),
    ) != plan_sha:
        raise ValueError("Execution bundle plan SHA-256 mismatch.")

    by_document_lists: list[list[ExecutionBundle]] = [
        [] for _ in range(len(documents))
    ]
    for bundle in bundles:
        if bundle.document_index >= len(documents):
            raise ValueError("Execution bundle document index is out of range.")
        document = documents[bundle.document_index]
        if bundle.relative_path != document.relative_path:
            raise ValueError("Execution bundle document identity mismatch.")
        by_document_lists[bundle.document_index].append(bundle)

    with documents_path.open(encoding="utf-8", newline="") as handle:
        document_rows = {
            int(row["document_index"]): row
            for row in csv.DictReader(handle, delimiter="\t")
        }
    if set(document_rows) != set(range(len(documents))):
        raise ValueError("Execution bundle document coverage mismatch.")
    total_segments = 0
    for document_index, (document, document_bundles) in enumerate(
        zip(documents, by_document_lists, strict=True)
    ):
        if not document_bundles:
            raise ValueError("Execution bundle plan omits a document.")
        expected_ordinal = 0
        previous_last_identity: tuple[int, int] | None = None
        for expected_bundle_index, bundle in enumerate(document_bundles):
            if bundle.bundle_index != expected_bundle_index:
                raise ValueError("Execution bundle indices are not canonical.")
            if bundle.first_segment_ordinal != expected_ordinal:
                raise ValueError("Execution bundle segment coverage is not contiguous.")
            first_identity = (
                bundle.first_line_number,
                bundle.first_segment_index,
            )
            last_identity = (bundle.last_line_number, bundle.last_segment_index)
            if first_identity > last_identity or (
                previous_last_identity is not None
                and first_identity <= previous_last_identity
            ):
                raise ValueError("Execution bundle identities are not canonical.")
            previous_last_identity = last_identity
            expected_ordinal = bundle.last_segment_ordinal_exclusive
        row = document_rows[document_index]
        if (
            row.get("relative_path") != document.relative_path
            or int(row["segments"]) != expected_ordinal
            or int(row["bundles"]) != len(document_bundles)
        ):
            raise ValueError("Execution bundle document summary mismatch.")
        total_segments += expected_ordinal
    if total_segments != int(summary.get("total_segments", -1)):
        raise ValueError("Execution bundle total segment coverage mismatch.")

    return ExecutionBundlePlan(
        root=root,
        scan_signature_sha256=scan_signature,
        plan_sha256=plan_sha,
        materialization_sha256=materialization.hexdigest(),
        planner_implementation=planner,
        representation_set_sha256=representation_sha,
        segment_sequence_sha256=segment_sha,
        bundles=tuple(bundles),
        by_document=tuple(tuple(items) for items in by_document_lists),
    )
