"""IAST observation frontend with orthography separated from phonology."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterator, Literal

from sktlm.latent.phonology import Phoneme, match_iast_phoneme, normalize_iast


class CueKind(str, Enum):
    SPACE = "space"
    AVAGRAHA = "avagraha"
    PUNCTUATION = "punctuation"


@dataclass(frozen=True, slots=True)
class OrthographicCue:
    kind: CueKind
    text: str
    source_start: int
    source_end: int
    phoneme_offset: int


@dataclass(frozen=True, slots=True)
class SurfaceUnit:
    kind: Literal["phoneme", "avagraha"]
    phoneme: Phoneme | None
    source_start: int
    source_end: int

    @property
    def match_key(self) -> tuple[str, str]:
        if self.kind == "avagraha":
            return ("avagraha", "")
        assert self.phoneme is not None
        return ("phoneme", self.phoneme.value)


@dataclass(frozen=True, slots=True)
class ParsedSurface:
    written: str
    phonemes: tuple[Phoneme, ...]
    phoneme_spans: tuple[tuple[int, int], ...]
    cues: tuple[OrthographicCue, ...]


@dataclass(frozen=True, slots=True)
class ObservedToken:
    written: str
    source_start: int
    source_end: int
    units: tuple[SurfaceUnit, ...]

    @property
    def phonemes(self) -> tuple[Phoneme, ...]:
        return tuple(unit.phoneme for unit in self.units if unit.phoneme is not None)

    @property
    def has_avagraha(self) -> bool:
        return any(unit.kind == "avagraha" for unit in self.units)


@dataclass(frozen=True, slots=True)
class ObservedSegment:
    written: str
    source_start: int
    source_end: int
    tokens: tuple[ObservedToken, ...]
    separators: tuple[str, ...]

    def boundary_source_offset(self, boundary_index: int) -> int:
        if boundary_index <= 0 or boundary_index >= len(self.tokens):
            raise IndexError("boundary_index must be an internal token boundary")
        return self.tokens[boundary_index - 1].source_end


def parse_iast_surface(text: str) -> ParsedSurface:
    """Parse normalized IAST into phonemes plus separately typed cues."""

    written = normalize_iast(text)
    phonemes: list[Phoneme] = []
    spans: list[tuple[int, int]] = []
    cues: list[OrthographicCue] = []
    position = 0
    while position < len(written):
        character = written[position]
        if character.isspace():
            end = position + 1
            while end < len(written) and written[end].isspace():
                end += 1
            cues.append(
                OrthographicCue(
                    CueKind.SPACE,
                    written[position:end],
                    position,
                    end,
                    len(phonemes),
                )
            )
            position = end
            continue
        if character in {"'", "’", "ʼ"}:
            cues.append(
                OrthographicCue(
                    CueKind.AVAGRAHA,
                    character,
                    position,
                    position + 1,
                    len(phonemes),
                )
            )
            position += 1
            continue
        matched = match_iast_phoneme(written, position)
        if matched is not None:
            phoneme, end = matched
            phonemes.append(phoneme)
            spans.append((position, end))
            position = end
            continue
        cues.append(
            OrthographicCue(
                CueKind.PUNCTUATION,
                character,
                position,
                position + 1,
                len(phonemes),
            )
        )
        position += 1
    return ParsedSurface(written, tuple(phonemes), tuple(spans), tuple(cues))


def _events(parsed: ParsedSurface) -> Iterator[tuple[int, int, str, object]]:
    for phoneme, (start, end) in zip(parsed.phonemes, parsed.phoneme_spans):
        yield start, end, "phoneme", phoneme
    for cue in parsed.cues:
        yield cue.source_start, cue.source_end, "cue", cue


def iter_observed_segments(
    text: str,
    *,
    max_tokens: int = 128,
) -> Iterator[ObservedSegment]:
    """Yield punctuation-bounded, deterministically sharded surface segments.

    Punctuation is retained in :func:`parse_iast_surface` as an observed cue
    but delimits lexical inference. Long punctuation-free lines are sharded at
    a visible-space cue to keep memory bounded.
    """

    if max_tokens < 1:
        raise ValueError("max_tokens must be >= 1")
    parsed = parse_iast_surface(text)
    tokens: list[ObservedToken] = []
    separators: list[str] = []
    token_units: list[SurfaceUnit] = []
    token_start: int | None = None
    token_end: int | None = None
    pending_space = ""

    def finish_token() -> None:
        nonlocal token_units, token_start, token_end, pending_space
        if token_start is None or token_end is None:
            return
        if tokens:
            separators.append(pending_space)
        tokens.append(
            ObservedToken(
                parsed.written[token_start:token_end],
                token_start,
                token_end,
                tuple(token_units),
            )
        )
        token_units = []
        token_start = None
        token_end = None
        pending_space = ""

    def emit_chunks() -> Iterator[ObservedSegment]:
        nonlocal tokens, separators
        while tokens:
            chunk_tokens = tokens[:max_tokens]
            chunk_separators = separators[: max(0, len(chunk_tokens) - 1)]
            start = chunk_tokens[0].source_start
            end = chunk_tokens[-1].source_end
            yield ObservedSegment(
                parsed.written[start:end],
                start,
                end,
                tuple(chunk_tokens),
                tuple(chunk_separators),
            )
            consumed = len(chunk_tokens)
            tokens = tokens[consumed:]
            separators = separators[consumed:]

    for start, end, kind, value in sorted(_events(parsed), key=lambda item: item[:2]):
        if kind == "phoneme":
            if token_start is None:
                token_start = start
            token_end = end
            token_units.append(SurfaceUnit("phoneme", value, start, end))
            continue
        cue = value
        assert isinstance(cue, OrthographicCue)
        if cue.kind == CueKind.AVAGRAHA:
            if token_start is None:
                token_start = start
            token_end = end
            token_units.append(SurfaceUnit("avagraha", None, start, end))
        elif cue.kind == CueKind.SPACE:
            finish_token()
            if tokens:
                pending_space += cue.text
        else:
            finish_token()
            yield from emit_chunks()
    finish_token()
    yield from emit_chunks()
