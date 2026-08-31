"""Tests for SentencePiece helper behavior and trainer configuration."""

import sys
from types import SimpleNamespace

from sktlm.tokenizers.sentencepiece import iter_processed_texts, train_sentencepiece


def test_iter_processed_texts_is_sorted(tmp_path) -> None:
    (tmp_path / "b.txt").write_text("सीता", encoding="utf-8")
    (tmp_path / "a.txt").write_text("राम", encoding="utf-8")
    (tmp_path / "ignored.csv").write_text("x", encoding="utf-8")
    assert [path.name for path in iter_processed_texts(tmp_path)] == ["a.txt", "b.txt"]


def test_sentencepiece_training_preserves_existing_options(tmp_path, monkeypatch) -> None:
    calls: list[dict] = []

    class FakeTrainer:
        @staticmethod
        def train(**kwargs) -> None:
            calls.append(kwargs)

    monkeypatch.setitem(sys.modules, "sentencepiece", SimpleNamespace(SentencePieceTrainer=FakeTrainer))
    input_path = tmp_path / "corpus.txt"
    input_path.write_text("रामः गच्छति।", encoding="utf-8")

    train_sentencepiece([input_path], tmp_path / "model", 24000, "bpe")

    assert calls == [
        {
            "input": str(input_path),
            "model_prefix": str(tmp_path / "model"),
            "vocab_size": 24000,
            "model_type": "bpe",
            "character_coverage": 1.0,
            "normalization_rule_name": "identity",
            "bos_id": 1,
            "eos_id": 2,
            "unk_id": 0,
            "pad_id": 3,
            "hard_vocab_limit": False,
            "shuffle_input_sentence": False,
            "num_threads": 1,
            "max_sentence_length": 100_000,
        }
    ]
