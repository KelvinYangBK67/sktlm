"""Build a compact review report from the canonical anomaly occurrence CSV."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_INPUT = Path(
    "reports/cleaning/generated/initial_audit/gretil_canonical_flagged_occurrences.csv"
)

DEFAULT_OUTPUT = Path(
    "reports/cleaning/generated/initial_audit/gretil_canonical_anomaly_samples.txt"
)

SAMPLES_PER_CHARACTER = 20
TOP_FILES = 15


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize canonical anomaly occurrences into "
            "compact human-review samples."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=SAMPLES_PER_CHARACTER,
    )

    args = parser.parse_args(argv)

    if not args.input.is_file():
        raise FileNotFoundError(
            f"occurrence report not found: {args.input}"
        )

    total_counts: Counter[tuple[str, str]] = Counter()

    document_sets: dict[
        tuple[str, str],
        set[str],
    ] = defaultdict(set)

    file_counts: dict[
        tuple[str, str],
        Counter[str],
    ] = defaultdict(Counter)

    samples: dict[
        tuple[str, str],
        list[tuple[str, str, str]],
    ] = defaultdict(list)

    seen_sample_lines: dict[
        tuple[str, str],
        set[tuple[str, str]],
    ] = defaultdict(set)

    with args.input.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        for row in reader:
            flag_type = row["flag_type"]
            path = row["path"]
            line_number = row["line_number"]
            line_text = row["line_text"]

            count = int(row["count"])

            # "matches" contains the distinct suspicious characters found
            # on this line for this flag type, separated by spaces.
            #
            # For visible single characters this is straightforward.
            # Control characters are rendered as <U+XXXX>.
            match_items = [
                item
                for item in row["matches"].split(" ")
                if item
            ]

            for match in match_items:
                key = (flag_type, match)

                # The occurrence CSV aggregates by line and flag type, so
                # row["count"] cannot tell us the exact per-character count
                # when more than one distinct match appears. For review
                # purposes, count the line-level occurrence conservatively.
                total_counts[key] += count
                document_sets[key].add(path)
                file_counts[key][path] += count

                sample_identity = (
                    path,
                    line_text,
                )

                if (
                    len(samples[key]) < args.samples
                    and sample_identity
                    not in seen_sample_lines[key]
                ):
                    seen_sample_lines[key].add(
                        sample_identity
                    )

                    samples[key].append(
                        (
                            path,
                            line_number,
                            line_text,
                        )
                    )

    keys = sorted(
        total_counts,
        key=lambda key: (
            key[0],
            -total_counts[key],
            key[1],
        ),
    )

    lines: list[str] = [
        "Formal GRETIL canonical anomaly samples",
        "========================================",
        "",
        f"source: {args.input}",
        f"samples_per_character: {args.samples}",
        "",
    ]

    current_flag_type: str | None = None

    for key in keys:
        flag_type, match = key

        if flag_type != current_flag_type:
            if current_flag_type is not None:
                lines.append("")

            lines.extend(
                [
                    "",
                    "#" * 72,
                    f"# {flag_type}",
                    "#" * 72,
                    "",
                ]
            )

            current_flag_type = flag_type

        lines.extend(
            [
                f"=== {match} ===",
                f"approx_occurrences: {total_counts[key]}",
                f"documents: {len(document_sets[key])}",
                "",
                "top_files:",
            ]
        )

        for path, count in file_counts[
            key
        ].most_common(TOP_FILES):
            lines.append(
                f"  {count:>8}  {path}"
            )

        lines.extend(
            [
                "",
                "samples:",
            ]
        )

        for path, line_number, line_text in samples[key]:
            lines.append(
                f"[{path}:{line_number}]"
            )
            lines.append(
                line_text
            )
            lines.append("")

        lines.append("")

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(
        f"wrote compact anomaly sample report: "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()
