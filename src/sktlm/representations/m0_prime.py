"""Generate and validate the derived M0-prime IAST-continuous substrate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from sktlm.latent.frontend import (
    parse_devanagari_surface,
    parse_m0_prime_iast_surface,
)
from sktlm.representations.devanagari import VIRAMA
from sktlm.representations.script import (
    DEVANAGARI_CONSONANTS,
    DEVANAGARI_INDEPENDENT_VOWELS,
    DEVANAGARI_SIGNS,
    DEVANAGARI_VOWEL_MARKS,
    whitespace_signature,
)


CONFIG_SCHEMA = "sktlm-m0-prime-generation-config/v1"
MANIFEST_SCHEMA = "sktlm-m0-prime-representation/v1"
VALIDATION_SCHEMA = "sktlm-m0-prime-validation/v1"
DERIVATION_ID = "m0-prime-iast-continuous-v1"
EXPECTED_M0_FREEZE_ID = (
    "9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40"
)
SOURCE_SCRIPT = "devanagari"
SOURCE_CONDITION = "continuous"
OUTPUT_SCRIPT = "iast_m0_prime"
OUTPUT_CONDITION = "continuous"

_M0_PRIME_INDEPENDENT_VOWELS = {
    written: ("ē" if iast == "ai" else "ō" if iast == "au" else iast)
    for written, iast in DEVANAGARI_INDEPENDENT_VOWELS.items()
}
_M0_PRIME_CONSONANTS = {
    written: (iast[:-1] + "ʰ" if len(iast) > 1 and iast.endswith("h") else iast)
    for written, iast in DEVANAGARI_CONSONANTS.items()
}
_M0_PRIME_VOWEL_MARKS = {
    written: ("ē" if iast == "ai" else "ō" if iast == "au" else iast)
    for written, iast in DEVANAGARI_VOWEL_MARKS.items()
}
_M0_PRIME_SIGNS = {
    **DEVANAGARI_SIGNS,
    "ँ": "m̐",
    "ॐ": "oṃ",
}
_LEXICAL_AI_GLYPHS = frozenset({"ऐ", "ै"})
_LEXICAL_AU_GLYPHS = frozenset({"औ", "ौ"})
_ASPIRATED_CONSONANT_GLYPHS = frozenset(
    written
    for written, iast in DEVANAGARI_CONSONANTS.items()
    if len(iast) > 1 and iast.endswith("h")
)
_PLAIN_AMBIGUOUS_DIGRAPHS = ("kh", "gh", "ch", "jh", "ṭh", "ḍh", "th", "dh", "ph", "bh")


@dataclass(frozen=True, slots=True)
class M0PrimeConfig:
    config_path: Path
    repo_root: Path
    source_manifest: Path
    canonical_manifest: Path
    source_root: Path
    output_root: Path
    artifact_dir: Path
    expected_source_manifest_sha256: str
    expected_canonical_manifest_sha256: str
    expected_documents: int
    require_clean_git: bool
    require_observed_contrasts: bool


@dataclass(frozen=True, slots=True)
class M0PrimeResult:
    documents: int
    source_bytes: int
    output_bytes: int
    output_characters: int
    output_lines: int
    lexical_ai: int
    lexical_au: int
    lexical_aspirates: int
    hiatus_ai: int
    hiatus_au: int
    plain_consonant_digraphs: int
    manifest_sha256: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(text, encoding="utf-8", newline="")
    os.replace(temporary, path)


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def _write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(fieldnames), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _repo_path(repo_root: Path, value: str, *, label: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"{label} must be repository-relative: {value}")
    resolved = (repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root):
        raise ValueError(f"{label} escapes repository root: {value}")
    return resolved


def load_config(config_path: Path, *, repo_root: Path | None = None) -> M0PrimeConfig:
    config_path = config_path.resolve()
    if repo_root is None:
        repo_root = Path.cwd().resolve()
    else:
        repo_root = repo_root.resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CONFIG_SCHEMA:
        raise ValueError(f"unsupported M0-prime config schema: {payload.get('schema_version')}")
    if payload.get("derivation_id") != DERIVATION_ID:
        raise ValueError(f"unexpected derivation_id: {payload.get('derivation_id')}")

    source = payload.get("source", {})
    output = payload.get("output", {})
    transform = payload.get("transform", {})
    provenance = payload.get("provenance", {})
    expected_transform = {
        "source_script": SOURCE_SCRIPT,
        "source_condition": SOURCE_CONDITION,
        "output_script": OUTPUT_SCRIPT,
        "output_condition": OUTPUT_CONDITION,
        "lexical_ai": "ē",
        "lexical_au": "ō",
        "hiatus_ai": "ai",
        "hiatus_au": "au",
        "aspirated_consonants": "kʰ gʰ cʰ jʰ ṭʰ ḍʰ tʰ dʰ pʰ bʰ",
        "plain_consonant_sequences": "kh gh ch jh ṭh ḍh th dh ph bh",
    }
    if transform != expected_transform:
        raise ValueError("M0-prime transform contract differs from the frozen v1 semantics")
    if source.get("freeze_id") != EXPECTED_M0_FREEZE_ID:
        raise ValueError("M0-prime source must be the frozen M0 corpus")

    return M0PrimeConfig(
        config_path=config_path,
        repo_root=repo_root,
        source_manifest=_repo_path(
            repo_root, str(source["representation_manifest"]), label="source manifest"
        ),
        canonical_manifest=_repo_path(
            repo_root, str(source["canonical_manifest"]), label="canonical manifest"
        ),
        source_root=_repo_path(repo_root, str(source["root"]), label="source root"),
        output_root=_repo_path(repo_root, str(output["root"]), label="output root"),
        artifact_dir=_repo_path(
            repo_root, str(output["artifact_dir"]), label="artifact directory"
        ),
        expected_source_manifest_sha256=str(source["representation_manifest_sha256"]),
        expected_canonical_manifest_sha256=str(source["canonical_manifest_sha256"]),
        expected_documents=int(source["documents"]),
        require_clean_git=bool(provenance.get("require_clean_git", True)),
        require_observed_contrasts=bool(
            payload.get("validation", {}).get("require_observed_contrasts", True)
        ),
    )


def transliterate_devanagari_to_m0_prime_iast(text: str) -> str:
    """Render Devanagari injectively for the derived continuous condition."""

    text = unicodedata.normalize("NFC", text)
    output: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        consonant = _M0_PRIME_CONSONANTS.get(character)
        if consonant is not None:
            output.append(consonant)
            following = text[index + 1] if index + 1 < len(text) else ""
            if following == VIRAMA:
                index += 2
                continue
            vowel = _M0_PRIME_VOWEL_MARKS.get(following)
            if vowel is not None:
                output.append(vowel)
                index += 2
                continue
            output.append("a")
            index += 1
            continue
        independent = _M0_PRIME_INDEPENDENT_VOWELS.get(character)
        if independent is not None:
            output.append(independent)
        elif character in _M0_PRIME_SIGNS:
            output.append(_M0_PRIME_SIGNS[character])
        elif "\u0900" <= character <= "\u097f":
            raise ValueError(f"unsupported Devanagari character U+{ord(character):04X}")
        else:
            output.append(character)
        index += 1
    return unicodedata.normalize("NFC", "".join(output))


def _git_provenance(config: M0PrimeConfig) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=config.repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=config.repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("cannot resolve Git provenance") from exc
    if config.require_clean_git and status:
        raise RuntimeError("formal M0-prime generation requires a clean Git worktree")
    implementation_path = Path(__file__).resolve()
    return {
        "git_commit_sha": commit,
        "git_worktree_clean": not bool(status),
        "implementation": "sktlm.representations.m0_prime",
        "implementation_file": implementation_path.relative_to(config.repo_root).as_posix(),
        "implementation_sha256": file_sha256(implementation_path),
    }


def _validate_source_manifests(
    config: M0PrimeConfig,
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    if file_sha256(config.source_manifest) != config.expected_source_manifest_sha256:
        raise RuntimeError("frozen M0 representation-manifest SHA-256 mismatch")
    if file_sha256(config.canonical_manifest) != config.expected_canonical_manifest_sha256:
        raise RuntimeError("frozen M0 canonical-manifest SHA-256 mismatch")
    _, representation_rows = _read_csv(config.source_manifest)
    source_rows = [
        row
        for row in representation_rows
        if row.get("script") == SOURCE_SCRIPT
        and row.get("condition") == SOURCE_CONDITION
    ]
    source_rows.sort(key=lambda row: row["relative_path"])
    if len(source_rows) != config.expected_documents:
        raise RuntimeError("M0-prime source document count mismatch")
    if len({row["relative_path"] for row in source_rows}) != len(source_rows):
        raise RuntimeError("duplicate M0-prime source relative path")
    if {row["freeze_id"] for row in source_rows} != {EXPECTED_M0_FREEZE_ID}:
        raise RuntimeError("M0-prime source rows mix or change the M0 freeze")

    _, canonical_rows = _read_csv(config.canonical_manifest)
    canonical_by_relative = {row["freeze_input_path"]: row for row in canonical_rows}
    if len(canonical_by_relative) != config.expected_documents:
        raise RuntimeError("canonical M0 document identity is not one-to-one")
    if set(canonical_by_relative) != {row["relative_path"] for row in source_rows}:
        raise RuntimeError("source/canonical document membership mismatch")
    return source_rows, canonical_by_relative


def _source_path(config: M0PrimeConfig, row: dict[str, str]) -> Path:
    path = _repo_path(config.repo_root, row["representation_path"], label="source row path")
    if not path.is_relative_to(config.source_root):
        raise RuntimeError(f"source row escapes configured root: {path}")
    return path


def _validate_semantics(source_text: str, output_text: str) -> dict[str, int]:
    if whitespace_signature(source_text) != whitespace_signature(output_text):
        raise RuntimeError("M0-prime transformation changed whitespace order")
    if any("\u0900" <= character <= "\u097f" for character in output_text):
        raise RuntimeError("M0-prime output retains a Devanagari code point")
    source_parsed = parse_devanagari_surface(source_text)
    output_parsed = parse_m0_prime_iast_surface(output_text)
    if source_parsed.phonemes != output_parsed.phonemes:
        raise RuntimeError("M0-prime output changed script-neutral phoneme order")

    lexical_ai = sum(source_text.count(glyph) for glyph in _LEXICAL_AI_GLYPHS)
    lexical_au = sum(source_text.count(glyph) for glyph in _LEXICAL_AU_GLYPHS)
    lexical_aspirates = sum(
        source_text.count(glyph) for glyph in _ASPIRATED_CONSONANT_GLYPHS
    )
    if output_text.count("ē") != lexical_ai or output_text.count("ō") != lexical_au:
        raise RuntimeError("lexical diphthong rendering count mismatch")
    if output_text.count("ʰ") != lexical_aspirates:
        raise RuntimeError("aspirated-consonant rendering count mismatch")
    return {
        "phonemes": len(output_parsed.phonemes),
        "lexical_ai": lexical_ai,
        "lexical_au": lexical_au,
        "lexical_aspirates": lexical_aspirates,
        "hiatus_ai": output_text.count("ai"),
        "hiatus_au": output_text.count("au"),
        "plain_consonant_digraphs": sum(
            output_text.count(token) for token in _PLAIN_AMBIGUOUS_DIGRAPHS
        ),
    }


_MANIFEST_FIELDS = (
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
    "char_count",
    "line_count",
    "source_script",
    "source_condition",
    "source_representation_path",
    "source_representation_hash",
    "source_byte_count",
    "phoneme_count",
    "lexical_ai_count",
    "lexical_au_count",
    "lexical_aspirated_consonant_count",
    "hiatus_ai_count",
    "hiatus_au_count",
    "plain_consonant_digraph_count",
)


def generate(config: M0PrimeConfig) -> M0PrimeResult:
    """Generate one atomic, non-overwriting M0-prime representation tree."""

    if config.output_root.exists():
        raise FileExistsError(f"M0-prime output root already exists: {config.output_root}")
    if config.artifact_dir.exists():
        raise FileExistsError(f"M0-prime artifact directory already exists: {config.artifact_dir}")
    provenance = _git_provenance(config)
    source_rows, canonical_by_relative = _validate_source_manifests(config)

    token = uuid.uuid4().hex
    staged_output = config.output_root.with_name(f".{config.output_root.name}.tmp-{token}")
    staged_artifact = config.artifact_dir.with_name(f".{config.artifact_dir.name}.tmp-{token}")
    if staged_output.exists() or staged_artifact.exists():
        raise FileExistsError("unexpected M0-prime staging path collision")
    staged_output.mkdir(parents=True)
    staged_artifact.mkdir(parents=True)

    rows: list[dict[str, Any]] = []
    totals = {
        "source_bytes": 0,
        "output_bytes": 0,
        "output_characters": 0,
        "output_lines": 0,
        "phonemes": 0,
        "lexical_ai": 0,
        "lexical_au": 0,
        "lexical_aspirates": 0,
        "hiatus_ai": 0,
        "hiatus_au": 0,
        "plain_consonant_digraphs": 0,
    }
    for source_row in source_rows:
        relative = source_row["relative_path"]
        canonical_row = canonical_by_relative[relative]
        if source_row["canonical_hash"] != canonical_row["canonical_hash"]:
            raise RuntimeError(f"canonical hash mismatch in source row: {relative}")
        source_path = _source_path(config, source_row)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        source_bytes = source_path.read_bytes()
        if len(source_bytes) != int(source_row["byte_count"]):
            raise RuntimeError(f"source byte count mismatch: {relative}")
        if hashlib.sha256(source_bytes).hexdigest() != source_row["representation_hash"]:
            raise RuntimeError(f"source SHA-256 mismatch: {relative}")
        source_text = source_bytes.decode("utf-8", errors="strict")
        output_text = transliterate_devanagari_to_m0_prime_iast(source_text)
        semantics = _validate_semantics(source_text, output_text)
        output_bytes = output_text.encode("utf-8")
        destination = staged_output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(output_bytes)
        final_destination = config.output_root / relative

        line_count = len(output_text.splitlines())
        if line_count != int(source_row["line_count"]):
            raise RuntimeError(f"line count changed: {relative}")
        totals["source_bytes"] += len(source_bytes)
        totals["output_bytes"] += len(output_bytes)
        totals["output_characters"] += len(output_text)
        totals["output_lines"] += line_count
        for key in (
            "phonemes",
            "lexical_ai",
            "lexical_au",
            "lexical_aspirates",
            "hiatus_ai",
            "hiatus_au",
            "plain_consonant_digraphs",
        ):
            totals[key] += semantics[key]
        rows.append(
            {
                "schema_version": MANIFEST_SCHEMA,
                "derivation_id": DERIVATION_ID,
                "freeze_id": EXPECTED_M0_FREEZE_ID,
                "relative_path": relative,
                "document_id": canonical_row["document_id"],
                "split": canonical_row["split"],
                "canonical_hash": canonical_row["canonical_hash"],
                "script": OUTPUT_SCRIPT,
                "condition": OUTPUT_CONDITION,
                "representation_path": final_destination.relative_to(config.repo_root).as_posix(),
                "representation_hash": hashlib.sha256(output_bytes).hexdigest(),
                "byte_count": len(output_bytes),
                "char_count": len(output_text),
                "line_count": line_count,
                "source_script": SOURCE_SCRIPT,
                "source_condition": SOURCE_CONDITION,
                "source_representation_path": source_path.relative_to(config.repo_root).as_posix(),
                "source_representation_hash": source_row["representation_hash"],
                "source_byte_count": len(source_bytes),
                "phoneme_count": semantics["phonemes"],
                "lexical_ai_count": semantics["lexical_ai"],
                "lexical_au_count": semantics["lexical_au"],
                "lexical_aspirated_consonant_count": semantics["lexical_aspirates"],
                "hiatus_ai_count": semantics["hiatus_ai"],
                "hiatus_au_count": semantics["hiatus_au"],
                "plain_consonant_digraph_count": semantics["plain_consonant_digraphs"],
            }
        )

    if config.require_observed_contrasts and any(
        totals[key] == 0
        for key in (
            "lexical_ai",
            "lexical_au",
            "lexical_aspirates",
            "hiatus_ai",
            "hiatus_au",
            "plain_consonant_digraphs",
        )
    ):
        raise RuntimeError("formal corpus does not expose every declared M0-prime contrast")

    manifest_path = staged_artifact / "manifest.csv"
    _write_csv(manifest_path, _MANIFEST_FIELDS, rows)
    manifest_sha256 = file_sha256(manifest_path)
    config_payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    (staged_artifact / "config.snapshot.json").write_text(
        _canonical_json(config_payload), encoding="utf-8", newline=""
    )
    generation = {
        "schema_version": VALIDATION_SCHEMA,
        "status": "GENERATED_PENDING_VALIDATION",
        "derivation_id": DERIVATION_ID,
        "source_freeze_id": EXPECTED_M0_FREEZE_ID,
        "source_representation_manifest_sha256": config.expected_source_manifest_sha256,
        "source_canonical_manifest_sha256": config.expected_canonical_manifest_sha256,
        "config_sha256": file_sha256(config.config_path),
        "manifest_sha256": manifest_sha256,
        "documents": len(rows),
        "totals": totals,
        "semantics": {
            "lexical_ai": "ē",
            "lexical_au": "ō",
            "hiatus_ai": "ai",
            "hiatus_au": "au",
            "aspirated_consonants": "kʰ gʰ cʰ jʰ ṭʰ ḍʰ tʰ dʰ pʰ bʰ",
            "plain_consonant_digraphs": "kh gh ch jh ṭh ḍh th dh ph bh",
            "source": "frozen M0 Devanagari continuous",
        },
        "provenance": provenance,
    }
    (staged_artifact / "generation.json").write_text(
        _canonical_json(generation), encoding="utf-8", newline=""
    )
    config.output_root.parent.mkdir(parents=True, exist_ok=True)
    config.artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    staged_output.rename(config.output_root)
    staged_artifact.rename(config.artifact_dir)
    return M0PrimeResult(
        documents=len(rows),
        source_bytes=totals["source_bytes"],
        output_bytes=totals["output_bytes"],
        output_characters=totals["output_characters"],
        output_lines=totals["output_lines"],
        lexical_ai=totals["lexical_ai"],
        lexical_au=totals["lexical_au"],
        lexical_aspirates=totals["lexical_aspirates"],
        hiatus_ai=totals["hiatus_ai"],
        hiatus_au=totals["hiatus_au"],
        plain_consonant_digraphs=totals["plain_consonant_digraphs"],
        manifest_sha256=manifest_sha256,
    )


def validate(config: M0PrimeConfig) -> M0PrimeResult:
    """Fail closed on source, provenance, identity, content, or hash drift."""

    if not config.output_root.is_dir() or not config.artifact_dir.is_dir():
        raise FileNotFoundError("M0-prime output/artifact directory is incomplete")
    validation_path = config.artifact_dir / "validation.json"
    checksums_path = config.artifact_dir / "SHA256SUMS"
    if validation_path.exists() or checksums_path.exists():
        raise FileExistsError("M0-prime formal validation has already been published")
    provenance = _git_provenance(config)
    source_rows, canonical_by_relative = _validate_source_manifests(config)
    generation = json.loads(
        (config.artifact_dir / "generation.json").read_text(encoding="utf-8")
    )
    if generation.get("provenance", {}).get("git_commit_sha") != provenance["git_commit_sha"]:
        raise RuntimeError("generation/validation Git commit mismatch")
    if generation.get("config_sha256") != file_sha256(config.config_path):
        raise RuntimeError("generation/validation config mismatch")

    manifest_path = config.artifact_dir / "manifest.csv"
    if generation.get("manifest_sha256") != file_sha256(manifest_path):
        raise RuntimeError("M0-prime manifest identity mismatch")
    fields, rows = _read_csv(manifest_path)
    if fields != list(_MANIFEST_FIELDS):
        raise RuntimeError("M0-prime manifest schema columns mismatch")
    if len(rows) != config.expected_documents:
        raise RuntimeError("M0-prime output manifest row count mismatch")
    by_relative = {row["relative_path"]: row for row in rows}
    if len(by_relative) != len(rows):
        raise RuntimeError("duplicate M0-prime output manifest relative path")
    if set(by_relative) != {row["relative_path"] for row in source_rows}:
        raise RuntimeError("M0-prime output membership mismatch")

    actual_files = {
        path.relative_to(config.output_root).as_posix()
        for path in config.output_root.rglob("*.txt")
        if path.is_file()
    }
    if actual_files != set(by_relative):
        raise RuntimeError("M0-prime output tree membership mismatch")

    totals = {
        "source_bytes": 0,
        "output_bytes": 0,
        "output_characters": 0,
        "output_lines": 0,
        "phonemes": 0,
        "lexical_ai": 0,
        "lexical_au": 0,
        "lexical_aspirates": 0,
        "hiatus_ai": 0,
        "hiatus_au": 0,
        "plain_consonant_digraphs": 0,
    }
    for source_row in source_rows:
        relative = source_row["relative_path"]
        row = by_relative[relative]
        canonical_row = canonical_by_relative[relative]
        if row["schema_version"] != MANIFEST_SCHEMA or row["derivation_id"] != DERIVATION_ID:
            raise RuntimeError(f"M0-prime row schema/derivation mismatch: {relative}")
        if row["freeze_id"] != EXPECTED_M0_FREEZE_ID:
            raise RuntimeError(f"M0-prime row freeze mismatch: {relative}")
        if row["document_id"] != canonical_row["document_id"] or row["split"] != canonical_row["split"]:
            raise RuntimeError(f"document identity/split mismatch: {relative}")
        if row["canonical_hash"] != canonical_row["canonical_hash"]:
            raise RuntimeError(f"canonical identity mismatch: {relative}")
        if row["script"] != OUTPUT_SCRIPT or row["condition"] != OUTPUT_CONDITION:
            raise RuntimeError(f"output representation identity mismatch: {relative}")

        source_path = _source_path(config, source_row)
        source_bytes = source_path.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != source_row["representation_hash"]:
            raise RuntimeError(f"source SHA-256 mismatch during validation: {relative}")
        output_path = _repo_path(
            config.repo_root, row["representation_path"], label="output row path"
        )
        if not output_path.is_relative_to(config.output_root) or not output_path.is_file():
            raise RuntimeError(f"output row escapes or is missing: {relative}")
        output_bytes = output_path.read_bytes()
        if len(output_bytes) != int(row["byte_count"]):
            raise RuntimeError(f"output byte count mismatch: {relative}")
        if hashlib.sha256(output_bytes).hexdigest() != row["representation_hash"]:
            raise RuntimeError(f"output SHA-256 mismatch: {relative}")
        source_text = source_bytes.decode("utf-8", errors="strict")
        output_text = output_bytes.decode("utf-8", errors="strict")
        if output_text != transliterate_devanagari_to_m0_prime_iast(source_text):
            raise RuntimeError(f"deterministic regeneration mismatch: {relative}")
        semantics = _validate_semantics(source_text, output_text)
        line_count = len(output_text.splitlines())
        expected_numeric = {
            "char_count": len(output_text),
            "line_count": line_count,
            "source_byte_count": len(source_bytes),
            "phoneme_count": semantics["phonemes"],
            "lexical_ai_count": semantics["lexical_ai"],
            "lexical_au_count": semantics["lexical_au"],
            "lexical_aspirated_consonant_count": semantics["lexical_aspirates"],
            "hiatus_ai_count": semantics["hiatus_ai"],
            "hiatus_au_count": semantics["hiatus_au"],
            "plain_consonant_digraph_count": semantics["plain_consonant_digraphs"],
        }
        for field, expected in expected_numeric.items():
            if int(row[field]) != expected:
                raise RuntimeError(f"{field} mismatch: {relative}")
        totals["source_bytes"] += len(source_bytes)
        totals["output_bytes"] += len(output_bytes)
        totals["output_characters"] += len(output_text)
        totals["output_lines"] += line_count
        for key in (
            "phonemes",
            "lexical_ai",
            "lexical_au",
            "lexical_aspirates",
            "hiatus_ai",
            "hiatus_au",
            "plain_consonant_digraphs",
        ):
            totals[key] += semantics[key]

    if totals != generation.get("totals"):
        raise RuntimeError("generation/validation total mismatch")
    if config.require_observed_contrasts and any(
        totals[key] == 0
        for key in (
            "lexical_ai",
            "lexical_au",
            "lexical_aspirates",
            "hiatus_ai",
            "hiatus_au",
            "plain_consonant_digraphs",
        )
    ):
        raise RuntimeError("formal output lacks a declared M0-prime contrast")

    validation = {
        "schema_version": VALIDATION_SCHEMA,
        "status": "VALID",
        "derivation_id": DERIVATION_ID,
        "source_freeze_id": EXPECTED_M0_FREEZE_ID,
        "documents": len(rows),
        "manifest_sha256": file_sha256(manifest_path),
        "totals": totals,
        "checks": {
            "source_manifest_identity": True,
            "canonical_manifest_identity": True,
            "document_membership_identity": True,
            "document_id_and_split_identity": True,
            "source_file_hashes": True,
            "output_file_hashes": True,
            "line_order_and_count": True,
            "script_neutral_phoneme_identity": True,
            "lexical_diphthong_distinction": True,
            "hiatus_distinction": True,
            "aspirated_consonant_distinction": True,
            "plain_consonant_cluster_distinction": True,
            "allowed_alphabet": True,
            "deterministic_regeneration": True,
            "git_and_config_provenance": True,
        },
        "provenance": provenance,
    }
    _write_text_atomic(validation_path, _canonical_json(validation))
    checksummed = (
        "config.snapshot.json",
        "generation.json",
        "manifest.csv",
        "validation.json",
    )
    checksum_lines = [
        f"{file_sha256(config.artifact_dir / name)}  {name}" for name in checksummed
    ]
    _write_text_atomic(checksums_path, "\n".join(checksum_lines) + "\n")
    return M0PrimeResult(
        documents=len(rows),
        source_bytes=totals["source_bytes"],
        output_bytes=totals["output_bytes"],
        output_characters=totals["output_characters"],
        output_lines=totals["output_lines"],
        lexical_ai=totals["lexical_ai"],
        lexical_au=totals["lexical_au"],
        lexical_aspirates=totals["lexical_aspirates"],
        hiatus_ai=totals["hiatus_ai"],
        hiatus_au=totals["hiatus_au"],
        plain_consonant_digraphs=totals["plain_consonant_digraphs"],
        manifest_sha256=file_sha256(manifest_path),
    )


def _print_result(result: M0PrimeResult) -> None:
    print(f"documents: {result.documents}")
    print(f"source bytes: {result.source_bytes}")
    print(f"output bytes: {result.output_bytes}")
    print(f"output characters: {result.output_characters}")
    print(f"output lines: {result.output_lines}")
    print(f"lexical ai/au: {result.lexical_ai}/{result.lexical_au}")
    print(f"lexical aspirated consonants: {result.lexical_aspirates}")
    print(f"hiatus ai/au: {result.hiatus_ai}/{result.hiatus_au}")
    print(f"plain consonant+h sequences: {result.plain_consonant_digraphs}")
    print(f"manifest sha256: {result.manifest_sha256}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate or validate M0-prime")
    parser.add_argument("action", choices=("generate", "validate"))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/representations/m0_prime_iast_continuous.json"),
    )
    args = parser.parse_args(argv)
    config = load_config(args.config)
    result = generate(config) if args.action == "generate" else validate(config)
    _print_result(result)


def _action_main(action: str, argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=f"{action.title()} M0-prime")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/representations/m0_prime_iast_continuous.json"),
    )
    args = parser.parse_args(argv)
    config = load_config(args.config)
    result = generate(config) if action == "generate" else validate(config)
    _print_result(result)


def generate_main(argv: list[str] | None = None) -> None:
    _action_main("generate", argv)


def validate_main(argv: list[str] | None = None) -> None:
    _action_main("validate", argv)


if __name__ == "__main__":
    main()
