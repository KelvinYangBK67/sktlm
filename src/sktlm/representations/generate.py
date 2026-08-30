"""Generate six script ? spacing datasets from one canonical freeze.

``lexical_boundary`` uses continuous text plus a sidecar containing only
source-provided whitespace offsets. These offsets are a documented proxy, not
inferred or gold Sanskrit segmentation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sktlm.representations.script import transform_script, whitespace_signature
from sktlm.representations.spacing import apply_spacing


IMPLEMENTATION = "canonical-representations-1"
DEFAULT_CANONICAL_ROOT = Path("data/canonical/gretil_iast")
DEFAULT_CANONICAL_MANIFEST = Path("data/manifests/canonical_corpus.csv")
DEFAULT_OUTPUT_ROOT = Path("data/representations/gretil")
DEFAULT_MANIFEST = Path("data/manifests/representations.csv")
DEFAULT_REPORT = Path("reports/representations/representation_generation_summary.txt")

SCRIPTS = ("iast", "devanagari")
CONDITIONS = ("continuous", "surface_word", "lexical_boundary")


@dataclass(frozen=True, slots=True)
class GenerationResult:
    canonical_files: int
    representation_files: int
    boundary_sidecars: int
    boundary_offsets: int
    freeze_id: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def boundary_offsets(line: str) -> list[int]:
    """Map source-provided whitespace to offsets in the continuous line."""

    offsets: list[int] = []
    continuous_offset = 0
    pending_boundary = False
    for character in line:
        if character.isspace():
            pending_boundary = continuous_offset > 0
            continue
        if pending_boundary and continuous_offset not in offsets:
            offsets.append(continuous_offset)
        pending_boundary = False
        continuous_offset += 1
    return offsets


def _manifest_relative(row: dict[str, str]) -> str:
    canonical = PurePosixPath(row["canonical_path"].replace("\\", "/"))
    if "gretil_iast" in canonical.parts:
        index = canonical.parts.index("gretil_iast")
        return PurePosixPath(*canonical.parts[index + 1 :]).as_posix()
    return str(row["freeze_input_path"])


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_boundaries(path: Path, surface_text: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        for line_number, line in enumerate(surface_text.split("\n"), start=1):
            offsets = boundary_offsets(line)
            count += len(offsets)
            handle.write(
                json.dumps(
                    {
                        "line_number": line_number,
                        "continuous_char_count": sum(
                            1 for character in line if not character.isspace()
                        ),
                        "boundary_offsets": offsets,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    return count


def generate_representations(
    *,
    canonical_root: Path,
    canonical_manifest: Path,
    output_root: Path,
    manifest_path: Path,
    report_path: Path,
) -> GenerationResult:
    if not canonical_root.is_dir():
        raise FileNotFoundError(f"canonical root does not exist: {canonical_root}")
    if output_root.exists():
        raise FileExistsError(f"representation output root already exists: {output_root}")

    _, canonical_rows = _read_csv(canonical_manifest)
    rows_by_relative = {_manifest_relative(row): row for row in canonical_rows}
    freeze_ids = {row.get("freeze_id", "") for row in canonical_rows}
    if len(freeze_ids) != 1 or "" in freeze_ids:
        raise RuntimeError("canonical manifest must contain exactly one non-empty freeze_id")
    freeze_id = next(iter(freeze_ids))

    files = tuple(sorted(path for path in canonical_root.rglob("*.txt") if path.is_file()))
    relatives = {path.relative_to(canonical_root).as_posix() for path in files}
    if relatives != set(rows_by_relative):
        raise RuntimeError("canonical root membership does not match canonical manifest")

    output_root.mkdir(parents=True)
    manifest_rows: list[dict[str, Any]] = []
    totals: Counter[tuple[str, str]] = Counter()
    boundary_total = 0

    for canonical_path in files:
        relative = canonical_path.relative_to(canonical_root).as_posix()
        canonical_text = canonical_path.read_text(encoding="utf-8")
        canonical_row = rows_by_relative[relative]

        for script in SCRIPTS:
            surface_text = transform_script(canonical_text, "iast", script)
            if whitespace_signature(surface_text) != whitespace_signature(canonical_text):
                raise RuntimeError(f"script transform changed whitespace signature: {relative}")

            continuous_text = apply_spacing(surface_text, "continuous", script)
            for condition in CONDITIONS:
                represented = (
                    surface_text if condition == "surface_word" else continuous_text
                )
                destination = output_root / script / condition / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(represented, encoding="utf-8", newline="")

                sidecar_path: Path | None = None
                sidecar_hash = ""
                sidecar_count = 0
                if condition == "lexical_boundary":
                    sidecar_path = destination.with_suffix(".boundaries.jsonl")
                    sidecar_count = _write_boundaries(sidecar_path, surface_text)
                    sidecar_hash = file_sha256(sidecar_path)
                    boundary_total += sidecar_count

                totals[(script, condition)] += 1
                manifest_rows.append(
                    {
                        "freeze_id": freeze_id,
                        "relative_path": relative,
                        "canonical_hash": canonical_row["canonical_hash"],
                        "script": script,
                        "condition": condition,
                        "representation_path": destination.as_posix(),
                        "representation_hash": file_sha256(destination),
                        "byte_count": destination.stat().st_size,
                        "char_count": len(represented),
                        "line_count": len(represented.splitlines()),
                        "boundary_path": sidecar_path.as_posix() if sidecar_path else "",
                        "boundary_hash": sidecar_hash,
                        "boundary_count": sidecar_count,
                        "boundary_semantics": (
                            "source_whitespace_proxy_not_gold"
                            if condition == "lexical_boundary"
                            else ""
                        ),
                    }
                )

    manifest_rows.sort(
        key=lambda row: (str(row["script"]), str(row["condition"]), str(row["relative_path"]))
    )
    _write_csv(
        manifest_path,
        (
            "freeze_id",
            "relative_path",
            "canonical_hash",
            "script",
            "condition",
            "representation_path",
            "representation_hash",
            "byte_count",
            "char_count",
            "line_count",
            "boundary_path",
            "boundary_hash",
            "boundary_count",
            "boundary_semantics",
        ),
        manifest_rows,
    )

    summary = [
        "Formal GRETIL representation generation",
        "=======================================",
        f"implementation: {IMPLEMENTATION}",
        f"canonical_root: {canonical_root}",
        f"canonical_manifest: {canonical_manifest}",
        f"freeze_id: {freeze_id}",
        f"canonical_files: {len(files)}",
        f"representation_files: {len(manifest_rows)}",
        f"boundary_sidecars: {len(files) * len(SCRIPTS)}",
        f"boundary_offsets: {boundary_total}",
        "",
        "condition file counts:",
    ]
    for script in SCRIPTS:
        for condition in CONDITIONS:
            summary.append(f"  {script}/{condition}: {totals[(script, condition)]}")
    summary.extend(
        [
            "",
            "semantics:",
            "  surface_word preserves source-provided spacing from the canonical freeze",
            "  continuous removes ordinary lexical whitespace but preserves LF boundaries",
            "  lexical_boundary text equals continuous text and adds per-line offsets",
            "  boundary offsets come only from source-provided whitespace",
            "  boundary offsets are a proxy, not inferred or gold Sanskrit segmentation",
            "  script conversion occurs before spacing manipulation",
            "  canonical corpus files are never modified",
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(summary), encoding="utf-8", newline="")

    return GenerationResult(
        canonical_files=len(files),
        representation_files=len(manifest_rows),
        boundary_sidecars=len(files) * len(SCRIPTS),
        boundary_offsets=boundary_total,
        freeze_id=freeze_id,
    )


def validate_representations(
    *, canonical_root: Path, output_root: Path, manifest_path: Path
) -> GenerationResult:
    _, rows = _read_csv(manifest_path)
    expected_rows = len(tuple(canonical_root.rglob("*.txt"))) * len(SCRIPTS) * len(CONDITIONS)
    if len(rows) != expected_rows:
        raise RuntimeError("representation manifest row count mismatch")

    by_key = {
        (row["script"], row["condition"], row["relative_path"]): row for row in rows
    }
    if len(by_key) != len(rows):
        raise RuntimeError("duplicate representation manifest key")
    freeze_ids = {row["freeze_id"] for row in rows}
    if len(freeze_ids) != 1:
        raise RuntimeError("representation manifest mixes canonical freezes")

    boundary_total = 0
    canonical_files = tuple(sorted(canonical_root.rglob("*.txt")))
    for canonical_path in canonical_files:
        relative = canonical_path.relative_to(canonical_root).as_posix()
        canonical_text = canonical_path.read_text(encoding="utf-8")
        for script in SCRIPTS:
            surface_row = by_key[(script, "surface_word", relative)]
            continuous_row = by_key[(script, "continuous", relative)]
            boundary_row = by_key[(script, "lexical_boundary", relative)]
            surface_path = Path(surface_row["representation_path"])
            continuous_path = Path(continuous_row["representation_path"])
            boundary_text_path = Path(boundary_row["representation_path"])
            sidecar_path = Path(boundary_row["boundary_path"])

            expected_root = output_root.resolve()
            for path in (surface_path, continuous_path, boundary_text_path, sidecar_path):
                if not path.resolve().is_relative_to(expected_root):
                    raise RuntimeError(f"representation path escapes output root: {path}")

            for row, path in (
                (surface_row, surface_path),
                (continuous_row, continuous_path),
                (boundary_row, boundary_text_path),
            ):
                if not path.is_file() or file_sha256(path) != row["representation_hash"]:
                    raise RuntimeError(f"representation hash mismatch: {path}")
            if continuous_path.read_bytes() != boundary_text_path.read_bytes():
                raise RuntimeError(f"continuous/boundary text mismatch: {relative}")
            if script == "iast" and surface_path.read_bytes() != canonical_path.read_bytes():
                raise RuntimeError(f"IAST surface_word differs from canonical: {relative}")
            if file_sha256(sidecar_path) != boundary_row["boundary_hash"]:
                raise RuntimeError(f"boundary sidecar hash mismatch: {sidecar_path}")

            surface_text = surface_path.read_text(encoding="utf-8")
            sidecar_rows = [
                json.loads(line)
                for line in sidecar_path.read_text(encoding="utf-8").splitlines()
            ]
            surface_lines = surface_text.split("\n")
            if len(sidecar_rows) != len(surface_lines):
                raise RuntimeError(f"boundary sidecar line count mismatch: {relative}")
            actual_count = 0
            for line_number, (surface_line, sidecar) in enumerate(
                zip(surface_lines, sidecar_rows), start=1
            ):
                expected_offsets = boundary_offsets(surface_line)
                if sidecar != {
                    "boundary_offsets": expected_offsets,
                    "continuous_char_count": sum(
                        1 for character in surface_line if not character.isspace()
                    ),
                    "line_number": line_number,
                }:
                    raise RuntimeError(f"boundary sidecar content mismatch: {relative}")
                actual_count += len(expected_offsets)
            if actual_count != int(boundary_row["boundary_count"]):
                raise RuntimeError(f"boundary count mismatch: {relative}")
            boundary_total += actual_count

    return GenerationResult(
        canonical_files=len(canonical_files),
        representation_files=len(rows),
        boundary_sidecars=len(canonical_files) * len(SCRIPTS),
        boundary_offsets=boundary_total,
        freeze_id=next(iter(freeze_ids)),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate canonical GRETIL representations")
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--canonical-manifest", type=Path, default=DEFAULT_CANONICAL_MANIFEST)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    result = generate_representations(
        canonical_root=args.canonical_root,
        canonical_manifest=args.canonical_manifest,
        output_root=args.output_root,
        manifest_path=args.manifest,
        report_path=args.report,
    )
    print(f"canonical files: {result.canonical_files}")
    print(f"representation files: {result.representation_files}")
    print(f"boundary sidecars: {result.boundary_sidecars}")
    print(f"boundary offsets: {result.boundary_offsets}")


def validate_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate generated representations")
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    result = validate_representations(
        canonical_root=args.canonical_root,
        output_root=args.output_root,
        manifest_path=args.manifest,
    )
    print(f"validated representations: {result.representation_files}")
    print(f"freeze id: {result.freeze_id}")


if __name__ == "__main__":
    main()
