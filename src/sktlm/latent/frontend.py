"""Script frontends with observed orthography separated from phonology."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterator, Literal
import unicodedata

from sktlm.latent.phonology import (
    IAST_TO_PHONEME,
    Phoneme,
    match_iast_phoneme,
    normalize_iast,
)
from sktlm.representations.devanagari import (
    CONSONANTS,
    INDEPENDENT_VOWELS,
    VIRAMA,
    VOWEL_MARKS,
)


_DEVANAGARI_CONSONANTS = {
    written: IAST_TO_PHONEME[iast] for iast, written in CONSONANTS.items()
}
_DEVANAGARI_INDEPENDENT_VOWELS = {
    written: IAST_TO_PHONEME[iast] for iast, written in INDEPENDENT_VOWELS.items()
}
_DEVANAGARI_VOWEL_MARKS = {
    written: IAST_TO_PHONEME[iast]
    for iast, written in VOWEL_MARKS.items()
    if written
}
_DEVANAGARI_SIGNS = {
    "ं": Phoneme.ANUSVARA,
    "ः": Phoneme.VISARGA,
    "ँ": Phoneme.ANUNASIKA,
}
_DEVANAGARI_AVAGRAHA = "ऽ"
_DEVANAGARI_DANDAS = frozenset({"।", "॥"})
_DEVANAGARI_OM = "ॐ"


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


def parse_devanagari_surface(text: str) -> ParsedSurface:
    """Parse the repository's generated M0 Devanagari representation."""

    written = unicodedata.normalize("NFC", text)
    phonemes: list[Phoneme] = []
    spans: list[tuple[int, int]] = []
    cues: list[OrthographicCue] = []
    position = 0

    def append(symbol: Phoneme, start: int, end: int) -> None:
        phonemes.append(symbol)
        spans.append((start, end))

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
        if character == _DEVANAGARI_AVAGRAHA:
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
        if character == _DEVANAGARI_OM:
            append(Phoneme.O, position, position + 1)
            append(Phoneme.ANUSVARA, position, position + 1)
            position += 1
            continue
        independent = _DEVANAGARI_INDEPENDENT_VOWELS.get(character)
        if independent is not None:
            append(independent, position, position + 1)
            position += 1
            continue
        consonant = _DEVANAGARI_CONSONANTS.get(character)
        if consonant is not None:
            following = written[position + 1] if position + 1 < len(written) else ""
            if following == VIRAMA:
                append(consonant, position, position + 2)
                position += 2
                continue
            append(consonant, position, position + 1)
            vowel = _DEVANAGARI_VOWEL_MARKS.get(following)
            if vowel is not None:
                append(vowel, position + 1, position + 2)
                position += 2
            else:
                append(Phoneme.A, position, position + 1)
                position += 1
            continue
        sign = _DEVANAGARI_SIGNS.get(character)
        if sign is not None:
            append(sign, position, position + 1)
            position += 1
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


def parse_surface(text: str, *, script: str = "iast") -> ParsedSurface:
    """Dispatch one formal M0 script to its observation parser."""

    if script == "iast":
        return parse_iast_surface(text)
    if script == "devanagari":
        return parse_devanagari_surface(text)
    raise ValueError(f"unsupported latent frontend script: {script}")


def _events(parsed: ParsedSurface) -> Iterator[tuple[int, int, str, object]]:
    for phoneme, (start, end) in zip(parsed.phonemes, parsed.phoneme_spans):
        yield start, end, "phoneme", phoneme
    for cue in parsed.cues:
        yield cue.source_start, cue.source_end, "cue", cue


def iter_observed_segments(
    text: str,
    *,
    max_tokens: int = 128,
    script: str = "iast",
) -> Iterator[ObservedSegment]:
    """Yield punctuation-bounded, deterministically sharded surface segments.

    Punctuation is retained by the script frontend as an observed cue
    but delimits lexical inference. Long punctuation-free lines are sharded at
    a visible-space cue to keep memory bounded.
    """

    if max_tokens < 1:
        raise ValueError("max_tokens must be >= 1")
    parsed = parse_surface(text, script=script)
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
