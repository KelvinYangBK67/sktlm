"""Build and verify content-identical local scientific review packets."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SPEC_SCHEMA_VERSION = "sktlm-review-packet-spec/v1"
MANIFEST_SCHEMA_VERSION = "sktlm-review-packet-manifest/v1"
RAW_METADATA_SCHEMA_VERSION = "sktlm-raw-review-metadata/v1"
REVIEWER_IDS = tuple(f"reviewer_{index:02d}" for index in range(1, 6))
REQUIRED_ROLES = frozenset({
    "method_spec", "experimental_design", "decisions", "provenance",
    "six_representation_summary", "quantitative_tables", "qualitative_materials",
    "limitations", "reviewer_prompt", "reviewer_method",
})


class ReviewPacketError(ValueError):
    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))

    def payload(self) -> dict[str, Any]:
        return {"valid": False, "errors": list(self.errors)}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_full_sha(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewPacketError((f"{label} is unreadable JSON: {path}: {exc}",)) from exc
    if not isinstance(value, dict):
        raise ReviewPacketError((f"{label} must be a JSON object: {path}",))
    return value


def _git(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo_root), *arguments),
        check=False, capture_output=True, text=True, encoding="utf-8",
    )
    if completed.returncode != 0:
        raise ReviewPacketError((
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}",
        ))
    return completed.stdout.strip()


def _safe_relative_posix_path(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ReviewPacketError((f"{label} must be a nonempty relative POSIX path",))
    if "\\" in value or ":" in value:
        raise ReviewPacketError((f"unsafe {label}: {value!r}",))
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.name in {"", "."}:
        raise ReviewPacketError((f"unsafe {label}: {value!r}",))
    return path


def _safe_packet_path(value: object) -> PurePosixPath:
    return _safe_relative_posix_path(value, "packet_path")


def _parse_spec(spec_path: Path, repo_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    spec = _read_object(spec_path, "review packet spec")
    errors: list[str] = []
    if spec.get("schema_version") != SPEC_SCHEMA_VERSION:
        errors.append(f"schema_version must be {SPEC_SCHEMA_VERSION!r}")
    if not isinstance(spec.get("milestone_id"), str) or not spec["milestone_id"].strip():
        errors.append("milestone_id must be a nonempty string")
    if not _is_full_sha(spec.get("scientific_commit")):
        errors.append("scientific_commit must be a lowercase full SHA")
    raw_files = spec.get("files")
    if not isinstance(raw_files, list):
        errors.append("files must be an array")
        raw_files = []

    files: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_files):
        label = f"files[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label} must be an object")
            continue
        role, source_value = raw.get("role"), raw.get("path")
        if not isinstance(role, str) or not role:
            errors.append(f"{label}.role must be a nonempty string")
            continue
        if not isinstance(source_value, str) or not source_value:
            errors.append(f"{label}.path must be a nonempty repository-relative path")
            continue
        try:
            packet_path = _safe_packet_path(raw.get("packet_path"))
        except ReviewPacketError as exc:
            errors.extend(f"{label}: {error}" for error in exc.errors)
            continue
        source = (repo_root / source_value).resolve()
        if not source.is_relative_to(repo_root):
            errors.append(f"{label}.path escapes repository root")
            continue
        files.append({
            "role": role,
            "source": source,
            "source_path": source.relative_to(repo_root).as_posix(),
            "packet_path": packet_path.as_posix(),
        })

    roles = {row["role"] for row in files}
    missing_roles = sorted(REQUIRED_ROLES - roles)
    if missing_roles:
        errors.append(f"packet spec is missing required roles: {missing_roles}")
    for role in ("reviewer_prompt", "reviewer_method"):
        if sum(row["role"] == role for row in files) != 1:
            errors.append(f"packet spec must contain exactly one {role}")
    packet_paths = [row["packet_path"] for row in files]
    repeated = sorted(value for value in set(packet_paths) if packet_paths.count(value) > 1)
    if repeated:
        errors.append(f"duplicate packet_path values: {repeated}")
    if errors:
        raise ReviewPacketError(errors)
    return spec, sorted(files, key=lambda row: (row["role"], row["packet_path"], row["source_path"]))


def build_packet(
    spec_path: Path,
    output_dir: Path,
    *,
    repo_root: Path = Path("."),
    repository_commit: str | None = None,
    require_clean: bool = True,
    require_tracked: bool = True,
) -> dict[str, Any]:
    repo_root, spec_path, output_dir = repo_root.resolve(), spec_path.resolve(), output_dir.resolve()
    spec, files = _parse_spec(spec_path, repo_root)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite review packet: {output_dir}")
    if repository_commit is None:
        repository_commit = _git(repo_root, "rev-parse", "HEAD")
    if not _is_full_sha(repository_commit):
        raise ReviewPacketError(("repository_commit must be a lowercase full SHA",))
    if require_clean and _git(repo_root, "status", "--porcelain"):
        raise ReviewPacketError(("review packet must be built from a clean working tree",))
    if require_tracked:
        for row in files:
            _git(repo_root, "ls-files", "--error-unmatch", "--", row["source_path"])

    entries: list[dict[str, Any]] = []
    for row in files:
        source = row["source"]
        if not source.is_file():
            raise ReviewPacketError((f"packet source file is missing: {row['source_path']}",))
        entries.append({
            "role": row["role"],
            "source_path": row["source_path"],
            "packet_path": row["packet_path"],
            "bytes": source.stat().st_size,
            "sha256": _file_sha256(source),
        })
    prompt = next(row for row in entries if row["role"] == "reviewer_prompt")
    method = next(row for row in entries if row["role"] == "reviewer_method")
    identity = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "milestone_id": spec["milestone_id"],
        "scientific_commit": spec["scientific_commit"],
        "repository_commit": repository_commit,
        "expected_reviewer_ids": list(REVIEWER_IDS),
        "reviewer_prompt_sha256": prompt["sha256"],
        "reviewer_method_sha256": method["sha256"],
        "files": entries,
    }
    manifest = {
        **identity,
        "packet_sha256": _sha256_bytes(_canonical_json(identity).encode("utf-8")),
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for row in files:
            destination = temporary / Path(row["packet_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(row["source"], destination)
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="",
        )
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest

def verify_packet(packet_dir: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    packet_dir = packet_dir.resolve()
    errors: list[str] = []
    manifest_path = packet_dir / "manifest.json"
    try:
        manifest = _read_object(manifest_path, "review packet manifest")
    except ReviewPacketError as exc:
        return {"valid": False, "errors": list(exc.errors), "packet_dir": str(packet_dir)}
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(f"manifest schema_version must be {MANIFEST_SCHEMA_VERSION!r}")
    identity = {key: value for key, value in manifest.items() if key != "packet_sha256"}
    expected_packet_sha = _sha256_bytes(_canonical_json(identity).encode("utf-8"))
    if manifest.get("packet_sha256") != expected_packet_sha:
        errors.append("packet manifest identity hash mismatch")
    files = manifest.get("files")
    if not isinstance(files, list):
        errors.append("packet manifest files must be an array")
        files = []
    resolved_root = None if repo_root is None else repo_root.resolve()
    for index, row in enumerate(files):
        if not isinstance(row, dict):
            errors.append(f"manifest files[{index}] must be an object")
            continue
        try:
            relative = _safe_packet_path(row.get("packet_path"))
        except ReviewPacketError as exc:
            errors.extend(exc.errors)
            continue
        packet_file = packet_dir / Path(relative.as_posix())
        if not packet_file.is_file():
            errors.append(f"packet file is missing: {relative.as_posix()}")
            continue
        if packet_file.stat().st_size != row.get("bytes") or _file_sha256(packet_file) != row.get("sha256"):
            errors.append(f"packet file identity mismatch: {relative.as_posix()}")
        if resolved_root is not None:
            source_value = row.get("source_path")
            if not isinstance(source_value, str):
                errors.append(f"packet source path is invalid: {relative.as_posix()}")
                continue
            source = (resolved_root / source_value).resolve()
            if not source.is_relative_to(resolved_root) or not source.is_file():
                errors.append(f"packet source is missing or unsafe: {source_value}")
            elif source.stat().st_size != row.get("bytes") or _file_sha256(source) != row.get("sha256"):
                errors.append(f"packet source changed after freeze: {source_value}")
    return {
        "valid": not errors,
        "errors": errors,
        "packet_dir": str(packet_dir),
        "packet_sha256": manifest.get("packet_sha256"),
        "reviewer_prompt_sha256": manifest.get("reviewer_prompt_sha256"),
        "reviewer_method_sha256": manifest.get("reviewer_method_sha256"),
        "manifest": manifest,
    }


def verify_raw_review_metadata(metadata_path: Path, packet_dir: Path) -> dict[str, Any]:
    packet = verify_packet(packet_dir)
    errors = list(packet["errors"])
    try:
        metadata = _read_object(metadata_path, "raw review metadata")
    except ReviewPacketError as exc:
        return {"valid": False, "errors": [*errors, *exc.errors]}
    if metadata.get("schema_version") != RAW_METADATA_SCHEMA_VERSION:
        errors.append(f"raw metadata schema_version must be {RAW_METADATA_SCHEMA_VERSION!r}")
    reviewer_id = metadata.get("reviewer_id")
    if reviewer_id not in REVIEWER_IDS:
        errors.append(f"reviewer_id must be one of {REVIEWER_IDS}")
    for field in ("packet_sha256", "reviewer_prompt_sha256", "reviewer_method_sha256"):
        if metadata.get(field) != packet.get(field):
            errors.append(f"raw review metadata {field} does not match packet")
    try:
        raw_relative = _safe_relative_posix_path(
            metadata.get("raw_review_path"), "raw_review_path"
        )
    except ReviewPacketError as exc:
        errors.extend(exc.errors)
    else:
        raw_path = metadata_path.parent / Path(raw_relative.as_posix())
        if not raw_path.is_file():
            errors.append(f"raw review is missing: {raw_path}")
        elif _file_sha256(raw_path) != metadata.get("raw_response_sha256"):
            errors.append("raw review SHA-256 does not match metadata")
    return {
        "valid": not errors,
        "errors": errors,
        "reviewer_id": reviewer_id,
        "metadata_path": str(metadata_path.resolve()),
    }