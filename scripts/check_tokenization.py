"""Print a few tokenization examples from a trained SentencePiece model."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Inspect tokenizer output.")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--lines", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    """Load a tokenizer and print pieces for a few non-empty lines."""
    try:
        import sentencepiece as spm
    except ImportError as exc:
        raise SystemExit(
            "sentencepiece is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc

    args = parse_args()
    processor = spm.SentencePieceProcessor(model_file=str(args.model))

    shown = 0
    for line in args.input.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        pieces = processor.encode(line, out_type=str)
        print(line)
        print(" ".join(pieces))
        print()
        shown += 1
        if shown >= args.lines:
            break


if __name__ == "__main__":
    main()
