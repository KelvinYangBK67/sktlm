"""Remove exact standalone source locators from ``vakobhau.txt`` only."""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


IMPLEMENTATION = "vakobhau-standalone-locators-1"
DEFAULT_INPUT_ROOT = Path("data/intermediate/gretil/source_cleaned_gretil_iast")
DEFAULT_OUTPUT_ROOT = Path("data/intermediate/gretil/apparatus_cleaned_gretil_iast")
DEFAULT_REPORT_DIR = Path("reports/cleaning/generated/source_specific_vakobhau")

TARGET_PATH = "6_sastra/3_phil/buddh/vakobhau.txt"
LOCATOR_RE = re.compile(r"^\[\d{3}\|\d{2}(?:-\d{3}\|\d{2})?\]$")

SUMMARY_FILENAME = "vakobhau_cleanup_summary.txt"
FILES_FILENAME = "vakobhau_cleanup_files.csv"
OCCURRENCES_FILENAME = "vakobhau_cleanup_occurrences.csv"


@dataclass(frozen=True, slots=True)
class CleanupResult:
    files_processed: int
    files_changed: int
    locator_lines_removed: int
    input_chars: int
    output_chars: int


def clean_line(line: str, *, path: str) -> tuple[str, bool]:
    """Blank one exact standalone locator, preserving all other material."""

    if path == TARGET_PATH and LOCATOR_RE.fullmatch(line):
        return "", True
    return line, False


def clean_document(text: str, *, path: str) -> tuple[str, list[tuple[int, str]]]:
    output_lines: list[str] = []
    changes: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.split("\n"), start=1):
        cleaned, changed = clean_line(line, path=path)
        output_lines.append(cleaned)
        if changed:
            changes.append((line_number, line))
    return "\n".join(output_lines), changes


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_cleanup(
    *,
    input_root: Path,
    output_root: Path,
    report_dir: Path,
    require_target: bool = True,
) -> CleanupResult:
    if not input_root.is_dir():
        raise FileNotFoundError(f"cleanup input root does not exist: {input_root}")
    if input_root.resolve() == output_root.resolve():
        raise ValueError("input_root and output_root must differ")
    if output_root.exists():
        raise FileExistsError(f"cleanup output root already exists: {output_root}")

    files = tuple(sorted(path for path in input_root.rglob("*.txt") if path.is_file()))
    if not files:
        raise RuntimeError(f"no .txt files found under: {input_root}")
    present_paths = {path.relative_to(input_root).as_posix() for path in files}
    if require_target and TARGET_PATH not in present_paths:
        raise RuntimeError(f"missing vakobhau target path: {TARGET_PATH}")

    output_root.mkdir(parents=True)
    input_chars = 0
    output_chars = 0
    files_changed = 0
    occurrences: list[dict[str, Any]] = []
    file_rows: list[dict[str, Any]] = []

    for source_path in files:
        relative_path = source_path.relative_to(input_root).as_posix()
        destination = output_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        text = source_path.read_text(encoding="utf-8")
        input_chars += len(text)

        if relative_path == TARGET_PATH:
            output, changes = clean_document(text, path=relative_path)
            destination.write_text(output, encoding="utf-8", newline="")
        else:
            output = text
            changes = []
            shutil.copy2(source_path, destination)

        if changes:
            files_changed += 1
        output_chars += len(output)
        file_rows.append(
            {
                "path": relative_path,
                "changed": int(bool(changes)),
                "input_chars": len(text),
                "output_chars": len(output),
                "char_delta": len(output) - len(text),
                "standalone_locator_lines_removed": len(changes),
            }
        )
        occurrences.extend(
            {
                "path": relative_path,
                "line_number": line_number,
                "rule": "standalone_source_locator_removed",
                "removed": removed,
                "replacement": "",
            }
            for line_number, removed in changes
        )

    file_rows.sort(key=lambda row: str(row["path"]))
    _write_csv(
        report_dir / FILES_FILENAME,
        (
            "path",
            "changed",
            "input_chars",
            "output_chars",
            "char_delta",
            "standalone_locator_lines_removed",
        ),
        file_rows,
    )
    _write_csv(
        report_dir / OCCURRENCES_FILENAME,
        ("path", "line_number", "rule", "removed", "replacement"),
        occurrences,
    )

    summary = [
        "Formal GRETIL vakobhau source-specific cleanup",
        "================================================",
        f"implementation: {IMPLEMENTATION}",
        f"input_root: {input_root}",
        f"output_root: {output_root}",
        f"files_processed: {len(files)}",
        f"files_changed: {files_changed}",
        f"standalone_locator_lines_removed: {len(occurrences)}",
        f"input_chars: {input_chars}",
        f"output_chars: {output_chars}",
        f"char_delta: {output_chars - input_chars}",
        "",
        "positive-match policy:",
        f"  target path: {TARGET_PATH}",
        r"  exact grammar: ^\[\d{3}\|\d{2}(?:-\d{3}\|\d{2})?\]$",
        "  only complete physical lines are blanked",
        "  malformed locator-like lines, inline references, variants, and prose remain untouched",
        "  non-target files remain byte/text identical",
        "",
        "The input corpus was not modified.",
        "",
    ]
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / SUMMARY_FILENAME).write_text(
        "\n".join(summary), encoding="utf-8", newline=""
    )

    return CleanupResult(
        files_processed=len(files),
        files_changed=files_changed,
        locator_lines_removed=len(occurrences),
        input_chars=input_chars,
        output_chars=output_chars,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Clean exact vakobhau source locators")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--allow-missing-target", action="store_true")
    args = parser.parse_args(argv)
    result = build_cleanup(
        input_root=args.input_root,
        output_root=args.output_root,
        report_dir=args.report_dir,
        require_target=not args.allow_missing_target,
    )
    print(f"files processed: {result.files_processed}")
    print(f"files changed: {result.files_changed}")
    print(f"locator lines removed: {result.locator_lines_removed}")
    print(f"character delta: {result.output_chars - result.input_chars}")


if __name__ == "__main__":
    main()
