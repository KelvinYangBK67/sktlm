"""Minimal local overfit training loop for the tiny Sanskrit LM."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import torch
import yaml
from torch.utils.data import DataLoader, Subset

from sktlm.corpus.dataset import load_canonical_segments, represent_segments
from sktlm.evaluation.likelihood import normalize_likelihood, score_autoregressive_sequences
from sktlm.experiments.models.transformer import TinyDecoderOnlyTransformer
from sktlm.tokenizers.factory import build_tokenizer
from sktlm.experiments.training.dataset import (
    BlockDataset,
    SegmentBlockDataset,
    encode_corpus,
    encode_segments,
    split_train_val,
)
from sktlm.representations.script import RepresentationConfig
from sktlm.representations.validity import require_valid_experimental_representation


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run a tiny LM overfit test.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/tiny.yaml"),
    )
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def load_config(path: Path) -> dict:
    """Load YAML config."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@torch.no_grad()
def evaluate(model: TinyDecoderOnlyTransformer, loader: DataLoader, device: str) -> float:
    """Evaluate mean loss over a small loader."""
    model.eval()
    losses: list[float] = []
    for input_ids, targets in loader:
        input_ids = input_ids.to(device)
        targets = targets.to(device)
        _, loss = model(input_ids, targets)
        assert loss is not None
        losses.append(float(loss.item()))
    model.train()
    return sum(losses) / max(1, len(losses))


def run_controlled_training(cfg: dict, device: str) -> Path:
    """Train on fixed canonical segment splits with a configured representation/tokenizer."""
    seed = int(cfg.get("seed", 0))
    random.seed(seed)
    torch.manual_seed(seed)

    data_cfg = cfg["data"]
    training_cfg = cfg["training"]
    model_cfg = cfg["model"]
    representation = RepresentationConfig.from_mapping(cfg["representation"])
    require_valid_experimental_representation(
        representation.script,
        representation.spacing,
        context="controlled LM runner",
    )
    manifest_path = Path(data_cfg["manifest"])
    train_canonical = load_canonical_segments(
        manifest_path,
        {"train"},
        max_segments=data_cfg.get("max_train_segments"),
    )
    eval_split = str(data_cfg.get("eval_split", "dev"))
    eval_canonical = load_canonical_segments(
        manifest_path,
        {eval_split},
        max_segments=data_cfg.get("max_eval_segments"),
    )
    if not train_canonical or not eval_canonical:
        raise ValueError("controlled training requires non-empty train and evaluation text splits")

    train_segments = represent_segments(train_canonical, representation)
    eval_segments = represent_segments(eval_canonical, representation)
    tokenizer = build_tokenizer(
        cfg["tokenizer"],
        (segment.text for segment in train_segments),
        model_dir=Path(training_cfg["output_dir"]) / "tokenizer",
    )
    train_encoded = encode_segments(train_segments, tokenizer)
    eval_encoded = encode_segments(eval_segments, tokenizer)

    context_length = int(model_cfg["context_length"])
    train_dataset = SegmentBlockDataset(train_encoded, context_length)
    eval_dataset = SegmentBlockDataset(eval_encoded, context_length)
    train_limit = min(int(training_cfg.get("max_train_examples", 64)), len(train_dataset))
    eval_limit = min(int(training_cfg.get("max_eval_examples", 16)), len(eval_dataset))
    train_subset = Subset(train_dataset, list(range(train_limit)))
    eval_subset = Subset(eval_dataset, list(range(eval_limit)))
    train_loader = DataLoader(train_subset, batch_size=int(training_cfg["batch_size"]), shuffle=True)
    eval_loader = DataLoader(eval_subset, batch_size=int(training_cfg["batch_size"]), shuffle=False)

    model = TinyDecoderOnlyTransformer(
        vocab_size=tokenizer.vocab_size,
        context_length=context_length,
        n_embd=int(model_cfg["n_embd"]),
        n_head=int(model_cfg["n_head"]),
        n_layer=int(model_cfg["n_layer"]),
        dropout=float(model_cfg.get("dropout", 0.0)),
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(training_cfg["learning_rate"]))
    initial_train_loss = evaluate(model, train_loader, device)
    initial_eval_loss = evaluate(model, eval_loader, device)
    print(f"initial train_loss={initial_train_loss:.4f} {eval_split}_loss={initial_eval_loss:.4f}")

    max_steps = int(training_cfg["max_steps"])
    eval_interval = int(training_cfg["eval_interval"])
    step = 0
    while step < max_steps:
        for input_ids, targets in train_loader:
            input_ids = input_ids.to(device)
            targets = targets.to(device)
            _, loss = model(input_ids, targets)
            assert loss is not None
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            step += 1
            if step % eval_interval == 0 or step == max_steps:
                train_loss = evaluate(model, train_loader, device)
                eval_loss = evaluate(model, eval_loader, device)
                print(f"step={step} train_loss={train_loss:.4f} {eval_split}_loss={eval_loss:.4f}")
            if step >= max_steps:
                break

    total_nll, scored_tokens = score_autoregressive_sequences(model, eval_encoded, context_length, device)
    normalized = normalize_likelihood(total_nll, scored_tokens, [segment.text for segment in eval_segments])
    output_dir = Path(training_cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "tiny_controlled.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": cfg,
            "tokenizer": tokenizer.fingerprint_payload(),
            "initial_train_loss": initial_train_loss,
            "final_train_loss": evaluate(model, train_loader, device),
            "normalized_likelihood": normalized.as_dict(),
        },
        checkpoint_path,
    )
    print(
        f"normalized bits_per_character={normalized.bits_per_character:.4f} "
        f"bits_per_byte={normalized.bits_per_byte:.4f}"
    )
    print(f"saved checkpoint: {checkpoint_path}")
    return checkpoint_path


