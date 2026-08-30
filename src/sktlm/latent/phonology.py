"""Script-neutral Sanskrit phonological symbols.

The enum values are stable linguistic identifiers, not written IAST glyphs.
IAST is confined to the parse/render adapter in this module. A future
Devanagari frontend can therefore emit the same :class:`Phoneme` sequence.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from sktlm.representations.iast import normalize_iast_equivalents


class Phoneme(str, Enum):
    A = "V_A"
    AA = "V_AA"
    I = "V_I"
    II = "V_II"
    U = "V_U"
    UU = "V_UU"
    VOCALIC_R = "V_R"
    VOCALIC_RR = "V_RR"
    VOCALIC_L = "V_L"
    VOCALIC_LL = "V_LL"
    E = "V_E"
    AI = "V_AI"
    O = "V_O"
    AU = "V_AU"
    K = "C_K"
    KH = "C_KH"
    G = "C_G"
    GH = "C_GH"
    NG = "C_NG"
    C = "C_C"
    CH = "C_CH"
    J = "C_J"
    JH = "C_JH"
    NY = "C_NY"
    TT = "C_TT"
    TTH = "C_TTH"
    DD = "C_DD"
    DDH = "C_DDH"
    NN = "C_NN"
    T = "C_T"
    TH = "C_TH"
    D = "C_D"
    DH = "C_DH"
    N = "C_N"
    P = "C_P"
    PH = "C_PH"
    B = "C_B"
    BH = "C_BH"
    M = "C_M"
    Y = "C_Y"
    R = "C_R"
    L = "C_L"
    V = "C_V"
    SH = "C_SH"
    SS = "C_SS"
    S = "C_S"
    H = "C_H"
    ANUSVARA = "M_ANUSVARA"
    VISARGA = "M_VISARGA"
    ANUNASIKA = "M_ANUNASIKA"


IAST_TO_PHONEME: dict[str, Phoneme] = {
    "ai": Phoneme.AI,
    "au": Phoneme.AU,
    "kh": Phoneme.KH,
    "gh": Phoneme.GH,
    "ch": Phoneme.CH,
    "jh": Phoneme.JH,
    "ṭh": Phoneme.TTH,
    "ḍh": Phoneme.DDH,
    "th": Phoneme.TH,
    "dh": Phoneme.DH,
    "ph": Phoneme.PH,
    "bh": Phoneme.BH,
    "m̐": Phoneme.ANUNASIKA,
    "a": Phoneme.A,
    "ā": Phoneme.AA,
    "i": Phoneme.I,
    "ī": Phoneme.II,
    "u": Phoneme.U,
    "ū": Phoneme.UU,
    "ṛ": Phoneme.VOCALIC_R,
    "ṝ": Phoneme.VOCALIC_RR,
    "ḷ": Phoneme.VOCALIC_L,
    "ḹ": Phoneme.VOCALIC_LL,
    "e": Phoneme.E,
    "o": Phoneme.O,
    "k": Phoneme.K,
    "g": Phoneme.G,
    "ṅ": Phoneme.NG,
    "c": Phoneme.C,
    "j": Phoneme.J,
    "ñ": Phoneme.NY,
    "ṭ": Phoneme.TT,
    "ḍ": Phoneme.DD,
    "ṇ": Phoneme.NN,
    "t": Phoneme.T,
    "d": Phoneme.D,
    "n": Phoneme.N,
    "p": Phoneme.P,
    "b": Phoneme.B,
    "m": Phoneme.M,
    "y": Phoneme.Y,
    "r": Phoneme.R,
    "l": Phoneme.L,
    "v": Phoneme.V,
    "ś": Phoneme.SH,
    "ṣ": Phoneme.SS,
    "s": Phoneme.S,
    "h": Phoneme.H,
    "ṃ": Phoneme.ANUSVARA,
    "ḥ": Phoneme.VISARGA,
}

PHONEME_TO_IAST = {value: key for key, value in IAST_TO_PHONEME.items()}
_IAST_TOKENS = tuple(sorted(IAST_TO_PHONEME, key=len, reverse=True))
VOWELS = frozenset(
    {
        Phoneme.A,
        Phoneme.AA,
        Phoneme.I,
        Phoneme.II,
        Phoneme.U,
        Phoneme.UU,
        Phoneme.VOCALIC_R,
        Phoneme.VOCALIC_RR,
        Phoneme.VOCALIC_L,
        Phoneme.VOCALIC_LL,
        Phoneme.E,
        Phoneme.AI,
        Phoneme.O,
        Phoneme.AU,
    }
)


@dataclass(frozen=True, slots=True)
class PhonologicalForm:
    """One complete latent lexical/phonological form."""

    symbols: tuple[Phoneme, ...]

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("A phonological form must contain at least one symbol.")

    @property
    def key(self) -> str:
        return ".".join(symbol.value for symbol in self.symbols)

    @property
    def iast(self) -> str:
        return "".join(PHONEME_TO_IAST[symbol] for symbol in self.symbols)

    @property
    def phoneme_ids(self) -> tuple[str, ...]:
        return tuple(symbol.value for symbol in self.symbols)

    def has_vowel(self) -> bool:
        return any(symbol in VOWELS for symbol in self.symbols)

    @classmethod
    def from_key(cls, key: str) -> "PhonologicalForm":
        if not key:
            raise ValueError("Empty phonological-form key.")
        return cls(tuple(Phoneme(item) for item in key.split(".")))


def normalize_iast(text: str) -> str:
    return unicodedata.normalize("NFC", normalize_iast_equivalents(text))


def match_iast_phoneme(text: str, start: int) -> tuple[Phoneme, int] | None:
    """Return the longest IAST phoneme beginning at ``start``."""

    for token in _IAST_TOKENS:
        if text.startswith(token, start):
            return IAST_TO_PHONEME[token], start + len(token)
    return None


def parse_iast_form(text: str) -> PhonologicalForm:
    """Parse a rule-side IAST string, rejecting non-phonological notation."""

    normalized = normalize_iast(text)
    symbols: list[Phoneme] = []
    position = 0
    while position < len(normalized):
        matched = match_iast_phoneme(normalized, position)
        if matched is None:
            raise ValueError(
                f"Unsupported IAST phonological notation at offset {position}: "
                f"{normalized[position:position + 8]!r}"
            )
        symbol, position = matched
        symbols.append(symbol)
    return PhonologicalForm(tuple(symbols))


def form_from_symbols(symbols: Iterable[Phoneme]) -> PhonologicalForm:
    return PhonologicalForm(tuple(symbols))
