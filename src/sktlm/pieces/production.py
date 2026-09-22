"""Finite reference updates for versioned S1M2 reusable-piece semantics.

V2 removes the largest wordform-host contribution. V3 measures symmetric
corroboration across distinct latent phonological wordform host types.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from sktlm.latent.phonology import PhonologicalForm
from sktlm.pieces.model import PieceModel, PieceModelConfig
from sktlm.pieces.objective import (
    S1M2_REUSABLE_PIECES_V2,
    S1M2_REUSABLE_PIECES_V3,
    cross_host_reusable_count,
)
from sktlm.pieces.scorer import (
    BaseMeasurePieceScorer,
    GeometricPhonemeBaseMeasure,
)


@dataclass(frozen=True, slots=True)
class ProductionPieceConfig:
    reference: PieceModelConfig = field(default_factory=PieceModelConfig)
    base_stop_probability: float = 0.5
    objective_model: str = S1M2_REUSABLE_PIECES_V2

    def __post_init__(self) -> None:
        if not 0.0 < self.base_stop_probability < 1.0:
            raise ValueError("base_stop_probability must be strictly between 0 and 1")
        if self.objective_model not in {
            S1M2_REUSABLE_PIECES_V2,
            S1M2_REUSABLE_PIECES_V3,
        }:
            raise ValueError(
                f"unsupported reusable-piece objective: {self.objective_model}"
            )

    def payload(self) -> dict[str, object]:
        semantics = (
            "R(q)=C(q)-max_h S(q,h); q=phonological_form"
            if self.objective_model == S1M2_REUSABLE_PIECES_V2
            else (
                "R_cross(q)=0 if C(q)=0 else "
                "C(q)-sum_h S(q,h)^2/C(q); q=phonological_form"
            )
        )
        return {
            "reference": self.reference.payload(),
            "base_stop_probability": self.base_stop_probability,
            "objective_model": self.objective_model,
            "learned_count_semantics": semantics,
        }


@dataclass(frozen=True, slots=True)
class ProductionPiecePass:
    pass_index: int
    neutral: bool
    weighted_log_score: float
    raw_expected_counts: dict[PhonologicalForm, float]
    max_host_expected_usage: dict[PhonologicalForm, float]
    reusable_counts: dict[PhonologicalForm, float]
    active_piece_counts: dict[PhonologicalForm, float]
    sum_host_support_squared: dict[PhonologicalForm, float] | None = None


@dataclass(frozen=True, slots=True)
class ProductionPieceTrainingResult:
    model: PieceModel
    active_piece_counts: dict[PhonologicalForm, float]
    history: tuple[ProductionPiecePass, ...]
    objective_model: str = S1M2_REUSABLE_PIECES_V2


def select_reusable_inventory(
    host_support: Mapping[tuple[PhonologicalForm, PhonologicalForm], float],
) -> tuple[
    dict[PhonologicalForm, float],
    dict[PhonologicalForm, float],
    dict[PhonologicalForm, float],
]:
    """Return role-collapsed C, M, and R from posterior host usage."""

    raw: dict[PhonologicalForm, float] = defaultdict(float)
    maximum: dict[PhonologicalForm, float] = defaultdict(float)
    for (piece, _host), support in sorted(
        host_support.items(), key=lambda item: (item[0][0].key, item[0][1].key)
    ):
        if support < 0.0:
            raise ValueError("host support must be nonnegative")
        raw[piece] += support
        maximum[piece] = max(maximum[piece], support)
    reusable = {
        piece: max(0.0, count - maximum[piece])
        for piece, count in raw.items()
    }
    return dict(raw), dict(maximum), reusable


def select_cross_host_reusable_inventory(
    host_support: Mapping[tuple[PhonologicalForm, PhonologicalForm], float],
) -> tuple[
    dict[PhonologicalForm, float],
    dict[PhonologicalForm, float],
    dict[PhonologicalForm, float],
    dict[PhonologicalForm, float],
]:
    """Return V3 role-collapsed ``C, Q, M, R_cross`` by wordform host type."""

    by_piece_host: dict[
        tuple[PhonologicalForm, PhonologicalForm], float
    ] = defaultdict(float)
    for (piece, host), support in host_support.items():
        amount = float(support)
        if amount < 0.0:
            raise ValueError("host support must be nonnegative")
        by_piece_host[(piece, host)] += amount
    raw: dict[PhonologicalForm, float] = defaultdict(float)
    squared: dict[PhonologicalForm, float] = defaultdict(float)
    maximum: dict[PhonologicalForm, float] = defaultdict(float)
    for (piece, _host), support in sorted(
        by_piece_host.items(), key=lambda item: (item[0][0].key, item[0][1].key)
    ):
        raw[piece] += support
        squared[piece] += support * support
        maximum[piece] = max(maximum[piece], support)
    reusable = {
        piece: cross_host_reusable_count(count, squared[piece])
        for piece, count in raw.items()
    }
    return dict(raw), dict(squared), dict(maximum), reusable


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
        host_support: dict[
            tuple[PhonologicalForm, PhonologicalForm], float
        ] = defaultdict(float)
        weighted_log_score = 0.0
        for form in observed:
            evaluation = model.evaluate(form)
            weighted_log_score += evaluation.log_score
            for identity, mass in evaluation.expected_piece_counts.items():
                # The observed tiny-gate occurrence has unit outer lexical
                # posterior; retain its exact conditional expected usage.
                host_support[(identity.piece, form)] += mass
        squared: dict[PhonologicalForm, float] | None = None
        if config.objective_model == S1M2_REUSABLE_PIECES_V3:
            raw, squared, maximum, reusable = (
                select_cross_host_reusable_inventory(host_support)
            )
        else:
            raw, maximum, reusable = select_reusable_inventory(host_support)
        active_counts = {
            piece: count for piece, count in reusable.items() if count > 0.0
        }
        history.append(
            ProductionPiecePass(
                pass_index=pass_index,
                neutral=pass_index == 1,
                weighted_log_score=weighted_log_score,
                raw_expected_counts=raw,
                max_host_expected_usage=maximum,
                reusable_counts=reusable,
                active_piece_counts=active_counts,
                sum_host_support_squared=squared,
            )
        )
        model = production_model_from_counts(active_counts, config)
    return ProductionPieceTrainingResult(
        model=model,
        active_piece_counts=active_counts,
        history=tuple(history),
        objective_model=config.objective_model,
    )
