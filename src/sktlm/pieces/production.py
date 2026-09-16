"""Finite active-state updates for the S1M2 production piece semantics.

Inference is exact for each fixed pass. Between passes, only singleton pieces
and positional pieces supported by multiple distinct host lexical-form types
become persistent parameters; all other legal pieces remain scoreable through
the normalized base measure.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from sktlm.latent.phonology import PhonologicalForm
from sktlm.pieces.lattice import PieceIdentity
from sktlm.pieces.model import PieceModel, PieceModelConfig
from sktlm.pieces.scorer import (
    BaseMeasurePieceScorer,
    GeometricPhonemeBaseMeasure,
)


@dataclass(frozen=True, slots=True)
class ProductionPieceConfig:
    reference: PieceModelConfig = field(default_factory=PieceModelConfig)
    base_stop_probability: float = 0.5
    min_reuse_host_types: int = 2
    host_support_threshold: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 < self.base_stop_probability < 1.0:
            raise ValueError("base_stop_probability must be strictly between 0 and 1")
        if self.min_reuse_host_types < 2:
            raise ValueError("min_reuse_host_types must be >= 2")
        if self.host_support_threshold <= 0.0:
            raise ValueError("host_support_threshold must be > 0")

    def payload(self) -> dict[str, object]:
        return {
            "reference": self.reference.payload(),
            "base_stop_probability": self.base_stop_probability,
            "min_reuse_host_types": self.min_reuse_host_types,
            "host_support_threshold": self.host_support_threshold,
            "activation_semantics": (
                "all observed positional singletons plus piece-role identities "
                "with aggregated posterior support >= host_support_threshold in "
                "at least min_reuse_host_types distinct lexical-form types"
            ),
        }


@dataclass(frozen=True, slots=True)
class ProductionPiecePass:
    pass_index: int
    neutral: bool
    weighted_log_score: float
    expected_piece_counts: dict[PieceIdentity, float]
    host_type_support: dict[PieceIdentity, int]
    active_piece_counts: dict[PieceIdentity, float]


@dataclass(frozen=True, slots=True)
class ProductionPieceTrainingResult:
    model: PieceModel
    active_piece_counts: dict[PieceIdentity, float]
    history: tuple[ProductionPiecePass, ...]


def select_reusable_inventory(
    expected_counts: Mapping[PieceIdentity, float],
    host_type_support: Mapping[PieceIdentity, int],
    *,
    min_reuse_host_types: int,
) -> dict[PieceIdentity, float]:
    """Select persistent reusable parameters without changing legal candidates."""

    if min_reuse_host_types < 2:
        raise ValueError("min_reuse_host_types must be >= 2")
    return {
        identity: float(count)
        for identity, count in sorted(
            expected_counts.items(), key=lambda item: item[0].key
        )
        if float(count) > 0.0
        and (
            len(identity.piece.symbols) == 1
            or host_type_support.get(identity, 0) >= min_reuse_host_types
        )
    }


def production_model_from_counts(
    counts: Mapping[PieceIdentity, float],
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
    active_counts: dict[PieceIdentity, float] = {}
    history: list[ProductionPiecePass] = []
    for pass_index in range(1, passes + 1):
        expected_counts: dict[PieceIdentity, float] = defaultdict(float)
        host_support: dict[
            tuple[PieceIdentity, PhonologicalForm], float
        ] = defaultdict(float)
        weighted_log_score = 0.0
        for form in observed:
            evaluation = model.evaluate(form)
            weighted_log_score += evaluation.log_score
            for identity, mass in evaluation.expected_piece_counts.items():
                expected_counts[identity] += mass
                # The observed tiny-gate occurrence has unit lexical posterior.
                # Aggregate it by host type before applying the threshold.
                host_support[(identity, form)] += 1.0
        host_type_support: dict[PieceIdentity, int] = defaultdict(int)
        for (identity, _host), mass in host_support.items():
            if mass >= config.host_support_threshold:
                host_type_support[identity] += 1
        active_counts = select_reusable_inventory(
            expected_counts,
            host_type_support,
            min_reuse_host_types=config.min_reuse_host_types,
        )
        history.append(
            ProductionPiecePass(
                pass_index=pass_index,
                neutral=pass_index == 1,
                weighted_log_score=weighted_log_score,
                expected_piece_counts=dict(expected_counts),
                host_type_support=dict(host_type_support),
                active_piece_counts=active_counts,
            )
        )
        model = production_model_from_counts(active_counts, config)
    return ProductionPieceTrainingResult(
        model=model,
        active_piece_counts=active_counts,
        history=tuple(history),
    )
