"""Minimal dry-run experiment and provenance artifact test."""

import csv
import json

from sktlm.experiments.runner import run_experiment


def build_fixture_manifest(tmp_path):
    rows = []
    for split, text in (
        ("train", "devaś ca rāmaś ca"),
        ("dev", "rāmo vanaṃ gacchati"),
        ("test", "devo'pi dhāvati"),
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
    return manifest


def test_minimal_dry_run_writes_metrics_and_fingerprints(tmp_path) -> None:
    config = {
        "data": {"manifest": str(build_fixture_manifest(tmp_path)), "split": "test"},
        "representation": {"script": "devanagari", "spacing": "continuous"},
        "tokenizer": {"type": "character"},
        "model": {"type": "none"},
        "seed": 0,
        "evaluation": {"prediction_examples": 1},
    }
    run_dir = run_experiment(config, tmp_path / "artifacts", dry_run=True)
    expected = {
        "config.yaml",
        "metrics.json",
        "data_fingerprint.json",
        "tokenizer_fingerprint.json",
        "git_commit.txt",
        "predictions.jsonl",
        "logs.txt",
        "result.csv",
    }
    assert {path.name for path in run_dir.iterdir()} == expected

    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["script"] == "devanagari"
    assert metrics["spacing"] == "continuous"
    assert metrics["tokenizer"] == "character"
    assert metrics["bits_per_character"] is None
    assert metrics["token_count"] > 0

    data_fingerprint = json.loads((run_dir / "data_fingerprint.json").read_text(encoding="utf-8"))
    tokenizer_fingerprint = json.loads((run_dir / "tokenizer_fingerprint.json").read_text(encoding="utf-8"))
    assert data_fingerprint["manifest_sha256"]
    assert data_fingerprint["segment_id_split_sha256"]
    assert tokenizer_fingerprint["fingerprint_sha256"]
    assert (run_dir / "git_commit.txt").read_text(encoding="utf-8").strip()


def test_eval_split_key_selects_dev_without_retokenized_split(tmp_path) -> None:
    config = {
        "run_id": "dev-split",
        "data": {"manifest": str(build_fixture_manifest(tmp_path)), "eval_split": "dev"},
        "representation": {"script": "iast", "spacing": "observed"},
        "tokenizer": {"type": "byte"},
        "model": {"type": "none"},
        "seed": 0,
        "evaluation": {"prediction_examples": 1},
    }

    run_dir = run_experiment(config, tmp_path / "artifacts", dry_run=True)
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))

    assert metrics["evaluation_split"] == "dev"
    assert metrics["test_segments"] is None


def test_runner_fits_sentencepiece_only_from_selected_train_segments(tmp_path) -> None:
    config = {
        "run_id": "fitted-bpe",
        "data": {"manifest": str(build_fixture_manifest(tmp_path)), "split": "test"},
        "representation": {"script": "iast", "spacing": "continuous"},
        "tokenizer": {"type": "bpe", "vocab_size": 32},
        "model": {"type": "none"},
        "seed": 0,
        "evaluation": {"prediction_examples": 1},
    }

    run_dir = run_experiment(config, tmp_path / "artifacts", dry_run=True)
    fingerprint = json.loads((run_dir / "tokenizer_fingerprint.json").read_text(encoding="utf-8"))

    assert (run_dir / "tokenizer" / "bpe_32.model").is_file()
    assert fingerprint["runtime"]["model_sha256"]
