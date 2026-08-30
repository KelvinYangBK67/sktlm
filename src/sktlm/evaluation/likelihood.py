"""Tokenizer-comparable likelihood normalization."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import torch
from torch.nn import functional as F

from sktlm.experiments.training.dataset import EncodedSegment


@dataclass(frozen=True, slots=True)
class LikelihoodMetrics:
    total_nll: float
    tokens: int
    characters: int
    bytes: int
    canonical_units: int | None = None

    @property
    def bits_per_character(self) -> float | None:
        return self.total_nll / math.log(2) / self.characters if self.characters else None

    @property
    def bits_per_byte(self) -> float | None:
        return self.total_nll / math.log(2) / self.bytes if self.bytes else None

    @property
    def bits_per_canonical_unit(self) -> float | None:
        if self.canonical_units is None or self.canonical_units == 0:
            return None
        return self.total_nll / math.log(2) / self.canonical_units

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            **asdict(self),
            "bits_per_character": self.bits_per_character,
            "bits_per_byte": self.bits_per_byte,
            "bits_per_canonical_unit": self.bits_per_canonical_unit,
        }


def normalize_likelihood(
    total_nll: float,
    tokens: int,
    texts: list[str] | tuple[str, ...],
    canonical_units: int | None = None,
) -> LikelihoodMetrics:
    """Normalize a shared total NLL by stable surface character and byte counts."""
    return LikelihoodMetrics(
        total_nll=float(total_nll),
        tokens=int(tokens),
        characters=sum(len(text) for text in texts),
        bytes=sum(len(text.encode("utf-8")) for text in texts),
        canonical_units=canonical_units,
    )


@torch.no_grad()
def score_autoregressive_sequences(
    model,
    segments: list[EncodedSegment],
    context_length: int,
    device: str,
) -> tuple[float, int]:
    """Score every within-segment next-token transition exactly once."""
    was_training = model.training
    model.eval()
    total_nll = 0.0
    token_count = 0
    for segment in segments:
        ids = segment.ids
        for target_position in range(1, len(ids)):
            context_start = max(0, target_position - context_length)
            input_ids = torch.tensor(
                [ids[context_start:target_position]], dtype=torch.long, device=device
            )
            logits, _ = model(input_ids)
            target = torch.tensor([ids[target_position]], dtype=torch.long, device=device)
            loss = F.cross_entropy(logits[:, -1, :], target, reduction="sum")
            total_nll += float(loss.item())
            token_count += 1
    if was_training:
        model.train()
    return total_nll, token_count
