"""Frozen latent-token vocabulary and deterministic OOV projection."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, Protocol

from sktlm.latent.phonology import Phoneme, PhonologicalForm


BASE_FORMS = tuple(PhonologicalForm((phoneme,)) for phoneme in Phoneme)
BASE_FORM_BY_SYMBOL = {
    form.symbols[0]: form
    for form in BASE_FORMS
}
BASE_UNIT_COUNT = len(BASE_FORMS)
SELECTION_PASS = 1
RANKING_RULE = "expected_count DESC, form_key ASC"

if BASE_UNIT_COUNT != 50:
    raise RuntimeError(
        f"The fixed base-unit contract requires 50 Phoneme values; found {BASE_UNIT_COUNT}."
    )


class FormScorer(Protocol):
    def score(self, form: PhonologicalForm) -> float: ...


@dataclass(frozen=True, slots=True)
class VocabularyEntry:
    rank: int
    kind: str
    form: PhonologicalForm
    pass1_expected_count: float


def allowed_key_sha256(keys: Iterable[str]) -> str:
    """Hash the sorted allowed-key inventory with an explicit line terminator."""

    payload = "".join(f"{key}\n" for key in sorted(keys)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class FrozenVocabulary:
    """One pass-1-selected vocabulary, including all phonological base units."""

    total_budget: int
    entries: tuple[VocabularyEntry, ...]
    allowed_sha256: str
    _allowed_keys: frozenset[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.total_budget < BASE_UNIT_COUNT:
            raise ValueError(
                f"vocab_budget must be >= {BASE_UNIT_COUNT}; got {self.total_budget}"
            )
        keys = tuple(entry.form.key for entry in self.entries)
        object.__setattr__(self, "_allowed_keys", frozenset(keys))
        if len(keys) != len(set(keys)):
            raise ValueError("Frozen vocabulary contains duplicate form keys.")
        if len(keys) > self.total_budget:
            raise ValueError("Frozen vocabulary exceeds its requested budget.")
        if tuple(entry.rank for entry in self.entries) != tuple(
            range(1, len(self.entries) + 1)
        ):
            raise ValueError("Frozen vocabulary ranks must be contiguous from 1.")
        base_keys = {form.key for form in BASE_FORMS}
        if not base_keys.issubset(keys):
            raise ValueError("Frozen vocabulary is missing phonological base units.")
        for entry in self.entries:
            expected_kind = "base" if len(entry.form.symbols) == 1 else "lexical"
            if entry.kind != expected_kind:
                raise ValueError(
                    f"Frozen vocabulary kind mismatch for {entry.form.key}."
                )
        if allowed_key_sha256(keys) != self.allowed_sha256:
            raise ValueError("Frozen vocabulary allowed-key SHA-256 mismatch.")

    @property
    def allowed_keys(self) -> frozenset[str]:
        return self._allowed_keys

    @property
    def learned_capacity(self) -> int:
        return self.total_budget - BASE_UNIT_COUNT

    @property
    def actual_size(self) -> int:
        return len(self.entries)

    def project(self, form: PhonologicalForm) -> tuple[PhonologicalForm, ...]:
        """Return one allowed identity or its constituent singleton units."""

        if form.key in self.allowed_keys:
            return (form,)
        return tuple(BASE_FORM_BY_SYMBOL[symbol] for symbol in form.symbols)

    def checkpoint_payload(self) -> dict[str, object]:
        return {
            "status": "frozen",
            "total_budget": self.total_budget,
            "base_unit_count": BASE_UNIT_COUNT,
            "learned_lexical_capacity": self.learned_capacity,
            "selection_pass": SELECTION_PASS,
            "ranking_rule": RANKING_RULE,
            "actual_vocabulary_size": self.actual_size,
            "allowed_key_sha256": self.allowed_sha256,
            "identity_semantics": "one distinct latent form_key is one vocabulary item",
            "surface_realizations_consume_slots": False,
            "oov_projection": "constituent phonological base-unit tokens",
        }

    def artifact_payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            **self.checkpoint_payload(),
            "base_unit_inventory": [form.key for form in BASE_FORMS],
        }


@dataclass(slots=True)
class ProjectedFormScorer:
    """Score an OOV form as the sum of its projected base-token scores."""

    scorer: FormScorer
    vocabulary: FrozenVocabulary
    _base_scores: dict[PhonologicalForm, float]

    def __init__(self, scorer: FormScorer, vocabulary: FrozenVocabulary) -> None:
        self.scorer = scorer
        self.vocabulary = vocabulary
        self._base_scores = {}

    def score(self, form: PhonologicalForm) -> float:
        projected = self.vocabulary.project(form)
        if len(projected) == 1 and projected[0] is form:
            return self.scorer.score(form)
        total = 0.0
        for base in projected:
            try:
                value = self._base_scores[base]
            except KeyError:
                value = self.scorer.score(base)
                self._base_scores[base] = value
            total += value
        return total
