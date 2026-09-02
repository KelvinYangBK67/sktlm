"""Cached reference model and tiny expected-count learning loop for S1M2."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping

from sktlm.latent.phonology import PhonologicalForm
from sktlm.pieces.inference import PieceEvaluation, evaluate_piece_lattice
from sktlm.pieces.lattice import build_piece_lattice
from sktlm.pieces.scorer import (
    ExpectedCountPieceScorer,
    NeutralPieceScorer,
    PieceScorer,
)


@dataclass(frozen=True, slots=True)
class PieceModelConfig:
    """Explicit development parameters for the P0 reference semantics."""

    max_piece_length: int = 8
    rho: float = 0.5
    alpha: float = 0.1
    lambda_: float = 0.5
    kappa: float = 1.0
    beta: float = 0.25
    tau: float = 1.0
    top_k: int = 8

    def __post_init__(self) -> None:
        if self.max_piece_length < 1:
            raise ValueError("max_piece_length must be >= 1")
        if not 0.0 < self.rho < 1.0:
            raise ValueError("rho must be strictly between 0 and 1")
        if self.alpha <= 0.0:
            raise ValueError("alpha must be > 0")
        if self.lambda_ < 0.0 or self.kappa < 0.0 or self.beta < 0.0:
            raise ValueError("lambda_, kappa, and beta must be >= 0")
        if self.tau <= 0.0:
            raise ValueError("tau must be > 0")
        if self.top_k < 1:
            raise ValueError("top_k must be >= 1")

    def payload(self) -> dict[str, float | int]:
        return {
            "max_piece_length": self.max_piece_length,
            "rho": self.rho,
            "alpha": self.alpha,
            "lambda": self.lambda_,
            "kappa": self.kappa,
            "beta": self.beta,
            "tau": self.tau,
            "top_k": self.top_k,
        }


class PieceModel:
    """A cached ``FormScorer`` implementation for tiny reference inference."""

    def __init__(
        self,
        config: PieceModelConfig = PieceModelConfig(),
        *,
        scorer: PieceScorer | None = None,
    ) -> None:
        self.config = config
        self.scorer = NeutralPieceScorer() if scorer is None else scorer
        self._cache: dict[PhonologicalForm, PieceEvaluation] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    @classmethod
    def neutral(
        cls,
        config: PieceModelConfig = PieceModelConfig(),
    ) -> "PieceModel":
        return cls(config, scorer=NeutralPieceScorer())

    @classmethod
    def from_expected_counts(
        cls,
        counts: Mapping[PhonologicalForm, float],
        config: PieceModelConfig = PieceModelConfig(),
    ) -> "PieceModel":
        scorer = ExpectedCountPieceScorer(
            counts,
            alpha=config.alpha,
            lambda_=config.lambda_,
            kappa=config.kappa,
            beta=config.beta,
            tau=config.tau,
        )
        return cls(config, scorer=scorer)

    def evaluate(self, form: PhonologicalForm) -> PieceEvaluation:
        cached = self._cache.get(form)
        if cached is not None:
            self.cache_hits += 1
            return cached
        self.cache_misses += 1
        lattice = build_piece_lattice(
            form,
            max_piece_length=self.config.max_piece_length,
        )
        evaluation = evaluate_piece_lattice(
            lattice,
            self.scorer,
            rho=self.config.rho,
            top_k=self.config.top_k,
        )
        self._cache[form] = evaluation
        return evaluation

    def score(self, form: PhonologicalForm) -> float:
        """Implement the existing outer M1 ``FormScorer`` protocol."""

        return self.evaluate(form).log_score

    def expected_counts_from_outer(
        self,
        outer_expected_counts: Mapping[PhonologicalForm, float],
    ) -> dict[PhonologicalForm, float]:
        r"""Apply ``sum_u E[count(u)|x] * E[count(p)|u]`` exactly."""

        piece_counts: dict[PhonologicalForm, float] = defaultdict(float)
        for form, outer_mass in sorted(
            outer_expected_counts.items(),
            key=lambda item: item[0].key,
        ):
            if outer_mass <= 0.0:
                continue
            evaluation = self.evaluate(form)
            for piece, conditional_count in evaluation.expected_piece_counts.items():
                piece_counts[piece] += outer_mass * conditional_count
        return dict(piece_counts)


@dataclass(frozen=True, slots=True)
class PieceTrainingPass:
    pass_index: int
    neutral: bool
    weighted_log_score: float
    expected_piece_counts: dict[PhonologicalForm, float]


@dataclass(frozen=True, slots=True)
class ReferencePieceTrainingResult:
    model: PieceModel
    history: tuple[PieceTrainingPass, ...]


def fit_reference_piece_model(
    form_weights: Mapping[PhonologicalForm, float],
    *,
    passes: int = 2,
    config: PieceModelConfig = PieceModelConfig(),
) -> ReferencePieceTrainingResult:
    """Run a tiny in-memory neutral-count-update loop.

    This is intentionally a reference/synthetic path, not a full-corpus M2
    trainer. The returned model is parameterized by the final pass's expected
    counts and is ready for the next inference pass.
    """

    if passes < 1:
        raise ValueError("passes must be >= 1")
    weights = {
        form: float(weight)
        for form, weight in form_weights.items()
        if float(weight) > 0.0
    }
    if not weights:
        raise ValueError("Reference training requires positive form weights.")

    model = PieceModel.neutral(config)
    history: list[PieceTrainingPass] = []
    for pass_index in range(1, passes + 1):
        expected_counts = model.expected_counts_from_outer(weights)
        weighted_log_score = sum(
            weight * model.evaluate(form).log_score
            for form, weight in sorted(weights.items(), key=lambda item: item[0].key)
        )
        history.append(
            PieceTrainingPass(
                pass_index=pass_index,
                neutral=pass_index == 1,
                weighted_log_score=weighted_log_score,
                expected_piece_counts=expected_counts,
            )
        )
        model = PieceModel.from_expected_counts(expected_counts, config)
    return ReferencePieceTrainingResult(model=model, history=tuple(history))
