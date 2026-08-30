"""Triage residual GRETIL findings without modifying corpus text.

Every residual character reported by :mod:`.residual` is assigned to exactly
one research-action category. The mapping is deliberately conservative: it
prioritizes review and never authorizes deletion or normalization.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from sktlm.corpus.gretil.cleaning.residual import DEFAULT_INPUT_ROOT, Hit, audit_text


IMPLEMENTATION = "residual-triage-1"
DEFAULT_REPORT_DIR = Path("reports/cleaning/generated/residual_triage")

SUMMARY_FILENAME = "residual_triage_summary.txt"
FILES_FILENAME = "residual_triage_files.csv"
FAMILIES_FILENAME = "residual_triage_families.csv"

MECHANICAL_STRUCTURAL = "mechanical_structural"
FAMILY_APPARATUS_EDITORIAL = "family_apparatus_editorial"
SOURCE_SPECIFIC_CONTAMINATION = "source_specific_contamination"
MIXED_LANGUAGE_SERIOUS_ANOMALY = "mixed_language_serious_anomaly"

TRIAGE_CATEGORIES = (
    MECHANICAL_STRUCTURAL,
    FAMILY_APPARATUS_EDITORIAL,
    SOURCE_SPECIFIC_CONTAMINATION,
    MIXED_LANGUAGE_SERIOUS_ANOMALY,
)

MECHANICAL_CATEGORIES = frozenset({"CONTROL_OR_FORMAT", "ANGLE", "UNDERSCORE"})
SERIOUS_CATEGORIES = frozenset({"NON_IAST_LATIN"})

# Positive path matches only. These sources are singled out because the current
# residual report or the Pass-3B exclusions show concentrated, source-local
# layout/editorial behavior. The list scopes review; it is not a cleanup rule.
SOURCE_SPECIFIC_PREFIXES = (
    "2_epic/mbh/ext/hv_",
    "4_rellit/buddh/srabhu_u.txt",
    "4_rellit/vaisn/vaimp__u.txt",
    "5_poetry/4_narr/sokss_pu.txt",
    "5_poetry/5_subhas/vidsrgpu.txt",
    "6_sastra/3_phil/buddh/vakobhau.txt",
    "6_sastra/7_ayur/vagaah_u.txt",
)


@dataclass(frozen=True, slots=True)
class TriageResult:
    files_processed: int
    flagged_files: int
    flagged_occurrences: int
    families: int


def is_source_specific(path: str) -> bool:
    """Return whether *path* is in an explicitly reviewed source scope."""

    return any(path.startswith(prefix) for prefix in SOURCE_SPECIFIC_PREFIXES)


def classify_hit(hit: Hit) -> str:
    """Assign one action category to an existing residual-audit hit."""

    if hit.category in SERIOUS_CATEGORIES:
        return MIXED_LANGUAGE_SERIOUS_ANOMALY
    if hit.category in MECHANICAL_CATEGORIES:
        return MECHANICAL_STRUCTURAL
    if is_source_specific(hit.path):
        return SOURCE_SPECIFIC_CONTAMINATION
    return FAMILY_APPARATUS_EDITORIAL


def source_family(path: str) -> str:
    """Return a stable aggregation family for a canonical relative path."""

    if path.startswith("2_epic/mbh/ext/hv_"):
        return "2_epic/mbh/ext/hv"
    parent = PurePosixPath(path).parent.as_posix()
    return parent if parent != "." else "(root)"


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...],
    rows: Iterable[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_triage(*, input_root: Path, report_dir: Path) -> TriageResult:
    """Audit *input_root* and write deterministic file/family triage reports."""

    if not input_root.is_dir():
        raise FileNotFoundError(f"triage input root does not exist: {input_root}")

    files = tuple(sorted(path for path in input_root.rglob("*.txt") if path.is_file()))
    if not files:
        raise RuntimeError(f"no .txt files found under: {input_root}")

    file_rows: list[dict[str, Any]] = []
    family_counts: dict[str, Counter[str]] = defaultdict(Counter)
    family_files: dict[str, set[str]] = defaultdict(set)
    totals: Counter[str] = Counter()

    for source_path in files:
        relative_path = source_path.relative_to(input_root).as_posix()
        text = source_path.read_text(encoding="utf-8")
        _, hits = audit_text(text, relative_path)

        counts: Counter[str] = Counter(classify_hit(hit) for hit in hits)
        total = sum(counts.values())
        family = source_family(relative_path)

        if total:
            family_files[family].add(relative_path)
        family_counts[family].update(counts)
        totals.update(counts)

        row: dict[str, Any] = {
            "path": relative_path,
            "source_family": family,
            "flagged_occurrences": total,
            "primary_triage": (
                max(TRIAGE_CATEGORIES, key=lambda category: (counts[category], -TRIAGE_CATEGORIES.index(category)))
                if total
                else "clean"
            ),
        }
        row.update({category: counts[category] for category in TRIAGE_CATEGORIES})
        file_rows.append(row)

    file_rows.sort(key=lambda row: (-int(row["flagged_occurrences"]), str(row["path"])))

    family_rows: list[dict[str, Any]] = []
    for family, counts in family_counts.items():
        total = sum(counts.values())
        row = {
            "source_family": family,
            "flagged_occurrences": total,
            "flagged_files": len(family_files[family]),
            "share_of_all_flags": f"{total / sum(totals.values()):.8f}" if totals else "0.00000000",
        }
        row.update({category: counts[category] for category in TRIAGE_CATEGORIES})
        family_rows.append(row)
    family_rows.sort(key=lambda row: (-int(row["flagged_occurrences"]), str(row["source_family"])))

    file_fields = (
        "path",
        "source_family",
        "flagged_occurrences",
        "primary_triage",
        *TRIAGE_CATEGORIES,
    )
    family_fields = (
        "source_family",
        "flagged_occurrences",
        "flagged_files",
        "share_of_all_flags",
        *TRIAGE_CATEGORIES,
    )
    _write_csv(report_dir / FILES_FILENAME, file_fields, file_rows)
    _write_csv(report_dir / FAMILIES_FILENAME, family_fields, family_rows)

    flagged_files = sum(1 for row in file_rows if int(row["flagged_occurrences"]))
    lines = [
        "Formal GRETIL residual triage",
        "==============================",
        f"implementation: {IMPLEMENTATION}",
        f"input_root: {input_root}",
        f"files_processed: {len(files)}",
        f"flagged_files: {flagged_files}",
        f"flagged_occurrences: {sum(totals.values())}",
        f"source_families: {len(family_rows)}",
        "",
        "triage totals:",
    ]
    for category in TRIAGE_CATEGORIES:
        lines.append(f"  {category}: {totals[category]}")
    lines.extend(["", "top source families:"])
    for row in family_rows[:25]:
        lines.append(
            f"  {int(row['flagged_occurrences']):>9}  {row['source_family']}  "
            f"({float(row['share_of_all_flags']):.2%})"
        )
    lines.extend(
        [
            "",
            "policy:",
            "  every residual occurrence is assigned to exactly one triage category",
            "  source-specific scopes are explicit positive path matches",
            "  flags prioritize review and do not authorize deletion or normalization",
            "  strict flagged_files=0 is not a cleanup objective",
            "",
            "The triaged corpus was not modified.",
            "",
        ]
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / SUMMARY_FILENAME).write_text("\n".join(lines), encoding="utf-8")

    return TriageResult(
        files_processed=len(files),
        flagged_files=flagged_files,
        flagged_occurrences=sum(totals.values()),
        families=len(family_rows),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Triage post-cleaning GRETIL residuals")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args(argv)
    result = build_triage(input_root=args.input_root, report_dir=args.report_dir)
    print(f"files processed: {result.files_processed}")
    print(f"flagged files: {result.flagged_files}")
    print(f"flagged occurrences: {result.flagged_occurrences}")
    print(f"source families: {result.families}")


if __name__ == "__main__":
    main()
