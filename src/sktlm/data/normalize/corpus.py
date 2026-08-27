"""Batch-normalize a raw text corpus and write a compact summary report."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from sktlm.data.normalize.devanagari import normalize_text


@dataclass
class FileStats:
    """Per-file normalization statistics."""

    relative_path: Path
    raw_chars: int
    normalized_chars: int
    normalized_lines: int

    @property
    def reduction_ratio(self) -> float:
        """Return the fraction of raw characters removed."""
        if self.raw_chars == 0:
            return 0.0
        return max(0.0, 1.0 - (self.normalized_chars / self.raw_chars))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Batch-normalize a corpus of .txt files.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw/ambuda-text"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/ambuda-text"))
    parser.add_argument("--report-dir", type=Path, default=Path("data/_reports"))
    parser.add_argument("--report-name", default="ambuda_normalization_summary.txt")
    parser.add_argument("--top-n", type=int, default=10)
    return parser.parse_args()


def normalized_line_count(text: str) -> int:
    """Count lines in normalized text, treating an empty file as zero lines."""
    if not text:
        return 0
    return len(text.splitlines())


def suspicious_notes(stats: FileStats) -> list[str]:
    """Return conservative warnings for suspicious normalized outputs."""
    notes: list[str] = []
    if stats.normalized_chars < 50:
        notes.append("very short normalized output")
    if stats.reduction_ratio >= 0.70:
        notes.append(f"high reduction ratio {stats.reduction_ratio:.1%}")
    if stats.normalized_lines <= 1 and stats.normalized_chars > 500:
        notes.append("long single-line output")
    return notes


def write_report(
    output_path: Path,
    total_files: int,
    successes: list[FileStats],
    failures: list[tuple[Path, str]],
    top_n: int,
) -> None:
    """Write a compact corpus summary report."""
    total_chars = sum(item.normalized_chars for item in successes)
    total_lines = sum(item.normalized_lines for item in successes)
    longest = sorted(successes, key=lambda item: item.normalized_chars, reverse=True)[:top_n]
    shortest = sorted(successes, key=lambda item: item.normalized_chars)[:top_n]

    lines: list[str] = [
        "Corpus Summary: ambuda-text",
        "",
        f"Total txt files: {total_files}",
        f"Successful files: {len(successes)}",
        f"Failed files: {len(failures)}",
        f"Total normalized characters: {total_chars}",
        f"Total normalized lines: {total_lines}",
        "",
        f"Longest files (top {top_n}):",
    ]

    for item in longest:
        lines.append(f"- {item.relative_path}: {item.normalized_chars} chars, {item.normalized_lines} lines")

    lines.extend(["", f"Shortest files (top {top_n}):"])
    for item in shortest:
        lines.append(f"- {item.relative_path}: {item.normalized_chars} chars, {item.normalized_lines} lines")

    lines.extend(["", "Suspicious files:"])
    suspicious_count = 0
    for item in successes:
        notes = suspicious_notes(item)
        if notes:
            suspicious_count += 1
            note_text = "; ".join(notes)
            lines.append(f"- {item.relative_path}: {note_text}")
    if suspicious_count == 0:
        lines.append("- none")

    lines.extend(["", "Failures:"])
    if failures:
        for relative_path, error in failures:
            lines.append(f"- {relative_path}: {error}")
    else:
        lines.append("- none")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_failures(output_path: Path, failures: list[tuple[Path, str]]) -> None:
    """Write failures to a separate file when any failures occur."""
    if not failures:
        return
    lines = ["Normalization Failures", ""]
    for relative_path, error in failures:
        lines.append(f"- {relative_path}: {error}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """Normalize all .txt files from the input directory."""
    args = parse_args()
    input_dir = args.input_dir
    output_dir = args.output_dir
    report_dir = args.report_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    input_files = sorted(path for path in input_dir.rglob("*.txt") if path.is_file())
    successes: list[FileStats] = []
    failures: list[tuple[Path, str]] = []

    for input_path in input_files:
        relative_path = input_path.relative_to(input_dir)
        output_path = output_dir / relative_path
        try:
            raw_text = input_path.read_text(encoding="utf-8")
            normalized = normalize_text(raw_text)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(normalized, encoding="utf-8")
            successes.append(
                FileStats(
                    relative_path=relative_path,
                    raw_chars=len(raw_text),
                    normalized_chars=len(normalized),
                    normalized_lines=normalized_line_count(normalized),
                )
            )
        except Exception as exc:  # noqa: BLE001 - batch jobs should keep going.
            failures.append((relative_path, f"{type(exc).__name__}: {exc}"))

    report_path = report_dir / args.report_name
    write_report(report_path, len(input_files), successes, failures, args.top_n)
    failures_path = report_dir / "ambuda_normalization_failures.txt"
    write_failures(failures_path, failures)

    print(f"Input files: {len(input_files)}")
    print(f"Successful files: {len(successes)}")
    print(f"Failed files: {len(failures)}")
    print(f"Output directory: {output_dir}")
    print(f"Summary report: {report_path}")
    if failures:
        print(f"Failures report: {failures_path}")


if __name__ == "__main__":
    main()
