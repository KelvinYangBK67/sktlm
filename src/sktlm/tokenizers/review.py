"""Extract existing vocabulary diagnostic categories for review."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


SPACE_MARK = "▁"
INDEPENDENT_VOWELS = set("अआइईउऊऋॠऌॡएऐओऔ")
DEPENDENT_VOWELS = set("ािीुूृॄॢॣेैोौ")
CONSONANTS = set("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहळ")
SPECIAL_SIGNS = set("ंःऽ।॥ॐ")
VIRAMA = "्"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract vocab pieces for manual review.")
    parser.add_argument(
        "--vocab",
        type=Path,
        default=Path("artifacts/tokenizers/weighted_unigram_24000_danda_split.vocab"),
    )
    parser.add_argument(
        "--txt",
        type=Path,
        default=Path("reports/baselines/vocab_review_weighted_unigram_24000_danda_split.txt"),
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("reports/baselines/vocab_review_weighted_unigram_24000_danda_split.csv"),
    )
    parser.add_argument("--limit", type=int, default=300, help="Maximum examples per category in the text report.")
    return parser.parse_args()


def clean_piece(piece: str) -> str:
    """Remove SentencePiece's leading space marker for linguistic checks."""
    return piece.lstrip(SPACE_MARK)


def vowel_count(piece: str) -> int:
    """Count independent vowels and dependent vowel signs."""
    return sum(1 for char in piece if char in INDEPENDENT_VOWELS or char in DEPENDENT_VOWELS)


def is_simple_cv(piece: str) -> bool:
    """Return true for a bare consonant or consonant + dependent vowel sign."""
    if len(piece) == 1:
        return piece in CONSONANTS
    if len(piece) == 2:
        return piece[0] in CONSONANTS and piece[1] in DEPENDENT_VOWELS
    return False


def read_vocab(path: Path) -> list[dict[str, str]]:
    """Read a SentencePiece vocab file."""
    rows: list[dict[str, str]] = []
    for rank, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "\t" in line:
            piece, score = line.split("\t", 1)
        else:
            piece, score = line, ""
        rows.append(
            {
                "rank": str(rank),
                "piece": piece,
                "clean_piece": clean_piece(piece),
                "score": score,
            }
        )
    return rows


def categories(row: dict[str, str]) -> list[str]:
    """Return review categories for one vocab row."""
    piece = row["piece"]
    clean = row["clean_piece"]
    cats: list[str] = []
    if clean and clean[0] in DEPENDENT_VOWELS:
        cats.append("starts_with_dependent_vowel")
    if any(char in SPECIAL_SIGNS for char in clean):
        cats.append("contains_special_A")
    if is_simple_cv(clean):
        cats.append("simple_cv")
    if clean.endswith(VIRAMA):
        cats.append("ends_with_virama")
    return cats


def main() -> None:
    args = parse_args()
    rows = read_vocab(args.vocab)

    review_rows: list[dict[str, str]] = []
    grouped: dict[str, list[dict[str, str]]] = {
        "starts_with_dependent_vowel": [],
        "contains_special_A": [],
        "simple_cv": [],
        "ends_with_virama": [],
    }

    for row in rows:
        cats = categories(row)
        if not cats:
            continue
        output_row = {
            **row,
            "categories": ";".join(cats),
            "vowel_count": str(vowel_count(row["clean_piece"])),
        }
        review_rows.append(output_row)
        for cat in cats:
            grouped[cat].append(output_row)

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["rank", "piece", "clean_piece", "score", "vowel_count", "categories"],
        )
        writer.writeheader()
        writer.writerows(review_rows)

    lines = [
        "Vocab Review Extract",
        "",
        f"Vocab: {args.vocab}",
        f"CSV: {args.csv}",
        f"Total vocab rows: {len(rows)}",
        f"Rows matching at least one category: {len(review_rows)}",
        "",
        "Definitions:",
        "- V: independent Devanagari vowels",
        "- V': dependent Devanagari vowel signs",
        "- A: anusvara, visarga, avagraha, danda, double danda, om",
        "- Simple CV: one consonant, or one consonant plus one dependent vowel sign",
        "- VO ending: virama-ending piece",
        "- Start/end checks ignore SentencePiece leading space marker ▁",
        "",
        "Category counts:",
    ]
    for cat, items in grouped.items():
        lines.append(f"- {cat}: {len(items)}")

    for cat, items in grouped.items():
        lines.extend(["", f"[{cat}] first {min(args.limit, len(items))} by vocab rank"])
        for item in items[: args.limit]:
            lines.append(
                f"{item['rank']}\t{item['piece']}\tclean={item['clean_piece']}\t"
                f"vowels={item['vowel_count']}\tscore={item['score']}"
            )

    args.txt.parent.mkdir(parents=True, exist_ok=True)
    args.txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Text report: {args.txt}")
    print(f"CSV report: {args.csv}")
    print(f"Matched rows: {len(review_rows)}")
    for cat, items in grouped.items():
        print(f"{cat}: {len(items)}")


if __name__ == "__main__":
    main()
