"""Minimal generation script for the tiny Sanskrit LM."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import sentencepiece as spm
import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model.tiny_transformer import TinyDecoderOnlyTransformer  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate text from a tiny checkpoint.")
    parser.add_argument("--checkpoint", type=Path, default=Path("checkpoints/tiny_overfit.pt"))
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=40)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output", type=Path, help="Optional file to append the result to.")
    return parser.parse_args()


def build_model(config: dict, device: str) -> TinyDecoderOnlyTransformer:
    """Build a model from checkpoint config."""
    return TinyDecoderOnlyTransformer(
        vocab_size=int(config["vocab_size"]),
        context_length=int(config["context_length"]),
        n_embd=int(config["n_embd"]),
        n_head=int(config["n_head"]),
        n_layer=int(config["n_layer"]),
        dropout=float(config["dropout"]),
    ).to(device)


@torch.no_grad()
def generate(
    model: TinyDecoderOnlyTransformer,
    input_ids: list[int],
    max_new_tokens: int,
    temperature: float,
    top_k: int,
    banned_ids: set[int],
    eos_id: int,
    device: str,
) -> list[int]:
    """Generate token ids with greedy decoding or simple top-k sampling."""
    model.eval()
    ids = torch.tensor([input_ids], dtype=torch.long, device=device)
    for _ in range(max_new_tokens):
        context = ids[:, -model.context_length :]
        logits, _ = model(context)
        next_logits = logits[:, -1, :]
        for token_id in banned_ids:
            if 0 <= token_id < next_logits.shape[-1]:
                next_logits[:, token_id] = float("-inf")
        if temperature <= 0:
            next_id = torch.argmax(next_logits, dim=-1, keepdim=True)
        else:
            next_logits = next_logits / temperature
            if top_k > 0:
                values, indices = torch.topk(next_logits, k=min(top_k, next_logits.shape[-1]))
                probs = torch.softmax(values, dim=-1)
                next_id = indices.gather(-1, torch.multinomial(probs, num_samples=1))
            else:
                probs = torch.softmax(next_logits, dim=-1)
                next_id = torch.multinomial(probs, num_samples=1)
        ids = torch.cat([ids, next_id], dim=1)
        if eos_id >= 0 and int(next_id.item()) == eos_id:
            break
    return ids[0].tolist()


def main() -> None:
    """Load checkpoint and tokenizer, generate text, and print it."""
    args = parse_args()
    checkpoint = torch.load(args.checkpoint, map_location=args.device)
    config = checkpoint["config"]

    tokenizer = spm.SentencePieceProcessor(model_file=str(config["tokenizer_path"]))
    model = build_model(config, args.device)
    model.load_state_dict(checkpoint["model_state_dict"])

    prompt_ids = tokenizer.encode(args.prompt, out_type=int)
    if not prompt_ids:
        prompt_ids = [tokenizer.bos_id()] if tokenizer.bos_id() >= 0 else [tokenizer.unk_id()]
    banned_ids = {tokenizer.unk_id(), tokenizer.bos_id(), tokenizer.pad_id()}
    banned_ids = {token_id for token_id in banned_ids if token_id >= 0}

    output_ids = generate(
        model=model,
        input_ids=prompt_ids,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_k=args.top_k,
        banned_ids=banned_ids,
        eos_id=tokenizer.eos_id(),
        device=args.device,
    )
    generated_text = tokenizer.decode(output_ids)
    result = (
        f"prompt: {args.prompt}\n"
        f"max_new_tokens: {args.max_new_tokens}\n"
        f"temperature: {args.temperature}\n"
        f"generated: {generated_text}\n"
    )

    print(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("a", encoding="utf-8") as file:
            file.write(result + "\n")


if __name__ == "__main__":
    main()
