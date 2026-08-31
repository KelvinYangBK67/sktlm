"""Surface-only Unigram token lattice over IAST grapheme-cluster atoms."""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import regex

from sktlm.tokenizers._surrogate import (
    SurfaceAtom,
    SurrogateSentencePieceTokenizer,
    TrainingTextFactory,
    train_surrogate_sentencepiece,
)
from sktlm.tokenizers.base import Encoding


SURFACE_LATTICE_CONTRACT = "iast_surface_lattice_v1"
DEFAULT_UNKNOWN_LOG_SCORE = -20.0


def atomize_iast_surface(text: str) -> tuple[SurfaceAtom, ...]:
    """Return exact `regex` extended grapheme clusters under the v1 barrier rule."""
    atoms: list[SurfaceAtom] = []
    for match in regex.finditer(r"\X", text):
        surface = match.group(0)
        categories = tuple(unicodedata.category(char) for char in surface)
        mergeable = any(category.startswith("L") for category in categories) and all(
            category[0] in {"L", "M"} for category in categories
        )
        atoms.append(SurfaceAtom(surface, match.start(), match.end(), mergeable))
    return tuple(atoms)


@dataclass(frozen=True, slots=True)
class LatticeArc:
    start_node: int
    end_node: int
    start: int
    end: int
    token_id: int
    piece: str
    log_score: float


@dataclass(frozen=True, slots=True)
class SurfaceLattice:
    text: str
    node_offsets: tuple[int, ...]
    arcs: tuple[LatticeArc, ...]

    @property
    def node_count(self) -> int:
        return len(self.node_offsets)

    def arcs_from(self, node: int) -> tuple[LatticeArc, ...]:
        return tuple(arc for arc in self.arcs if arc.start_node == node)


@dataclass(frozen=True, slots=True)
class LatticeEncodingStats:
    log_probability: float
    arc_count: int
    ambiguous_node_count: int


class _PieceTrieNode:
    def __init__(self) -> None:
        self.children: dict[str, _PieceTrieNode] = {}
        self.terminals: list[tuple[int, float]] = []


def _logaddexp(left: float, right: float) -> float:
    if left == -math.inf:
        return right
    if right == -math.inf:
        return left
    maximum = max(left, right)
    return maximum + math.log1p(math.exp(min(left, right) - maximum))


