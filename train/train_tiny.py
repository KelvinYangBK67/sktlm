"""Minimal local overfit training loop for the tiny Sanskrit LM."""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import torch
import yaml
from torch.utils.data import DataLoader, Subset

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model.tiny_transformer import TinyDecoderOnlyTransformer
from train.dataset import BlockDataset, encode_corpus, split_train_val


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run a tiny LM overfit test.")
    parser.add_argument("--config", type=Path, default=Path("configs/tiny.yaml"))
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


def main() -> None:
    """Run a small overfit test and save a checkpoint."""
    args = parse_args()
    cfg = load_config(args.config)
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
    ).to(args.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(cfg["learning_rate"]))

    initial_train_loss = evaluate(model, train_loader, args.device)
    initial_val_loss = evaluate(model, val_loader, args.device)
    print(f"initial train_loss={initial_train_loss:.4f} val_loss={initial_val_loss:.4f}")

    max_steps = int(cfg["max_steps"])
    eval_interval = int(cfg["eval_interval"])
    step = 0
    while step < max_steps:
        for input_ids, targets in train_loader:
            input_ids = input_ids.to(args.device)
            targets = targets.to(args.device)
            _, loss = model(input_ids, targets)
            assert loss is not None
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            step += 1

            if step % eval_interval == 0 or step == max_steps:
                train_loss = evaluate(model, train_loader, args.device)
                val_loss = evaluate(model, val_loader, args.device)
                print(f"step={step} train_loss={train_loss:.4f} val_loss={val_loss:.4f}")
            if step >= max_steps:
                break

    checkpoint_path = output_dir / "tiny_overfit.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": cfg,
            "initial_train_loss": initial_train_loss,
            "final_train_loss": evaluate(model, train_loader, args.device),
        },
        checkpoint_path,
    )
    print(f"saved checkpoint: {checkpoint_path}")


if __name__ == "__main__":
    main()
