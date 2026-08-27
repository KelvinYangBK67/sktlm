"""Minimal SentencePiece tokenizer training entry point."""

from __future__ import annotations

import argparse
from pathlib import Path


def iter_processed_texts(data_dir: Path) -> list[Path]:
    """Return processed text files that will be used for tokenizer training."""
    return sorted(path for path in data_dir.rglob("*.txt") if path.is_file())


def train_sentencepiece(
    input_files: list[Path],
    output_prefix: Path,
    vocab_size: int,
    model_type: str,
) -> None:
    """Train a tiny SentencePiece tokenizer on normalized text files."""
    try:
        import sentencepiece as spm
    except ImportError as exc:
        raise SystemExit(
            "sentencepiece is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc

    if not input_files:
        raise SystemExit("No input text files found.")
    empty_files = [path for path in input_files if path.stat().st_size == 0]
    if empty_files:
        names = ", ".join(str(path) for path in empty_files)
        raise SystemExit(f"Input text file(s) are empty: {names}")

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    input_arg = ",".join(str(path) for path in input_files)

    spm.SentencePieceTrainer.train(
        input=input_arg,
        model_prefix=str(output_prefix),
        vocab_size=vocab_size,
        model_type=model_type,
        character_coverage=1.0,
        normalization_rule_name="identity",
        bos_id=1,
        eos_id=2,
        unk_id=0,
        pad_id=3,
        hard_vocab_limit=False,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Train a tiny SentencePiece tokenizer.")
    parser.add_argument("--input-file", type=Path, help="Single normalized text file to train on.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-prefix", type=Path, default=Path("tokenizer/sanskrit_spm"))
    parser.add_argument("--vocab-size", type=int, default=512)
    parser.add_argument("--model-type", choices=("unigram", "bpe"), default="unigram")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List input files without training.",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the tokenizer training skeleton."""
    args = parse_args()
    input_files = [args.input_file] if args.input_file else iter_processed_texts(args.data_dir)

    print(f"Found {len(input_files)} processed text file(s).")
    for path in input_files:
        print(path)

    if args.dry_run:
        return

    train_sentencepiece(input_files, args.output_prefix, args.vocab_size, args.model_type)


if __name__ == "__main__":
    main()