class SurfaceLatticeTokenizer(SurrogateSentencePieceTokenizer):
    """Complete learned-piece DAG with marginal likelihood and Viterbi encoding."""

    name = "surface_lattice"

    def __init__(self, model_path: Path) -> None:
        super().__init__(model_path, expected_contract=SURFACE_LATTICE_CONTRACT)
        expected_regex = str(self.metadata.get("regex_version"))
        if expected_regex != regex.__version__:
            raise RuntimeError(
                f"surface-lattice requires regex {expected_regex}, found {regex.__version__}"
            )
        expected_unicode = str(self.metadata.get("unicodedata_version"))
        if expected_unicode != unicodedata.unidata_version:
            raise RuntimeError(
                "surface-lattice Unicode database mismatch: "
                f"expected {expected_unicode}, found {unicodedata.unidata_version}"
            )
        self.unknown_log_score = float(self.metadata["unknown_log_score"])
        self._piece_trie = _PieceTrieNode()
        for token_id in range(4, self.vocab_size):
            atoms = self.piece_atoms(token_id)
            if not atoms:
                continue
            node = self._piece_trie
            for atom in atoms:
                node = node.children.setdefault(atom, _PieceTrieNode())
            node.terminals.append((token_id, float(self.processor.get_score(token_id))))
        self._sort_trie_terminals(self._piece_trie)

    @classmethod
    def _sort_trie_terminals(cls, node: _PieceTrieNode) -> None:
        node.terminals.sort(key=lambda item: item[0])
        for child in node.children.values():
            cls._sort_trie_terminals(child)

    def build_lattice(self, text: str) -> SurfaceLattice:
        atoms = atomize_iast_surface(text)
        node_offsets = (0, *(atom.end for atom in atoms))
        arcs: list[LatticeArc] = []
        atom_texts = tuple(atom.text for atom in atoms)

        for index, atom in enumerate(atoms):
            matched = False
            node = self._piece_trie
            end_node = index
            while end_node < len(atoms):
                next_atom = atoms[end_node]
                if end_node > index and (not atom.mergeable or not next_atom.mergeable):
                    break
                child = node.children.get(atom_texts[end_node])
                if child is None:
                    break
                node = child
                end_node += 1
                for token_id, score in node.terminals:
                    arcs.append(
                        LatticeArc(
                            start_node=index,
                            end_node=end_node,
                            start=atom.start,
                            end=atoms[end_node - 1].end,
                            token_id=token_id,
                            piece=text[atom.start : atoms[end_node - 1].end],
                            log_score=score,
                        )
                    )
                    matched = True
                if not atom.mergeable:
                    break
            if not matched:
                arcs.append(
                    LatticeArc(
                        start_node=index,
                        end_node=index + 1,
                        start=atom.start,
                        end=atom.end,
                        token_id=0,
                        piece=atom.text,
                        log_score=self.unknown_log_score,
                    )
                )

        arcs.sort(key=lambda arc: (arc.start_node, arc.end_node, arc.token_id))
        return SurfaceLattice(text=text, node_offsets=node_offsets, arcs=tuple(arcs))

    @staticmethod
    def _arcs_by_start(lattice: SurfaceLattice) -> tuple[tuple[LatticeArc, ...], ...]:
        grouped: list[list[LatticeArc]] = [[] for _ in lattice.node_offsets]
        for arc in lattice.arcs:
            grouped[arc.start_node].append(arc)
        return tuple(tuple(arcs) for arcs in grouped)

    def encode_with_lattice(self, text: str) -> tuple[Encoding, LatticeEncodingStats]:
        lattice = self.build_lattice(text)
        if lattice.node_count == 1:
            return Encoding((), (), ()), LatticeEncodingStats(0.0, 0, 0)
        arcs_by_start = self._arcs_by_start(lattice)
        final_node = lattice.node_count - 1

        forward = [-math.inf] * lattice.node_count
        forward[0] = 0.0
        best_score = [-math.inf] * lattice.node_count
        best_score[0] = 0.0
        best_count = [0] * lattice.node_count
        predecessor: list[LatticeArc | None] = [None] * lattice.node_count

        for start_node in range(final_node):
            if not arcs_by_start[start_node]:
                raise ValueError(f"surface lattice is disconnected at node {start_node}")
            for arc in arcs_by_start[start_node]:
                forward[arc.end_node] = _logaddexp(
                    forward[arc.end_node], forward[start_node] + arc.log_score
                )
                candidate_score = best_score[start_node] + arc.log_score
                candidate_count = best_count[start_node] + 1
                previous = predecessor[arc.end_node]
                replace = candidate_score > best_score[arc.end_node]
                if candidate_score == best_score[arc.end_node]:
                    previous_id = previous.token_id if previous is not None else math.inf
                    previous_start = previous.start_node if previous is not None else math.inf
                    replace = (candidate_count, arc.token_id, arc.start_node) < (
                        best_count[arc.end_node],
                        previous_id,
                        previous_start,
                    )
                if replace:
                    best_score[arc.end_node] = candidate_score
                    best_count[arc.end_node] = candidate_count
                    predecessor[arc.end_node] = arc

        if forward[final_node] == -math.inf or predecessor[final_node] is None:
            raise ValueError("surface lattice has no complete path")

        path: list[LatticeArc] = []
        node = final_node
        while node > 0:
            arc = predecessor[node]
            if arc is None:
                raise ValueError("surface lattice Viterbi backpointer is missing")
            path.append(arc)
            node = arc.start_node
        path.reverse()
        encoding = Encoding(
            ids=tuple(arc.token_id for arc in path),
            pieces=tuple(arc.piece for arc in path),
            spans=tuple((arc.start, arc.end) for arc in path),
        )
        ambiguous_nodes = sum(len(arcs) > 1 for arcs in arcs_by_start[:-1])
        stats = LatticeEncodingStats(
            log_probability=forward[final_node],
            arc_count=len(lattice.arcs),
            ambiguous_node_count=ambiguous_nodes,
        )
        return encoding, stats

    def encode(self, text: str) -> Encoding:
        encoding, _ = self.encode_with_lattice(text)
        return encoding

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            **super().fingerprint_payload(),
            "type": self.name,
            "atomizer": SURFACE_LATTICE_CONTRACT,
            "regex_version": regex.__version__,
            "unicodedata_version": unicodedata.unidata_version,
            "unknown_log_score": self.unknown_log_score,
        }


def train_surface_lattice(
    texts: TrainingTextFactory,
    model_dir: Path,
    *,
    vocab_size: int,
    max_piece_atoms: int = 16,
    unknown_log_score: float = DEFAULT_UNKNOWN_LOG_SCORE,
) -> SurfaceLatticeTokenizer:
    """Fit one independent surface-only Unigram lattice vocabulary."""
    if not math.isfinite(unknown_log_score) or unknown_log_score >= 0:
        raise ValueError("unknown_log_score must be a finite negative number")
    model_path = train_surrogate_sentencepiece(
        texts,
        model_dir / f"surface_lattice_{vocab_size}",
        atomizer=atomize_iast_surface,
        contract=SURFACE_LATTICE_CONTRACT,
        model_type="unigram",
        vocab_size=vocab_size,
        max_piece_atoms=max_piece_atoms,
        metadata={
            "atomizer": SURFACE_LATTICE_CONTRACT,
            "regex_version": regex.__version__,
            "unicodedata_version": unicodedata.unidata_version,
            "unknown_log_score": unknown_log_score,
            "likelihood": "complete_dag_logsumexp",
        },
    )
    return SurfaceLatticeTokenizer(model_path)
