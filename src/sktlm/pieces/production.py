"""Finite active-state updates for the S1M2 production piece semantics.

Inference is exact for each fixed pass. Between passes, only singleton pieces
and pieces supported by multiple observed lexical-form occurrences become
persistent parameters; all other legal pieces remain scoreable through the
normalized base measure.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from sktlm.latent.phonology import PhonologicalForm
from sktlm.pieces.model import PieceModel, PieceModelConfig
from sktlm.pieces.scorer import (
    BaseMeasurePieceScorer,
    GeometricPhonemeBaseMeasure,
)


@dataclass(frozen=True, slots=True)
class ProductionPieceConfig:
    reference: PieceModelConfig = field(default_factory=PieceModelConfig)
    base_stop_probability: float = 0.5
    min_reuse_occurrences: int = 2
    support_epsilon: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 < self.base_stop_probability < 1.0:
            raise ValueError("base_stop_probability must be strictly between 0 and 1")
        if self.min_reuse_occurrences < 2:
            raise ValueError("min_reuse_occurrences must be >= 2")
        if self.support_epsilon < 0.0:
            raise ValueError("support_epsilon must be >= 0")

    def payload(self) -> dict[str, object]:
        return {
            "reference": self.reference.payload(),
            "base_stop_probability": self.base_stop_probability,
            "min_reuse_occurrences": self.min_reuse_occurrences,
            "support_epsilon": self.support_epsilon,
            "activation_semantics": (
                "all observed singletons plus pieces with posterior support in "
                "at least min_reuse_occurrences lexical-form occurrences"
            ),
        }


@dataclass(frozen=True, slots=True)
class ProductionPiecePass:
    pass_index: int
    neutral: bool
    weighted_log_score: float
    expected_piece_counts: dict[PhonologicalForm, float]
    occurrence_support: dict[PhonologicalForm, int]
    active_piece_counts: dict[PhonologicalForm, float]


@dataclass(frozen=True, slots=True)
class ProductionPieceTrainingResult:
    model: PieceModel
    active_piece_counts: dict[PhonologicalForm, float]
    history: tuple[ProductionPiecePass, ...]


def select_reusable_inventory(
    expected_counts: Mapping[PhonologicalForm, float],
    occurrence_support: Mapping[PhonologicalForm, int],
    *,
    min_reuse_occurrences: int,
) -> dict[PhonologicalForm, float]:
    """Select persistent reusable parameters without changing legal candidates."""

    if min_reuse_occurrences < 2:
        raise ValueError("min_reuse_occurrences must be >= 2")
    return {
        piece: float(count)
        for piece, count in sorted(
            expected_counts.items(), key=lambda item: item[0].key
        )
        if float(count) > 0.0
        and (
            len(piece.symbols) == 1
            or occurrence_support.get(piece, 0) >= min_reuse_occurrences
        )
    }


def production_model_from_counts(
    counts: Mapping[PhonologicalForm, float],
    config: ProductionPieceConfig = ProductionPieceConfig(),
) -> PieceModel:
    scorer = BaseMeasurePieceScorer(
        counts,
        alpha=config.reference.alpha,
        lambda_=config.reference.lambda_,
        kappa=config.reference.kappa,
        beta=config.reference.beta,
        tau=config.reference.tau,
        base_measure=GeometricPhonemeBaseMeasure(
            stop_probability=config.base_stop_probability
        ),
    )
    return PieceModel(config.reference, scorer=scorer)


def fit_production_piece_model(
    occurrences: Iterable[PhonologicalForm],
    *,
    passes: int = 3,
    config: ProductionPieceConfig = ProductionPieceConfig(),
) -> ProductionPieceTrainingResult:
    """Run a tiny deterministic multi-pass gate for the production semantics.

    This helper intentionally materializes its tiny synthetic occurrence list.
    It is a correctness gate, not the streaming/full-corpus trainer.
    """

    if passes < 1:
        raise ValueError("passes must be >= 1")
    observed = tuple(occurrences)
    if not observed:
        raise ValueError("production training requires at least one occurrence")

    model = PieceModel.neutral(config.reference)
    active_counts: dict[PhonologicalForm, float] = {}
    history: list[ProductionPiecePass] = []
    for pass_index in range(1, passes + 1):
        expected_counts: dict[PhonologicalForm, float] = defaultdict(float)
        occurrence_support: dict[PhonologicalForm, int] = defaultdict(int)
        weighted_log_score = 0.0
        for form in observed:
            evaluation = model.evaluate(form)
            weighted_log_score += evaluation.log_score
            for piece, mass in evaluation.expected_piece_counts.items():
                expected_counts[piece] += mass
                if mass > config.support_epsilon:
                    occurrence_support[piece] += 1
        active_counts = select_reusable_inventory(
            expected_counts,
            occurrence_support,
            min_reuse_occurrences=config.min_reuse_occurrences,
        )
        history.append(
            ProductionPiecePass(
                pass_index=pass_index,
                neutral=pass_index == 1,
                weighted_log_score=weighted_log_score,
                expected_piece_counts=dict(expected_counts),
                occurrence_support=dict(occurrence_support),
                active_piece_counts=active_counts,
            )
        )
        model = production_model_from_counts(active_counts, config)
    return ProductionPieceTrainingResult(
        model=model,
        active_piece_counts=active_counts,
        history=tuple(history),
    )
