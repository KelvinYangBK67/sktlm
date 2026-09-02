"""Tests for the common bounded-memory downstream LM contract."""

from pathlib import Path

import torch

from sktlm.experiments.baselines.downstream import run_common_downstream_lm
from sktlm.experiments.baselines.matrix import (
    FROZEN_M0_ID,
    BaselineCell,
    BaselineMatrixSettings,
    BaselineRunSpec,
    DownstreamLMSettings,
)
from sktlm.representations.canonical import RepresentedSegment
from sktlm.tokenizers.character import CharacterTokenizer


class FixtureCatalog:
    texts = {
        "train": ("abcdefghijkl", "mnopqrstuvwx"),
        "test": ("abcdef", "mnopqr"),
    }

    def iter_segments(self, script, spacing, *, splits, max_segments=None):
        split = next(iter(splits))
        for index, text in enumerate(self.texts[split]):
            if max_segments is not None and index >= max_segments:
                return
            yield RepresentedSegment(
                document_id=f"doc-{split}",
                segment_id=f"doc-{split}:l{index + 1:08d}",
                split=split,
                text=text,
                source="fixture",
                layer="test",
                script=script,
                spacing=spacing,
            )


def _spec(tmp_path: Path) -> BaselineRunSpec:
    contract = DownstreamLMSettings(
        context_length=2,
        n_embd=8,
        n_head=2,
        n_layer=1,
        batch_size=2,
        max_steps=2,
        shuffle_buffer_blocks=4,
        device="cpu",
    )
    settings = BaselineMatrixSettings(
        freeze_id=FROZEN_M0_ID,
        canonical_manifest=Path("canonical.csv"),
        representation_manifest=Path("representations.csv"),
        artifact_root=tmp_path,
        seed=7,
        vocab_size=32,
        downstream_lm=contract,
    )
    return BaselineRunSpec(BaselineCell("unicode_codepoint", "iast", "surface_word"), settings)


def test_common_downstream_is_deterministic_and_reports_all_normalizations(tmp_path) -> None:
    catalog = FixtureCatalog()
    tokenizer = CharacterTokenizer.train(catalog.texts["train"])
    first = run_common_downstream_lm(
        catalog, _spec(tmp_path / "a"), tokenizer, tmp_path / "a", device="cpu"
    )
    second = run_common_downstream_lm(
        catalog, _spec(tmp_path / "b"), tokenizer, tmp_path / "b", device="cpu"
    )

    assert first.checkpoint_path.is_file()
    assert first.metrics == second.metrics
    assert first.metrics["common_downstream_finite"] is True
    assert first.metrics["common_downstream_bits_per_character"] > 0
    assert first.metrics["common_downstream_bits_per_byte"] > 0
    assert first.metrics["bits_per_canonical_unit"] > 0
    assert first.metrics["common_downstream_canonical_units"] == 12
    checkpoint = torch.load(first.checkpoint_path, map_location="cpu", weights_only=False)
    assert checkpoint["contract"]["scoring_protocol"] == (
        "each_within_segment_target_once_v1"
    )
    assert checkpoint["condition_id"] == "unicode_codepoint__iast__surface_word"
