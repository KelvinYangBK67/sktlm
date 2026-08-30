"""Smoke tests for the unchanged tiny Transformer architecture."""

import torch

from sktlm.experiments.models.transformer import TinyDecoderOnlyTransformer


def test_tiny_transformer_forward_pass() -> None:
    torch.manual_seed(0)
    model = TinyDecoderOnlyTransformer(
        vocab_size=32,
        context_length=8,
        n_embd=16,
        n_head=2,
        n_layer=2,
        dropout=0.0,
    )
    input_ids = torch.randint(0, 32, (2, 8))
    targets = torch.randint(0, 32, (2, 8))

    logits, loss = model(input_ids, targets)

    assert logits.shape == (2, 8, 32)
    assert loss is not None
    assert torch.isfinite(loss)
