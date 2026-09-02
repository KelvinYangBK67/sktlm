"""Declared expected-count/reweighted-MDL scores for reusable pieces."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Protocol

from sktlm.latent.phonology import Phoneme, PhonologicalForm


class PieceScorer(Protocol):
    def score(self, piece: PhonologicalForm) -> float: ...


@dataclass(frozen=True, slots=True)
class NeutralPieceScorer:
    """Pass-1 scorer: the normalized segmentation prior is the whole score."""

    def score(self, piece: PhonologicalForm) -> float:
        del piece
        return 0.0


class ExpectedCountPieceScorer:
    r"""Reference piece energy derived from the preceding pass's counts.

    The implementation follows the declared P0 semantics exactly::

        log P(p) - lambda * (kappa + beta * len(p))
                   * log(1 + 1 / (tau + count(p)))

    This is an energy/reweighted-MDL scoring rule. It is not presented as a
    new normalized generative prior over variable-length segmentations.
    """

    def __init__(
        self,
        counts: Mapping[PhonologicalForm, float],
        *,
        alpha: float,
        lambda_: float,
        kappa: float,
        beta: float,
        tau: float,
    ) -> None:
        if alpha <= 0.0:
            raise ValueError("alpha must be > 0")
        if lambda_ < 0.0 or kappa < 0.0 or beta < 0.0:
            raise ValueError("lambda_, kappa, and beta must be >= 0")
        if tau <= 0.0:
            raise ValueError("tau must be > 0")
        self.counts = {
            piece: float(count)
            for piece, count in counts.items()
            if float(count) > 0.0
        }
        if not self.counts:
            raise ValueError("Expected-count piece scorer requires positive counts.")
        self.alpha = alpha
        self.lambda_ = lambda_
        self.kappa = kappa
        self.beta = beta
        self.tau = tau
        self.total_count = sum(self.counts.values())
        self.vocabulary_size = len(self.counts)
        self.denominator = self.total_count + alpha * self.vocabulary_size

    def probability(self, piece: PhonologicalForm) -> float:
        return (self.counts.get(piece, 0.0) + self.alpha) / self.denominator

    def complexity_increment(self, piece: PhonologicalForm) -> float:
        count = self.counts.get(piece, 0.0)
        amplitude = self.lambda_ * (
            self.kappa + self.beta * len(piece.symbols)
        )
        return amplitude * math.log1p(1.0 / (self.tau + count))

    def score(self, piece: PhonologicalForm) -> float:
        return math.log(max(self.probability(piece), 1e-300)) - (
            self.complexity_increment(piece)
        )


@dataclass(frozen=True, slots=True)
class GeometricPhonemeBaseMeasure:
    """Normalized base mass over every finite nonempty phoneme sequence.

    Length is geometric and symbols are uniform over the complete finite
    script-neutral Phoneme inventory. The measure is never enumerated.
    """

    stop_probability: float = 0.5
    alphabet_size: int = len(Phoneme)

    def __post_init__(self) -> None:
        if not 0.0 < self.stop_probability < 1.0:
            raise ValueError("stop_probability must be strictly between 0 and 1")
        if self.alphabet_size != len(Phoneme):
            raise ValueError(
                "alphabet_size must equal the complete script-neutral Phoneme inventory"
            )

    def log_probability(self, piece: PhonologicalForm) -> float:
        length = len(piece.symbols)
        continuation = (
            0.0
            if length == 1
            else (length - 1) * math.log1p(-self.stop_probability)
        )
        return (
            math.log(self.stop_probability)
            + continuation
            - length * math.log(self.alphabet_size)
        )

    def probability(self, piece: PhonologicalForm) -> float:
        return math.exp(self.log_probability(piece))

    def length_mass(self, length: int) -> float:
        if length < 1:
            raise ValueError("length must be >= 1")
        return self.stop_probability * (
            (1.0 - self.stop_probability) ** (length - 1)
        )


class BaseMeasurePieceScorer:
    r"""Production fixed-pass score with coherent mass for inactive pieces.

    For a finite active count map and normalized countable base measure H::

        P(p) = (count(p) + alpha * H(p)) / (N + alpha)

    The active inventory need not enumerate unseen strings, and changing the
    number of materialized candidates does not change any probability.
    """

    def __init__(
        self,
        counts: Mapping[PhonologicalForm, float],
        *,
        alpha: float,
        lambda_: float,
        kappa: float,
        beta: float,
        tau: float,
        base_measure: GeometricPhonemeBaseMeasure = GeometricPhonemeBaseMeasure(),
    ) -> None:
        if alpha <= 0.0:
            raise ValueError("alpha must be > 0")
        if lambda_ < 0.0 or kappa < 0.0 or beta < 0.0:
            raise ValueError("lambda_, kappa, and beta must be >= 0")
        if tau <= 0.0:
            raise ValueError("tau must be > 0")
        self.counts = {
            piece: float(count)
            for piece, count in counts.items()
            if float(count) > 0.0
        }
        if any(
            isinstance(count, bool)
            or not math.isfinite(float(count))
            or float(count) < 0.0
            for count in counts.values()
        ):
            raise ValueError("piece counts must be finite and nonnegative")
        self.alpha = alpha
        self.lambda_ = lambda_
        self.kappa = kappa
        self.beta = beta
        self.tau = tau
        self.base_measure = base_measure
        self.total_count = sum(self.counts.values())
        self.denominator = self.total_count + alpha
        self.score_calls = 0
        self.store_lookups = 0
        self.active_hits = 0
        self.inactive_misses = 0

    def probability(self, piece: PhonologicalForm) -> float:
        return (
            self.counts.get(piece, 0.0)
            + self.alpha * self.base_measure.probability(piece)
        ) / self.denominator

    def complexity_increment(self, piece: PhonologicalForm) -> float:
        count = self.counts.get(piece, 0.0)
        amplitude = self.lambda_ * (
            self.kappa + self.beta * len(piece.symbols)
        )
        return amplitude * math.log1p(1.0 / (self.tau + count))

    def score(self, piece: PhonologicalForm) -> float:
        self.score_calls += 1
        self.store_lookups += 1
        if piece in self.counts:
            self.active_hits += 1
        else:
            self.inactive_misses += 1
        probability = self.probability(piece)
        return math.log(max(probability, 1e-300)) - self.complexity_increment(
            piece
        )

    def payload(self) -> dict[str, float | int | str]:
        return {
            "probability_semantics": (
                "(count(p)+alpha*H(p))/(sum_active_counts+alpha)"
            ),
            "base_measure": "geometric_length_uniform_phoneme",
            "base_stop_probability": self.base_measure.stop_probability,
            "alphabet_size": self.base_measure.alphabet_size,
            "active_piece_types": len(self.counts),
            "active_count_total": self.total_count,
            "alpha": self.alpha,
            "lambda": self.lambda_,
            "kappa": self.kappa,
            "beta": self.beta,
            "tau": self.tau,
        }
