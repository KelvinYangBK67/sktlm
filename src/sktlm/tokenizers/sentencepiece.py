"""SentencePiece tokenizer training helpers and command-line entry point."""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sktlm.tokenizers.base import Encoding, Tokenizer


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _surface_span(text: str, begin: int, end: int, surface: str) -> tuple[int, int]:
    """Interpret SentencePiece offsets as characters, falling back from UTF-8 bytes."""
    if 0 <= begin <= end <= len(text) and text[begin:end] == surface:
        return begin, end
    encoded = text.encode("utf-8")
    if 0 <= begin <= end <= len(encoded):
        try:
            char_begin = len(encoded[:begin].decode("utf-8"))
            char_end = len(encoded[:end].decode("utf-8"))
            return char_begin, char_end
        except UnicodeDecodeError:
            pass
    return max(0, min(begin, len(text))), max(0, min(end, len(text)))


class SentencePieceTokenizer(Tokenizer):
    """Adapter for existing BPE/Unigram models with immutable-proto spans."""

    def __init__(self, model_path: Path, model_type: str) -> None:
        if model_type not in {"bpe", "unigram"}:
            raise ValueError(f"unsupported SentencePiece model type: {model_type}")
        try:
            import sentencepiece as spm
        except ImportError as exc:
            raise RuntimeError("sentencepiece is required for this tokenizer") from exc
        self.model_path = Path(model_path)
        self.model_type = model_type
        self.name = model_type
        self.processor = spm.SentencePieceProcessor(model_file=str(self.model_path))
        bos_id = self.processor.bos_id()
        self.bos_id = bos_id if bos_id >= 0 else None
        eos_id = self.processor.eos_id()
        self.eos_id = eos_id if eos_id >= 0 else None

    @property
    def vocab_size(self) -> int:
        return self.processor.vocab_size()

    def encode(self, text: str) -> Encoding:
        try:
            mapping = self.processor.encode(text, return_type="offset_mapping")
        except (TypeError, ValueError) as exc:
            message = str(exc)
            if "return_type" not in message and "offset_mapping" not in message:
                raise
        else:
            return Encoding(
                ids=tuple(int(token_id) for token_id in mapping["ids"]),
                pieces=tuple(str(piece) for piece in mapping["pieces"]),
                spans=tuple((int(begin), int(end)) for begin, end in mapping["offsets"]),
            )

        # SentencePiece before the offset-mapping API exposed the same character
        # offsets through an immutable proto. Keep that path for older supported
        # installations without calling the API removed in SentencePiece 0.2.2.
        proto = self.processor.encode_as_immutable_proto(text)
        ids: list[int] = []
        pieces: list[str] = []
        spans: list[tuple[int, int]] = []
        for item in proto.pieces:
            ids.append(int(item.id))
            pieces.append(str(item.piece))
            spans.append(_surface_span(text, int(item.begin), int(item.end), str(item.surface)))
        return Encoding(tuple(ids), tuple(pieces), tuple(spans))

    def decode(self, ids: list[int] | tuple[int, ...]) -> str:
        return self.processor.decode(list(ids))

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            **super().fingerprint_payload(),
            "model_type": self.model_type,
            "model_path": str(self.model_path.as_posix()),
            "model_sha256": _file_sha256(self.model_path),
        }


class SentencePieceBPETokenizer(SentencePieceTokenizer):
    def __init__(self, model_path: Path) -> None:
        super().__init__(model_path, "bpe")


class SentencePieceUnigramTokenizer(SentencePieceTokenizer):
    def __init__(self, model_path: Path) -> None:
        super().__init__(model_path, "unigram")


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
        shuffle_input_sentence=False,
        num_threads=1,
    )


def train_sentencepiece_from_texts(
    texts: Iterable[str],
    output_prefix: Path,
    vocab_size: int,
    model_type: str,
) -> Path:
    """Train deterministically from selected train segments without materializing them."""
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    input_path = output_prefix.with_name(f"{output_prefix.name}_segments.txt")
    try:
        text_count = 0
        with input_path.open("w", encoding="utf-8", newline="\n") as handle:
            for text in texts:
                handle.write(text)
                handle.write("\n")
                text_count += 1
        if text_count == 0:
            raise ValueError("SentencePiece training requires at least one train segment")
        train_sentencepiece([input_path], output_prefix, vocab_size, model_type)
    finally:
        input_path.unlink(missing_ok=True)
    return output_prefix.with_suffix(".model")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Train a tiny SentencePiece tokenizer.")
    parser.add_argument("--input-file", type=Path, help="Single normalized text file to train on.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=Path("artifacts/tokenizers/sanskrit_spm"),
    )
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
