"""End-to-end smoke test for tokenizer-independent controlled tiny training."""

import csv

import torch

from sktlm.training.tiny import run_controlled_training


def test_controlled_character_training_uses_fixed_text_splits(tmp_path) -> None:
    rows = []
    for split, text in (
        ("train", "devaścarāmaśca"),
        ("dev", "devodhāvati"),
    ):
        path = tmp_path / f"{split}.txt"
        path.write_text(text, encoding="utf-8")
        rows.append(
            {
                "path": str(path),
                "canonical_path": str(path),
                "canonical_script": "iast",
                "source": "fixture",
                "layer": "test",
                "document_id": f"doc_{split}",
                "split": split,
            }
        )
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    config = {
        "data": {"manifest": str(manifest), "eval_split": "dev"},
        "representation": {"script": "iast", "spacing": "continuous"},
        "tokenizer": {"type": "character"},
        "model": {"type": "tiny_transformer", "context_length": 4, "n_embd": 8, "n_head": 2, "n_layer": 1, "dropout": 0.0},
        "training": {
            "output_dir": str(tmp_path / "output"),
            "batch_size": 2,
            "learning_rate": 0.001,
            "max_steps": 1,
            "eval_interval": 1,
            "max_train_examples": 4,
            "max_eval_examples": 4,
        },
        "seed": 0,
        "evaluation": {},
    }
    checkpoint_path = run_controlled_training(config, "cpu")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    assert checkpoint["tokenizer"]["type"] == "character"
    assert checkpoint["normalized_likelihood"]["bits_per_character"] is not None
    assert checkpoint["normalized_likelihood"]["bits_per_byte"] is not None
