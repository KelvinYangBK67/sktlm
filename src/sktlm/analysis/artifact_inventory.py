"""Read-only artifact inventory and evidence-based deletion readiness gate."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .six_representation_gate import GateValidationError, _read_json_object, _resolve_local_path

SCHEMA_VERSION = "sktlm-artifact-inventory-input/v1"
OUTPUT_SCHEMA_VERSION = "sktlm-artifact-inventory/v1"
DELETION_STATUSES = {"PENDING", "RETAIN", "SAFE_TO_DELETE_REGENERABLE", "NOT_SAFE"}


def stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _existing_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise GateValidationError((f"{label} is not an existing file: {path}",))


def _row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def _numeric_sum(path: Path, column: str) -> float:
    total = compensation = 0.0
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or column not in reader.fieldnames:
            raise GateValidationError((f"missing TSV column {column!r}: {path}",))
        for line_number, row in enumerate(reader, start=2):
            try:
                value = float(row[column])
            except (TypeError, ValueError) as exc:
                raise GateValidationError((f"non-numeric TSV value in {column!r} at {path}:{line_number}",)) from exc
            if not math.isfinite(value):
                raise GateValidationError((f"non-finite TSV value in {column!r} at {path}:{line_number}",))
            adjusted = value - compensation
            updated = total + adjusted
            compensation = (updated - total) - adjusted
            total = updated
    return total


def _check_consistency(source: Path, replacement: Path, checks: object) -> list[dict[str, Any]]:
    if not isinstance(checks, list):
        raise GateValidationError(("consistency_checks must be a list",))
    results: list[dict[str, Any]] = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise GateValidationError((f"consistency_checks[{index}] must be an object",))
        kind = check.get("kind")
        if kind == "row_count":
            left, right = _row_count(source), _row_count(replacement)
            passed = left == right
            detail = {"source": left, "replacement": right}
        elif kind == "numeric_sum":
            source_column = check.get("source_column")
            replacement_column = check.get("replacement_column", source_column)
            if not isinstance(source_column, str) or not isinstance(replacement_column, str):
                raise GateValidationError((f"consistency_checks[{index}] requires column names",))
            left = _numeric_sum(source, source_column)
            right = _numeric_sum(replacement, replacement_column)
            tolerance = float(check.get("absolute_tolerance", 1e-9))
            passed = math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)
            detail = {"source": left, "replacement": right, "absolute_tolerance": tolerance}
        elif kind == "json_fields":
            fields = check.get("fields")
            if not isinstance(fields, list) or not fields or not all(isinstance(value, str) for value in fields):
                raise GateValidationError((f"consistency_checks[{index}].fields is invalid",))
            source_json = _read_json_object(source, "source consistency JSON")
            replacement_json = _read_json_object(replacement, "replacement consistency JSON")
            detail = {field: {"source": source_json.get(field), "replacement": replacement_json.get(field)} for field in fields}
            passed = all(source_json.get(field) == replacement_json.get(field) for field in fields)
        else:
            raise GateValidationError((f"unknown consistency check kind: {kind!r}",))
        results.append({"kind": kind, "passed": passed, "detail": detail})
    return results


def build_inventory(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = _read_json_object(manifest_path, "artifact inventory manifest")
    errors: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    inventory_id = manifest.get("inventory_id")
    if not isinstance(inventory_id, str) or not inventory_id.strip():
        errors.append("inventory_id must be a nonempty string")
    try:
        base_dir = _resolve_local_path(manifest_path.parent, manifest.get("base_dir", "."), "base_dir")
    except GateValidationError as exc:
        errors.extend(exc.errors)
        base_dir = manifest_path.parent

    evidence = manifest.get("retained_evidence", {})
    if not isinstance(evidence, dict):
        errors.append("retained_evidence must be an object")
        evidence = {}
    evidence_payload: dict[str, list[dict[str, Any]]] = {}
    for group in ("provenance", "config", "runtime_termination"):
        raw_paths = evidence.get(group, [])
        if not isinstance(raw_paths, list):
            errors.append(f"retained_evidence.{group} must be a list")
            raw_paths = []
        rows = []
        for index, value in enumerate(raw_paths):
            try:
                path = _resolve_local_path(base_dir, value, f"retained_evidence.{group}[{index}]")
                _existing_file(path, f"retained_evidence.{group}[{index}]")
                rows.append({"relative_path": path.relative_to(base_dir).as_posix(), "size_bytes": path.stat().st_size, "sha256": stream_sha256(path)})
            except (GateValidationError, ValueError, OSError) as exc:
                errors.extend(exc.errors if isinstance(exc, GateValidationError) else [str(exc)])
        evidence_payload[group] = rows

    artifacts_raw = manifest.get("artifacts")
    if not isinstance(artifacts_raw, list):
        errors.append("artifacts must be a list")
        artifacts_raw = []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(artifacts_raw):
        label = f"artifacts[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        try:
            source = _resolve_local_path(base_dir, item.get("path"), f"{label}.path")
            _existing_file(source, f"{label}.path")
            relative = source.relative_to(base_dir).as_posix()
            if relative in seen:
                raise GateValidationError((f"duplicate artifact path: {relative}",))
            seen.add(relative)
            source_hash = stream_sha256(source)
            expected_hash = item.get("expected_sha256")
            if expected_hash is not None and expected_hash != source_hash:
                raise GateValidationError((f"{label} source SHA-256 mismatch",))
            role = item.get("artifact_role")
            regenerability = item.get("regenerability")
            retained = item.get("retention_required")
            if not isinstance(role, str) or not role:
                raise GateValidationError((f"{label}.artifact_role must be nonempty",))
            if regenerability not in {"REGENERABLE", "NOT_REGENERABLE", "UNKNOWN"}:
                raise GateValidationError((f"{label}.regenerability is invalid",))
            if not isinstance(retained, bool):
                raise GateValidationError((f"{label}.retention_required must be boolean",))
            replacement_value = item.get("replacement_compact_artifact")
            replacement = None if replacement_value is None else _resolve_local_path(base_dir, replacement_value, f"{label}.replacement_compact_artifact")
            replacement_payload = None
            checks: list[dict[str, Any]] = []
            if replacement is not None:
                _existing_file(replacement, f"{label}.replacement_compact_artifact")
                checks = _check_consistency(source, replacement, item.get("consistency_checks", []))
                replacement_payload = {"relative_path": replacement.relative_to(base_dir).as_posix(), "size_bytes": replacement.stat().st_size, "sha256": stream_sha256(replacement)}
            if retained:
                deletion_status, reasons = "RETAIN", ["retention_required=true"]
            elif regenerability == "UNKNOWN":
                deletion_status, reasons = "PENDING", ["regenerability is not yet resolved"]
            elif regenerability != "REGENERABLE":
                deletion_status, reasons = "NOT_SAFE", ["artifact is not declared REGENERABLE"]
            else:
                reasons = []
                if replacement_payload is None:
                    reasons.append("compact replacement is absent")
                if not checks:
                    reasons.append("no declared consistency check passed")
                elif not all(check["passed"] for check in checks):
                    reasons.append("replacement consistency check failed")
                if not evidence_payload["provenance"]:
                    reasons.append("provenance evidence is not retained")
                if not evidence_payload["config"]:
                    reasons.append("config evidence is not retained")
                if item.get("runtime_evidence_required", False) and not evidence_payload["runtime_termination"]:
                    reasons.append("runtime/termination evidence is not retained")
                deletion_status = "NOT_SAFE" if reasons else "SAFE_TO_DELETE_REGENERABLE"
            rows.append({
                "relative_path": relative, "size_bytes": source.stat().st_size,
                "sha256": source_hash, "artifact_role": role,
                "regenerability": regenerability,
                "replacement_compact_artifact": replacement_payload,
                "retention_required": retained, "deletion_status": deletion_status,
                "deletion_reasons": reasons, "consistency_checks": checks,
            })
        except (GateValidationError, ValueError, OSError) as exc:
            errors.extend(exc.errors if isinstance(exc, GateValidationError) else [f"{label}: {exc}"])
    if errors:
        raise GateValidationError(errors)
    rows.sort(key=lambda row: row["relative_path"])
    ready = bool(rows) and all(row["deletion_status"] in {"RETAIN", "SAFE_TO_DELETE_REGENERABLE"} for row in rows)
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION, "inventory_id": inventory_id,
        "validation": {"valid": True, "errors": []},
        "deletion_gate": "READY" if ready else "NOT_READY",
        "artifacts": rows, "retained_evidence": evidence_payload,
    }


def write_inventory(result: Mapping[str, Any], output_dir: Path) -> None:
    """Atomically publish JSON/TSV inventory outputs without overwriting."""

    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        (temporary / "inventory.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="",
        )
        with (temporary / "inventory.tsv").open("x", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow((
                "relative_path", "size_bytes", "sha256", "artifact_role",
                "regenerability", "replacement_compact_artifact",
                "replacement_size_bytes", "replacement_sha256",
                "retention_required", "deletion_status", "deletion_reasons",
                "consistency_checks_passed",
            ))
            for row in result["artifacts"]:
                replacement = row["replacement_compact_artifact"]
                writer.writerow((
                    row["relative_path"], row["size_bytes"], row["sha256"],
                    row["artifact_role"], row["regenerability"],
                    "N/A" if replacement is None else replacement["relative_path"],
                    "N/A" if replacement is None else replacement["size_bytes"],
                    "N/A" if replacement is None else replacement["sha256"],
                    str(row["retention_required"]).lower(), row["deletion_status"],
                    "; ".join(row["deletion_reasons"]) or "N/A",
                    "N/A" if not row["consistency_checks"] else str(all(check["passed"] for check in row["consistency_checks"])).lower(),
                ))
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
