"""Positive-match cleanup for two Harivamsa critical-edition exports.

Only complete, line-final edition locators are removed. Sanskrit verse text,
dandas, speaker labels, variants, brackets, and every non-matching line remain
untouched for later review.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


IMPLEMENTATION = "harivamsa-line-final-locators-1"
DEFAULT_INPUT_ROOT = Path(
    "data/intermediate/gretil/pass3b_v3_hyphen_normalized_gretil_iast"
)
DEFAULT_OUTPUT_ROOT = Path("data/intermediate/gretil/source_cleaned_gretil_iast")
DEFAULT_REPORT_DIR = Path("reports/cleaning/generated/source_specific_harivamsa")

APPENDIX_PATH = "2_epic/mbh/ext/hv_apppu.txt"
CRITICAL_PATH = "2_epic/mbh/ext/hv_conpu.txt"
TARGET_PATHS = frozenset({APPENDIX_PATH, CRITICAL_PATH})

APPENDIX_SUFFIX_RE = re.compile(
    r"\s+HV\s+App\.[A-Za-z0-9.,*]+\s+\|{1,2}\s*$"
)
CRITICAL_SUFFIX_RE = re.compile(
    r"\s+\*HV\s+[A-Za-z0-9.]+\*[A-Za-z0-9.:]+\s+\|{1,2}\s*$"
)

SUMMARY_FILENAME = "harivamsa_cleanup_summary.txt"
FILES_FILENAME = "harivamsa_cleanup_files.csv"
OCCURRENCES_FILENAME = "harivamsa_cleanup_occurrences.csv"


@dataclass(frozen=True, slots=True)
class Change:
    path: str
    line_number: int
    rule: str
    removed: str
    line_before: str
    line_after: str


@dataclass(frozen=True, slots=True)
class CleanupResult:
    files_processed: int
    files_changed: int
    occurrences_removed: int
    input_chars: int
    output_chars: int


def clean_line(line: str, *, path: str) -> tuple[str, str | None, str]:
    """Remove one approved locator suffix and return line, rule, removed text."""

    if path == APPENDIX_PATH:
        regex = APPENDIX_SUFFIX_RE
        rule = "appendix_line_final_locator_removed"
    elif path == CRITICAL_PATH:
        regex = CRITICAL_SUFFIX_RE
        rule = "critical_line_final_locator_removed"
    else:
        return line, None, ""

    match = regex.search(line)
    if match is None:
        return line, None, ""

    prefix = line[: match.start()].rstrip()
    # The edition locator must follow an already complete Sanskrit pada/verse.
    # This additional positive condition prevents removal from metadata-only
    # lines and malformed embedded markers.
    if not prefix.endswith("|"):
        return line, None, ""

    return prefix, rule, line[match.start() :]


def clean_document(text: str, *, path: str) -> tuple[str, list[Change]]:
    """Apply the scoped line rule while preserving LF layout exactly."""

    output_lines: list[str] = []
    changes: list[Change] = []
    for line_number, line in enumerate(text.split("\n"), start=1):
        cleaned, rule, removed = clean_line(line, path=path)
        output_lines.append(cleaned)
        if rule is not None:
            changes.append(
                Change(
                    path=path,
                    line_number=line_number,
                    rule=rule,
                    removed=removed,
                    line_before=line,
                    line_after=cleaned,
                )
            )
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
    require_all_targets: bool = True,
) -> CleanupResult:
    """Rebuild the corpus with the two path-scoped HV locator rules."""

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
    missing_targets = sorted(TARGET_PATHS - present_paths)
    if require_all_targets and missing_targets:
        raise RuntimeError("missing Harivamsa target paths: " + ", ".join(missing_targets))

    output_root.mkdir(parents=True)
    file_rows: list[dict[str, Any]] = []
    occurrence_rows: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    files_changed = 0
    input_chars = 0
    output_chars = 0

    for source_path in files:
        relative_path = source_path.relative_to(input_root).as_posix()
        destination = output_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        text = source_path.read_text(encoding="utf-8")
        input_chars += len(text)

        if relative_path in TARGET_PATHS:
            output, changes = clean_document(text, path=relative_path)
            destination.write_text(output, encoding="utf-8", newline="")
        else:
            output = text
            changes = []
            shutil.copy2(source_path, destination)

        if changes:
            files_changed += 1
        output_chars += len(output)
        counts = Counter(change.rule for change in changes)
        totals.update(counts)
        file_rows.append(
            {
                "path": relative_path,
                "changed": int(bool(changes)),
                "input_chars": len(text),
                "output_chars": len(output),
                "char_delta": len(output) - len(text),
                "appendix_line_final_locator_removed": counts[
                    "appendix_line_final_locator_removed"
                ],
                "critical_line_final_locator_removed": counts[
                    "critical_line_final_locator_removed"
                ],
            }
        )
        occurrence_rows.extend(
            {
                "path": change.path,
                "line_number": change.line_number,
                "rule": change.rule,
                "removed": change.removed,
                "line_before": change.line_before,
                "line_after": change.line_after,
            }
            for change in changes
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
            "appendix_line_final_locator_removed",
            "critical_line_final_locator_removed",
        ),
        file_rows,
    )
    _write_csv(
        report_dir / OCCURRENCES_FILENAME,
        ("path", "line_number", "rule", "removed", "line_before", "line_after"),
        occurrence_rows,
    )

    summary_lines = [
        "Formal GRETIL Harivamsa source-specific cleanup",
        "================================================",
        f"implementation: {IMPLEMENTATION}",
        f"input_root: {input_root}",
        f"output_root: {output_root}",
        f"files_processed: {len(files)}",
        f"files_changed: {files_changed}",
        f"input_chars: {input_chars}",
        f"output_chars: {output_chars}",
        f"char_delta: {output_chars - input_chars}",
        "",
        "rule totals:",
        "  appendix_line_final_locator_removed: "
        f"{totals['appendix_line_final_locator_removed']}",
        "  critical_line_final_locator_removed: "
        f"{totals['critical_line_final_locator_removed']}",
        f"  total: {sum(totals.values())}",
        "",
        "positive-match policy:",
        f"  appendix path: {APPENDIX_PATH}",
        f"  critical path: {CRITICAL_PATH}",
        "  match must be a complete supported locator at physical line end",
        "  retained prefix must end in danda before removal",
        "  non-target files and non-matching target lines remain byte/text identical",
        "  variants, speaker labels, brackets, and suspicious characters remain untouched",
        "",
        "The input corpus was not modified.",
        "",
    ]
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / SUMMARY_FILENAME).write_text(
        "\n".join(summary_lines), encoding="utf-8", newline=""
    )

    return CleanupResult(
        files_processed=len(files),
        files_changed=files_changed,
        occurrences_removed=sum(totals.values()),
        input_chars=input_chars,
        output_chars=output_chars,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Clean explicit Harivamsa line locators")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--allow-missing-targets", action="store_true")
    args = parser.parse_args(argv)
    result = build_cleanup(
        input_root=args.input_root,
        output_root=args.output_root,
        report_dir=args.report_dir,
        require_all_targets=not args.allow_missing_targets,
    )
    print(f"files processed: {result.files_processed}")
    print(f"files changed: {result.files_changed}")
    print(f"occurrences removed: {result.occurrences_removed}")
    print(f"character delta: {result.output_chars - result.input_chars}")


if __name__ == "__main__":
    main()
