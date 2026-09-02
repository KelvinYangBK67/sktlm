"""Declared expected-count/reweighted-MDL scores for reusable pieces."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Protocol

from sktlm.latent.phonology import PhonologicalForm


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
