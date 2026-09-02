"""Config-driven representation/tokenizer diagnostics and optional tiny LM run."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

import yaml

from sktlm.corpus.dataset import load_canonical_segments, represent_segments
from sktlm.evaluation.reporting import write_result_table
from sktlm.evaluation.tokenizer import SandhiFragmentConfig, evaluate_tokenizer
from sktlm.experiments.artifacts import (
    build_data_fingerprint,
    build_tokenizer_fingerprint,
    make_run_id,
    write_run_artifacts,
)
from sktlm.representations.script import RepresentationConfig
from sktlm.representations.validity import require_valid_experimental_representation
from sktlm.tokenizers.factory import build_tokenizer


def load_experiment_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("experiment config must be a YAML mapping")
    required = {"data", "representation", "tokenizer", "model", "seed", "evaluation"}
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"experiment config is missing: {', '.join(missing)}")
    return config


def run_experiment(
    config: dict[str, Any],
    output_root: Path = Path("artifacts"),
    *,
    dry_run: bool = False,
    repo_root: Path = Path("."),
) -> Path:
    """Run shared data/representation/tokenizer diagnostics and write provenance."""
    seed = int(config["seed"])
    data_cfg = config["data"]
    manifest_path = Path(data_cfg["manifest"])
    eval_split = str(data_cfg.get("eval_split", data_cfg.get("split", "test")))
    train_canonical = load_canonical_segments(
        manifest_path,
        {"train"},
        max_segments=data_cfg.get("max_train_segments"),
    )
    eval_canonical = load_canonical_segments(
        manifest_path,
        {eval_split},
        max_segments=data_cfg.get("max_eval_segments"),
    )
    if not train_canonical or not eval_canonical:
        raise ValueError("experiment requires non-empty train and evaluation segment splits")

    run_id = make_run_id(config)
    representation = RepresentationConfig.from_mapping(config["representation"])
    require_valid_experimental_representation(
        representation.script,
        representation.spacing,
        context="generic experiment runner",
    )
    train_segments = represent_segments(train_canonical, representation)
    eval_segments = represent_segments(eval_canonical, representation)
    tokenizer = build_tokenizer(
        config["tokenizer"],
        (segment.text for segment in train_segments),
        model_dir=output_root / run_id / "tokenizer",
    )
    encoded = [(segment.text, tokenizer.encode(segment.text)) for segment in eval_segments]
    patterns = tuple(config["evaluation"].get("sandhi_patterns", SandhiFragmentConfig().patterns))
    diagnostics = evaluate_tokenizer(encoded, SandhiFragmentConfig(patterns))

    metrics: dict[str, Any] = {
        "run_id": run_id,
        "script": representation.script,
        "spacing": representation.spacing,
        "tokenizer": tokenizer.name,
        "vocab_size": tokenizer.vocab_size,
        "seed": seed,
        "train_segments": len(train_segments),
        "test_segments": len(eval_segments) if eval_split == "test" else None,
        "evaluation_split": eval_split,
        "bits_per_character": None,
        "bits_per_byte": None,
        "dry_run": dry_run,
        **diagnostics,
    }
    logs = [
        f"run_id={run_id}",
        f"mode={'dry-run' if dry_run else 'run'}",
        f"representation={representation.script}/{representation.spacing}",
        f"tokenizer={tokenizer.name}",
        f"train_segments={len(train_segments)} eval_segments={len(eval_segments)}",
    ]

    if not dry_run and config["model"].get("type") == "tiny_transformer" and "training" in config:
        import torch

        from sktlm.experiments.training.tiny import run_controlled_training

        runtime_config = copy.deepcopy(config)
        runtime_config["data"]["eval_split"] = eval_split
        runtime_config["training"]["output_dir"] = str(output_root / run_id)
        if not runtime_config["tokenizer"].get("model_path") and hasattr(tokenizer, "model_path"):
            runtime_config["tokenizer"]["model_path"] = str(tokenizer.model_path)
        checkpoint_path = run_controlled_training(runtime_config, str(config["model"].get("device", "cpu")))
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        likelihood = checkpoint["normalized_likelihood"]
        metrics.update(likelihood)
        logs.append(f"checkpoint={checkpoint_path}")
    elif not dry_run:
        logs.append("model training not requested; emitted representation/tokenizer diagnostics only")

    selected_canonical = train_canonical + eval_canonical
    data_fingerprint = build_data_fingerprint(manifest_path, selected_canonical, representation.as_dict(), seed)
    tokenizer_fingerprint = build_tokenizer_fingerprint(
        dict(config["tokenizer"]),
        tokenizer.fingerprint_payload(),
    )
    preview_limit = int(config["evaluation"].get("prediction_examples", 5))
    predictions = [
        {
            "kind": "tokenization_preview",
            "segment_id": segment.segment_id,
            "text": segment.text,
            "ids": list(encoding.ids),
            "pieces": list(encoding.pieces),
            "spans": [list(span) for span in encoding.spans],
        }
        for segment, (_, encoding) in zip(eval_segments[:preview_limit], encoded[:preview_limit])
    ]
    run_dir = write_run_artifacts(
        output_root,
        config,
        metrics,
        data_fingerprint,
        tokenizer_fingerprint,
        predictions,
        logs,
        repo_root,
    )
    write_result_table([metrics], run_dir / "result.csv")
    return run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a controlled sktlm experiment.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_experiment_config(args.config)
    run_dir = run_experiment(config, args.output_root, dry_run=args.dry_run)
    print(f"run artifacts: {run_dir}")


if __name__ == "__main__":
    main()
