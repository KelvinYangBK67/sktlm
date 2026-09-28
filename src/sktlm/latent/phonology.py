"""Script-neutral Sanskrit phonological symbols.

The enum values are stable linguistic identifiers, not written IAST glyphs.
IAST is confined to the parse/render adapter in this module. A future
Devanagari frontend can therefore emit the same :class:`Phoneme` sequence.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
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


# Stable transient-storage encoding.  This table is deliberately explicit and
# ordered by the canonical Phoneme.value bytes; it is not derived from Enum
# declaration order.  Codes start at one so zero remains an invalid/corrupt
# payload byte.  Keeping this order also makes equal-version packed forms sort
# exactly like their dot-separated canonical keys.
HOST_BLOB_CODEC_VERSION = 1
_HOST_BLOB_CODE_TO_PHONEME: tuple[Phoneme, ...] = (
    Phoneme.B,
    Phoneme.BH,
    Phoneme.C,
    Phoneme.CH,
    Phoneme.D,
    Phoneme.DD,
    Phoneme.DDH,
    Phoneme.DH,
    Phoneme.G,
    Phoneme.GH,
    Phoneme.H,
    Phoneme.J,
    Phoneme.JH,
    Phoneme.K,
    Phoneme.KH,
    Phoneme.L,
    Phoneme.M,
    Phoneme.N,
    Phoneme.NG,
    Phoneme.NN,
    Phoneme.NY,
    Phoneme.P,
    Phoneme.PH,
    Phoneme.R,
    Phoneme.S,
    Phoneme.SH,
    Phoneme.SS,
    Phoneme.T,
    Phoneme.TH,
    Phoneme.TT,
    Phoneme.TTH,
    Phoneme.V,
    Phoneme.Y,
    Phoneme.ANUNASIKA,
    Phoneme.ANUSVARA,
    Phoneme.VISARGA,
    Phoneme.A,
    Phoneme.AA,
    Phoneme.AI,
    Phoneme.AU,
    Phoneme.E,
    Phoneme.I,
    Phoneme.II,
    Phoneme.VOCALIC_L,
    Phoneme.VOCALIC_LL,
    Phoneme.O,
    Phoneme.VOCALIC_R,
    Phoneme.VOCALIC_RR,
    Phoneme.U,
    Phoneme.UU,
)
_HOST_BLOB_PHONEME_TO_CODE = {
    phoneme: code
    for code, phoneme in enumerate(_HOST_BLOB_CODE_TO_PHONEME, start=1)
}


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
    _key: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("A phonological form must contain at least one symbol.")
        object.__setattr__(
            self,
            "_key",
            ".".join(symbol.value for symbol in self.symbols),
        )

    @property
    def key(self) -> str:
        return self._key

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


def pack_phonological_form(form: PhonologicalForm) -> bytes:
    """Return the versioned, bijective transient-storage identity for ``form``."""

    return bytes(
        (HOST_BLOB_CODEC_VERSION,)
        + tuple(_HOST_BLOB_PHONEME_TO_CODE[symbol] for symbol in form.symbols)
    )


def pack_host_key(key: str) -> bytes:
    """Pack one canonical phonological-form key, rejecting malformed input."""

    return pack_phonological_form(PhonologicalForm.from_key(key))


def _host_blob_phonemes(payload: bytes) -> tuple[Phoneme, ...]:
    if len(payload) < 2:
        raise ValueError("Packed host identity is truncated or empty.")
    if payload[0] != HOST_BLOB_CODEC_VERSION:
        raise ValueError(
            f"Unsupported packed host identity version: {payload[0]!r}."
        )
    try:
        symbols = tuple(
            _HOST_BLOB_CODE_TO_PHONEME[code - 1] for code in payload[1:]
        )
    except IndexError as error:
        raise ValueError("Packed host identity contains an invalid phoneme code.") from error
    if any(code == 0 for code in payload[1:]):
        raise ValueError("Packed host identity contains an invalid phoneme code.")
    return symbols


def validate_host_blob(payload: bytes) -> None:
    """Validate a compact identity without constructing a canonical string."""

    _host_blob_phonemes(payload)


def unpack_host_blob(payload: bytes) -> PhonologicalForm:
    """Decode one exact host identity and fail closed on any corrupt byte."""

    return PhonologicalForm(_host_blob_phonemes(payload))


def host_blob_to_key(payload: bytes) -> str:
    return unpack_host_blob(payload).key


def canonical_host_key_utf8_length(payload: bytes) -> int:
    """Measure the legacy canonical key without materializing that string."""

    symbols = _host_blob_phonemes(payload)
    return sum(len(symbol.value) for symbol in symbols) + len(symbols) - 1
