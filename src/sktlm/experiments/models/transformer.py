"""The existing very small decoder-only Transformer language model."""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class TinyDecoderOnlyTransformer(nn.Module):
    """Minimal causal Transformer for next-token prediction."""

    def __init__(
        self,
        vocab_size: int,
        context_length: int,
        n_embd: int,
        n_head: int,
        n_layer: int,
        dropout: float = 0.0,
    ) -> None:
        super().__init__()
        self.context_length = context_length
        self.token_embedding = nn.Embedding(vocab_size, n_embd)
        self.position_embedding = nn.Embedding(context_length, n_embd)
        layer = nn.TransformerEncoderLayer(
            d_model=n_embd,
            nhead=n_head,
            dim_feedforward=4 * n_embd,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.blocks = nn.TransformerEncoder(layer, num_layers=n_layer)
        self.final_norm = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size, bias=False)

    def forward(
        self,
        input_ids: torch.Tensor,
        targets: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor | None]:
        """Return logits and optional next-token cross-entropy loss."""
        batch_size, seq_len = input_ids.shape
        if seq_len > self.context_length:
            raise ValueError(f"sequence length {seq_len} exceeds context length {self.context_length}")

        positions = torch.arange(seq_len, device=input_ids.device)
        hidden = self.token_embedding(input_ids) + self.position_embedding(positions)[None, :, :]
        causal_mask = torch.triu(
            torch.full((seq_len, seq_len), float("-inf"), device=input_ids.device),
            diagonal=1,
        )
        hidden = self.blocks(hidden, mask=causal_mask, is_causal=True)
        hidden = self.final_norm(hidden)
        logits = self.lm_head(hidden)

        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.reshape(batch_size * seq_len, -1), targets.reshape(batch_size * seq_len))
        return logits, loss
