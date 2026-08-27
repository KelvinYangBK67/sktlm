"""Tests for tokenizer-independent likelihood normalization."""

import math

import torch
from torch import nn

from sktlm.evaluation.likelihood import normalize_likelihood, score_autoregressive_sequences
from sktlm.training.dataset import EncodedSegment


def test_bits_per_character_and_byte() -> None:
    metrics = normalize_likelihood(total_nll=10 * math.log(2), tokens=7, texts=["abcde"])
    assert metrics.tokens == 7
    assert metrics.characters == 5
    assert metrics.bytes == 5
    assert metrics.bits_per_character == 2.0
    assert metrics.bits_per_byte == 2.0
    assert metrics.bits_per_canonical_unit is None


def test_utf8_byte_denominator_differs_from_character_denominator() -> None:
    metrics = normalize_likelihood(total_nll=6 * math.log(2), tokens=3, texts=["क"])
    assert metrics.characters == 1
    assert metrics.bytes == 3
    assert metrics.bits_per_character == 6.0
    assert metrics.bits_per_byte == 2.0


class RecordingUniformModel(nn.Module):
    def __init__(self, vocab_size: int) -> None:
        super().__init__()
        self.vocab_size = vocab_size
        self.inputs: list[list[int]] = []

    def forward(self, input_ids, targets=None):
        self.inputs.append(input_ids[0].tolist())
        shape = (*input_ids.shape, self.vocab_size)
        return torch.zeros(shape, device=input_ids.device), None


def test_sequence_scoring_uses_sliding_context_and_scores_each_target_once() -> None:
    model = RecordingUniformModel(vocab_size=10)
    segment = EncodedSegment("segment", "test", "abc", (1, 4, 5, 6, 2))

    total_nll, tokens = score_autoregressive_sequences(model, [segment], 2, "cpu")

    assert tokens == 4
    assert math.isclose(total_nll, 4 * math.log(10), rel_tol=1e-6)
    assert model.inputs == [[1], [1, 4], [4, 5], [5, 6]]
