"""Deterministic atom-to-private-use mapping for atom-aware SentencePiece models."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sktlm.tokenizers.base import Encoding, Tokenizer


PRETOKENIZATION_DELIMITER = "␞"
MAX_SENTENCE_LENGTH = 100_000
PRIVATE_USE_RANGES = (
    (0xE000, 0xF8FF),
    (0xF0000, 0xFFFFD),
    (0x100000, 0x10FFFD),
)
SURROGATE_SENTENCEPIECE_TRAINER_CONTRACT = {
    "normalization_rule_name": "identity",
    "add_dummy_prefix": False,
    "remove_extra_whitespaces": False,
    "escape_whitespaces": True,
    "split_by_whitespace": False,
    "treat_whitespace_as_suffix": False,
    "allow_whitespace_only_pieces": False,
    "split_by_unicode_script": False,
    "split_by_number": False,
}


@dataclass(frozen=True, slots=True)
class SurfaceAtom:
    """One indivisible source span and whether learned pieces may cross it."""

    text: str
    start: int
    end: int
    mergeable: bool

    def __post_init__(self) -> None:
        if (
            not self.text
            or self.start < 0
            or self.end <= self.start
            or len(self.text) != self.end - self.start
        ):
            raise ValueError("surface atoms require a non-empty ordered source span")


Atomizer = Callable[[str], tuple[SurfaceAtom, ...]]
TrainingTextFactory = Callable[[], Iterable[str]]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _private_use_codepoint(index: int) -> int:
    remaining = index
    for start, end in PRIVATE_USE_RANGES:
        size = end - start + 1
        if remaining < size:
            return start + remaining
        remaining -= size
    raise ValueError("surface atom inventory exceeds the Unicode private-use capacity")


def _metadata_path(model_path: Path) -> Path:
    return model_path.with_suffix(".atoms.json")


def _partition_surrogates(
    atoms: tuple[SurfaceAtom, ...], atom_to_symbol: dict[str, str]
) -> tuple[str, ...]:
    """Return mergeable chunks and singleton barriers for trainer pretokenization."""
    groups: list[str] = []
    mergeable: list[str] = []
    for atom in atoms:
        symbol = atom_to_symbol[atom.text]
        if atom.mergeable:
            mergeable.append(symbol)
            continue
        if mergeable:
            groups.append("".join(mergeable))
            mergeable.clear()
        groups.append(symbol)
    if mergeable:
        groups.append("".join(mergeable))
    return tuple(groups)


def train_surrogate_sentencepiece(
    texts: TrainingTextFactory,
    output_prefix: Path,
    *,
    atomizer: Atomizer,
    contract: str,
    model_type: str,
    vocab_size: int,
    max_piece_atoms: int,
    metadata: dict[str, Any],
) -> Path:
    """Fit a deterministic SentencePiece model over replayable atomized text."""
    if model_type not in {"bpe", "unigram"}:
        raise ValueError(f"unsupported surrogate model type: {model_type}")
    if max_piece_atoms <= 0:
        raise ValueError("max_piece_atoms must be positive")
    try:
        import sentencepiece as spm
    except ImportError as exc:
        raise RuntimeError("sentencepiece is required for surrogate training") from exc

    atom_inventory: set[str] = set()
    barrier_inventory: set[str] = set()
    text_count = 0
    for text in texts():
        atoms = atomizer(text)
        if "".join(atom.text for atom in atoms) != text:
            raise ValueError("atomizer did not reconstruct its source text")
        for atom in atoms:
            atom_inventory.add(atom.text)
            if not atom.mergeable:
                barrier_inventory.add(atom.text)
        text_count += 1
    if text_count == 0 or not atom_inventory:
        raise ValueError("surrogate SentencePiece training requires non-empty text")

    ordered_atoms = sorted(atom_inventory)
    required_vocab = len(ordered_atoms) + 5
    if vocab_size < required_vocab:
        raise ValueError(
            f"vocab_size={vocab_size} cannot contain {len(ordered_atoms)} atoms "
            "plus four reserved IDs and the internal delimiter"
        )
    atom_to_symbol = {
        atom: chr(_private_use_codepoint(index)) for index, atom in enumerate(ordered_atoms)
    }

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    input_path = output_prefix.with_name(f"{output_prefix.name}_segments.txt")
    try:
        written = 0
        with input_path.open("w", encoding="utf-8", newline="\n") as handle:
            for text in texts():
                groups = _partition_surrogates(atomizer(text), atom_to_symbol)
                if not groups:
                    continue
                handle.write(PRETOKENIZATION_DELIMITER.join(groups))
                handle.write("\n")
                written += 1
        if written == 0:
            raise ValueError("surrogate SentencePiece training produced no sentences")

        spm.SentencePieceTrainer.train(
            input=str(input_path),
            model_prefix=str(output_prefix),
            vocab_size=vocab_size,
            model_type=model_type,
            character_coverage=1.0,
            **SURROGATE_SENTENCEPIECE_TRAINER_CONTRACT,
            pretokenization_delimiter=PRETOKENIZATION_DELIMITER,
            user_defined_symbols=[PRETOKENIZATION_DELIMITER],
            max_sentencepiece_length=max_piece_atoms,
            max_sentence_length=MAX_SENTENCE_LENGTH,
            bos_id=1,
            eos_id=2,
            unk_id=0,
            pad_id=3,
            hard_vocab_limit=False,
            shuffle_input_sentence=False,
            num_threads=1,
        )
    finally:
        input_path.unlink(missing_ok=True)

    model_path = output_prefix.with_suffix(".model")
    payload = {
        "contract": contract,
        "model_type": model_type,
        "vocab_size_requested": vocab_size,
        "max_piece_atoms": max_piece_atoms,
        "pretokenization_delimiter": PRETOKENIZATION_DELIMITER,
        "sentencepiece_trainer_contract": SURROGATE_SENTENCEPIECE_TRAINER_CONTRACT,
        "atoms": ordered_atoms,
        "barrier_atoms": sorted(barrier_inventory),
        **metadata,
    }
    _metadata_path(model_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return model_path


class SurrogateSentencePieceTokenizer(Tokenizer):
    """Common loading, span projection, decoding, and fingerprint behavior."""

    def __init__(self, model_path: Path, *, expected_contract: str) -> None:
        try:
            import sentencepiece as spm
        except ImportError as exc:
            raise RuntimeError("sentencepiece is required for this tokenizer") from exc

        self.model_path = Path(model_path)
        self.metadata_path = _metadata_path(self.model_path)
        self.metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        if self.metadata.get("contract") != expected_contract:
            raise ValueError(
                f"expected atomizer contract {expected_contract}, "
                f"found {self.metadata.get('contract')}"
            )
        atoms = self.metadata.get("atoms")
        if (
            not isinstance(atoms, list)
            or not atoms
            or not all(isinstance(atom, str) and atom for atom in atoms)
            or len(atoms) != len(set(atoms))
        ):
            raise ValueError("serialized surface atom inventory is invalid")
        self.atom_to_symbol = {
            str(atom): chr(_private_use_codepoint(index)) for index, atom in enumerate(atoms)
        }
        self.symbol_to_atom = {symbol: atom for atom, symbol in self.atom_to_symbol.items()}
        self.processor = spm.SentencePieceProcessor(model_file=str(self.model_path))
        reserved_ids = (
            self.processor.unk_id(),
            self.processor.bos_id(),
            self.processor.eos_id(),
            self.processor.pad_id(),
        )
        if reserved_ids != (0, 1, 2, 3):
            raise ValueError(f"surrogate model reserved IDs are invalid: {reserved_ids}")
        missing_symbols = [
            symbol
            for symbol in self.atom_to_symbol.values()
            if self.processor.piece_to_id(symbol) == 0
        ]
        if missing_symbols:
            raise ValueError(
                f"surrogate model is missing {len(missing_symbols)} serialized atom symbols"
            )
        self.bos_id = 1
        self.eos_id = 2
        self.unknown_id = 0
        self.unknown_semantics = "unseen_serialized_surface_atom"

    @property
    def vocab_size(self) -> int:
        return self.processor.vocab_size()

    def _encode_known_atoms(self, atoms: list[SurfaceAtom]) -> Encoding:
        if not atoms:
            return Encoding((), (), ())
        internal = "".join(self.atom_to_symbol[atom.text] for atom in atoms)
        mapping = self.processor.encode(internal, return_type="offset_mapping")
        ids: list[int] = []
        pieces: list[str] = []
        spans: list[tuple[int, int]] = []
        for token_id, (begin, end) in zip(mapping["ids"], mapping["offsets"]):
            begin = int(begin)
            end = int(end)
            if not (0 <= begin < end <= len(atoms)):
                raise ValueError(f"invalid surrogate token offset: {(begin, end)}")
            start = atoms[begin].start
            stop = atoms[end - 1].end
            ids.append(int(token_id))
            pieces.append("".join(atom.text for atom in atoms[begin:end]))
            spans.append((start, stop))
        return Encoding(tuple(ids), tuple(pieces), tuple(spans))

    @staticmethod
    def _unknown_atom(atom: SurfaceAtom) -> Encoding:
        return Encoding((0,), (atom.text,), ((atom.start, atom.end),))

    def _decode_piece(self, token_id: int) -> str:
        if token_id == 0:
            return "�"
        if token_id in {1, 2, 3}:
            return ""
        piece = self.processor.id_to_piece(int(token_id))
        if piece == PRETOKENIZATION_DELIMITER:
            return ""
        decoded: list[str] = []
        for symbol in piece:
            atom = self.symbol_to_atom.get(symbol)
            if atom is None:
                return "�"
            decoded.append(atom)
        return "".join(decoded)

    def decode(self, ids: list[int] | tuple[int, ...]) -> str:
        return "".join(self._decode_piece(int(token_id)) for token_id in ids)

    def piece_atoms(self, token_id: int) -> tuple[str, ...] | None:
        if token_id < 4:
            return None
        piece = self.processor.id_to_piece(int(token_id))
        if piece == PRETOKENIZATION_DELIMITER:
            return None
        atoms: list[str] = []
        for symbol in piece:
            atom = self.symbol_to_atom.get(symbol)
            if atom is None:
                return None
            atoms.append(atom)
        return tuple(atoms) if atoms else None

    def fingerprint_payload(self) -> dict[str, Any]:
        vocab_path = self.model_path.with_suffix(".vocab")
        payload: dict[str, Any] = {
            **super().fingerprint_payload(),
            "model_path": self.model_path.as_posix(),
            "model_sha256": _file_sha256(self.model_path),
            "atom_metadata_path": self.metadata_path.as_posix(),
            "atom_metadata_sha256": _file_sha256(self.metadata_path),
            "contract": self.metadata["contract"],
            "max_piece_atoms": self.metadata["max_piece_atoms"],
        }
        if vocab_path.is_file():
            payload["vocab_sha256"] = _file_sha256(vocab_path)
        return payload
