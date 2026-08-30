"""Integration check that the tracked tiny checkpoint still matches the model."""

from pathlib import Path

import torch

from sktlm.models.transformer import TinyDecoderOnlyTransformer


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_existing_tiny_checkpoint_loads() -> None:
    checkpoint = torch.load(REPO_ROOT / "checkpoints" / "tiny_overfit.pt", map_location="cpu", weights_only=False)
    config = checkpoint["config"]
    model = TinyDecoderOnlyTransformer(
        vocab_size=int(config["vocab_size"]),
        context_length=int(config["context_length"]),
        n_embd=int(config["n_embd"]),
        n_head=int(config["n_head"]),
        n_layer=int(config["n_layer"]),
        dropout=float(config["dropout"]),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