def run_legacy_training(cfg: dict, device: str) -> Path:
    """Run the first-round token-stream workflow only for compatibility."""
    random.seed(0)
    torch.manual_seed(0)

    tokenizer_path = Path(cfg["tokenizer_path"])
    data_dir = Path(cfg["data_dir"])
    output_dir = Path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    tokens = encode_corpus(data_dir, tokenizer_path, max_tokens=int(cfg["max_train_tokens"]))
    train_tokens, val_tokens = split_train_val(tokens, float(cfg["train_fraction"]))

    context_length = int(cfg["context_length"])
    train_dataset = BlockDataset(train_tokens, context_length)
    val_dataset = BlockDataset(val_tokens, context_length) if len(val_tokens) > context_length else train_dataset

    # Keep the overfit test intentionally tiny and deterministic.
    subset_size = min(64, len(train_dataset))
    train_subset = Subset(train_dataset, list(range(subset_size)))
    val_subset = Subset(val_dataset, list(range(min(16, len(val_dataset)))))

    train_loader = DataLoader(train_subset, batch_size=int(cfg["batch_size"]), shuffle=True)
    val_loader = DataLoader(val_subset, batch_size=int(cfg["batch_size"]), shuffle=False)

    model = TinyDecoderOnlyTransformer(
        vocab_size=int(cfg["vocab_size"]),
        context_length=context_length,
        n_embd=int(cfg["n_embd"]),
        n_head=int(cfg["n_head"]),
        n_layer=int(cfg["n_layer"]),
        dropout=float(cfg["dropout"]),
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(cfg["learning_rate"]))

    initial_train_loss = evaluate(model, train_loader, device)
    initial_val_loss = evaluate(model, val_loader, device)
    print(f"initial train_loss={initial_train_loss:.4f} val_loss={initial_val_loss:.4f}")

    max_steps = int(cfg["max_steps"])
    eval_interval = int(cfg["eval_interval"])
    step = 0
    while step < max_steps:
        for input_ids, targets in train_loader:
            input_ids = input_ids.to(device)
            targets = targets.to(device)
            _, loss = model(input_ids, targets)
            assert loss is not None
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            step += 1

            if step % eval_interval == 0 or step == max_steps:
                train_loss = evaluate(model, train_loader, device)
                val_loss = evaluate(model, val_loader, device)
                print(f"step={step} train_loss={train_loss:.4f} val_loss={val_loss:.4f}")
            if step >= max_steps:
                break

    checkpoint_path = output_dir / "tiny_overfit.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": cfg,
            "initial_train_loss": initial_train_loss,
            "final_train_loss": evaluate(model, train_loader, device),
        },
        checkpoint_path,
    )
    print(f"saved checkpoint: {checkpoint_path}")
    return checkpoint_path


def main() -> None:
    """Run controlled training, with the first-round config retained as an explicit fallback."""
    args = parse_args()
    cfg = load_config(args.config)
    controlled_keys = {"data", "representation", "tokenizer", "model", "training"}
    if controlled_keys.issubset(cfg):
        run_controlled_training(cfg, args.device)
        return
    print("legacy config detected: using the first-round token-stream compatibility workflow")
    run_legacy_training(cfg, args.device)


if __name__ == "__main__":
    main()
