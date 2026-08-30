"""Create a weighted tokenizer training corpus from a corpus manifest.

Weights are applied as deterministic line sampling. This keeps the generated
training file reproducible while allowing broad corpora, duplicates, and layers
to contribute at different rates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from pathlib import Path


SENTENCE_BOUNDARY_RE = re.compile(r"[^।॥]+(?:॥|।)?")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build weighted tokenizer corpus.")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/corpus_manifest.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/tokenizer_corpora/weighted_full.txt"))
    parser.add_argument("--report", type=Path, default=Path("reports/baselines/weighted_tokenizer_corpus_summary.txt"))
    parser.add_argument("--seed", default="sanskrit_llm_weighted_tokenizer_v1")
    return parser.parse_args()


def normalize_commas(line: str) -> str:
    """Map legal residual commas to danda and delete illegal comma residue.

    A legal comma is a comma not at line start and not preceded by whitespace.
    Line-start commas and commas after whitespace are treated as residue.
    """
    output: list[str] = []
    for char in line:
        if char != ",":
            output.append(char)
            continue
        if not output or output[-1].isspace():
            continue
        output.append("।")
    return "".join(output)


def split_on_danda(line: str) -> list[str]:
    """Split a line on danda/double danda, keeping the boundary mark."""
    pieces = [match.group(0).strip() for match in SENTENCE_BOUNDARY_RE.finditer(line)]
    return [piece for piece in pieces if piece]


def include_line(seed: str, path: str, line_number: int, weight: float) -> bool:
    """Deterministically include a line according to its file weight."""
    if weight >= 1.0:
        return True
    if weight <= 0.0:
        return False
    key = f"{seed}|{path}|{line_number}".encode("utf-8")
    value = int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big") / 2**64
    return value < weight


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(args.manifest.read_text(encoding="utf-8").splitlines()))
    stats: dict[str, dict[str, float]] = {}
    total_input_lines = 0
    total_output_lines = 0
    total_output_chars = 0
    total_split_segments = 0

    with args.output.open("w", encoding="utf-8", newline="\n") as out:
        for row in rows:
            path = Path(row["path"])
            weight = float(row["final_weight"])
            layer = row["layer"]
            source = row["source"]
            key = f"{source}:{layer}"
            layer_stats = stats.setdefault(
                key,
                {"files": 0, "input_lines": 0, "output_lines": 0, "output_chars": 0, "weight_sum": 0.0},
            )
            layer_stats["files"] += 1
            layer_stats["weight_sum"] += weight

            for line_number, raw_line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                total_input_lines += 1
                layer_stats["input_lines"] += 1
                line = normalize_commas(raw_line).strip()
                if not line:
                    continue
                if not include_line(args.seed, row["path"], line_number, weight):
                    continue
                segments = split_on_danda(line)
                total_split_segments += max(0, len(segments) - 1)
                for segment in segments:
                    out.write(segment)
                    out.write("\n")
                    total_output_lines += 1
                    total_output_chars += len(segment) + 1
                    layer_stats["output_lines"] += 1
                    layer_stats["output_chars"] += len(segment) + 1

    lines = [
        "Weighted Tokenizer Corpus Summary",
        "",
        f"Manifest: {args.manifest}",
        f"Output: {args.output}",
        f"Seed: {args.seed}",
        f"Input files: {len(rows)}",
        f"Input lines: {total_input_lines}",
        f"Output lines: {total_output_lines}",
        f"Output characters: {total_output_chars}",
        f"Extra lines from danda/double-danda splitting: {total_split_segments}",
        "",
        "Comma rule:",
        "- legal residual comma -> danda",
        "- line-start comma or comma preceded by whitespace -> deleted",
        "",
        "Line splitting:",
        "- split on danda and double danda",
        "- keep the boundary mark at the end of each emitted line",
        "",
        "Source/layer totals:",
    ]
    for key, item in sorted(stats.items()):
        avg_weight = item["weight_sum"] / item["files"] if item["files"] else 0
        lines.append(
            f"- {key}: files={int(item['files'])}, avg_weight={avg_weight:.3f}, "
            f"input_lines={int(item['input_lines'])}, output_lines={int(item['output_lines'])}, "
            f"output_chars={int(item['output_chars'])}"
        )
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Output: {args.output}")
    print(f"Report: {args.report}")
    print(f"Output lines: {total_output_lines}")
    print(f"Output characters: {total_output_chars}")


if __name__ == "__main__":
    main()
