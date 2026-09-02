"""Bounded-memory common downstream LM training and scoring for baseline cells."""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch.nn import functional as F

from sktlm.evaluation.likelihood import LikelihoodMetrics, score_autoregressive_sequences
from sktlm.experiments.baselines.frozen import FrozenRepresentationCatalog
from sktlm.experiments.baselines.matrix import BaselineRunSpec, DownstreamLMSettings
from sktlm.experiments.models.transformer import TinyDecoderOnlyTransformer
from sktlm.experiments.training.dataset import EncodedSegment
from sktlm.representations.canonical import RepresentedSegment
from sktlm.tokenizers.base import Tokenizer


@dataclass(frozen=True, slots=True)
class DownstreamResult:
    metrics: dict[str, Any]
    checkpoint_path: Path


def _encode_segment(
    segment: RepresentedSegment,
    tokenizer: Tokenizer,
    contract: DownstreamLMSettings,
) -> EncodedSegment:
    ids = list(tokenizer.encode(segment.text).ids)
    if contract.prepend_bos and tokenizer.bos_id is not None:
        ids.insert(0, tokenizer.bos_id)
    if contract.append_eos and tokenizer.eos_id is not None:
        ids.append(tokenizer.eos_id)
    return EncodedSegment(segment.segment_id, segment.split, segment.text, tuple(ids))


def _training_blocks(
    segments: Iterable[RepresentedSegment],
    tokenizer: Tokenizer,
    contract: DownstreamLMSettings,
) -> Iterator[tuple[tuple[int, ...], tuple[int, ...]]]:
    """Stream the same full-context windows as SegmentBlockDataset."""
    width = contract.context_length
    for segment in segments:
        ids = _encode_segment(segment, tokenizer, contract).ids
        for start in range(max(0, len(ids) - width)):
            chunk = ids[start : start + width + 1]
            yield chunk[:-1], chunk[1:]


def _buffered_shuffle(
    values: Iterable[tuple[tuple[int, ...], tuple[int, ...]]],
    *,
    buffer_size: int,
    seed: int,
) -> Iterator[tuple[tuple[int, ...], tuple[int, ...]]]:
    """Deterministically shuffle fixed-size chunks with bounded memory."""
    randomizer = random.Random(seed)
    iterator = iter(values)
    while True:
        block = list(itertools.islice(iterator, buffer_size))
        if not block:
            return
        randomizer.shuffle(block)
        yield from block


def _paired_evaluation_segments(
    catalog: FrozenRepresentationCatalog,
    spec: BaselineRunSpec,
    contract: DownstreamLMSettings,
    tokenizer: Tokenizer,
    max_eval_segments: int | None,
    counters: dict[str, int],
) -> Iterator[EncodedSegment]:
    surfaces = catalog.iter_segments(
        spec.cell.script,
        spec.cell.spacing,
        splits={contract.eval_split},
        max_segments=max_eval_segments,
    )
    canonical_units = catalog.iter_segments(
        "iast",
        "surface_word",
        splits={contract.eval_split},
        max_segments=max_eval_segments,
    )
    sentinel = object()
    for surface, canonical in itertools.zip_longest(surfaces, canonical_units, fillvalue=sentinel):
        if surface is sentinel or canonical is sentinel:
            raise ValueError("canonical-unit reference and evaluated representation differ in length")
        assert isinstance(surface, RepresentedSegment)
        assert isinstance(canonical, RepresentedSegment)
        if surface.segment_id != canonical.segment_id or surface.split != canonical.split:
            raise ValueError(
                "canonical-unit reference identity mismatch: "
                f"{surface.segment_id} != {canonical.segment_id}"
            )
        counters["segments"] += 1
        counters["characters"] += len(surface.text)
        counters["bytes"] += len(surface.text.encode("utf-8"))
        counters["canonical_units"] += len(canonical.text)
        yield _encode_segment(surface, tokenizer, contract)


def run_common_downstream_lm(
    catalog: FrozenRepresentationCatalog,
    spec: BaselineRunSpec,
    tokenizer: Tokenizer,
    artifact_dir: Path,
    *,
    device: str | None = None,
    max_train_segments: int | None = None,
    max_eval_segments: int | None = None,
    max_steps: int | None = None,
) -> DownstreamResult:
    """Train and score the frozen common protocol without materializing the corpus."""
    contract = spec.settings.downstream_lm
    runtime_device = device or contract.device
    runtime_steps = max_steps if max_steps is not None else contract.max_steps
    if runtime_steps <= 0:
        raise ValueError("common downstream max_steps must be positive")
    if runtime_device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("common downstream contract requests CUDA but CUDA is unavailable")
    if runtime_device == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("common downstream contract requests MPS but MPS is unavailable")

    random.seed(spec.settings.seed)
    torch.manual_seed(spec.settings.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(spec.settings.seed)
    previous_determinism = torch.are_deterministic_algorithms_enabled()
    torch.use_deterministic_algorithms(contract.deterministic_algorithms)
    try:
        model = TinyDecoderOnlyTransformer(
            vocab_size=tokenizer.vocab_size,
            context_length=contract.context_length,
            n_embd=contract.n_embd,
            n_head=contract.n_head,
            n_layer=contract.n_layer,
            dropout=contract.dropout,
        ).to(runtime_device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=contract.learning_rate)
        train_segments = catalog.iter_segments(
            spec.cell.script,
            spec.cell.spacing,
            splits={"train"},
            max_segments=max_train_segments,
        )
        shuffled = _buffered_shuffle(
            _training_blocks(train_segments, tokenizer, contract),
            buffer_size=contract.shuffle_buffer_blocks,
            seed=spec.settings.seed,
        )
        losses: list[float] = []
        model.train()
        for step in range(runtime_steps):
            examples = list(itertools.islice(shuffled, contract.batch_size))
            if len(examples) != contract.batch_size:
                raise ValueError(
                    "common downstream training budget exceeds available segment-contained "
                    f"blocks at step {step + 1}"
                )
            input_ids = torch.tensor(
                [example[0] for example in examples], dtype=torch.long, device=runtime_device
            )
            targets = torch.tensor(
                [example[1] for example in examples], dtype=torch.long, device=runtime_device
            )
            logits, _ = model(input_ids)
            loss = F.cross_entropy(
                logits.reshape(-1, tokenizer.vocab_size), targets.reshape(-1)
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.item()))

        counters = {"segments": 0, "characters": 0, "bytes": 0, "canonical_units": 0}
        encoded_eval = _paired_evaluation_segments(
            catalog,
            spec,
            contract,
            tokenizer,
            max_eval_segments,
            counters,
        )
        total_nll, scored_tokens = score_autoregressive_sequences(
            model,
            encoded_eval,
            contract.context_length,
            runtime_device,
        )
        if counters["segments"] == 0 or scored_tokens == 0:
            raise ValueError("common downstream scoring requires non-empty evaluation targets")
        normalized = LikelihoodMetrics(
            total_nll=total_nll,
            tokens=scored_tokens,
            characters=counters["characters"],
            bytes=counters["bytes"],
            canonical_units=counters["canonical_units"],
        )
        output_dir = artifact_dir / "downstream_lm"
        output_dir.mkdir(parents=True, exist_ok=False)
        checkpoint_path = output_dir / "tiny_decoder_only_transformer.pt"
        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "contract": contract.as_dict(),
                "runtime_device": runtime_device,
                "runtime_steps": runtime_steps,
                "seed": spec.settings.seed,
                "condition_id": spec.cell.condition_id,
                "tokenizer": tokenizer.fingerprint_payload(),
                "final_train_loss": losses[-1],
                "normalized_likelihood": normalized.as_dict(),
            },
            checkpoint_path,
        )
    finally:
        torch.use_deterministic_algorithms(previous_determinism)

    metrics = {
        "common_downstream_contract_version": contract.contract_version,
        "common_downstream_model_class": contract.model_class,
        "common_downstream_optimizer": contract.optimizer,
        "common_downstream_device": runtime_device,
        "common_downstream_train_steps": runtime_steps,
        "common_downstream_batch_size": contract.batch_size,
        "common_downstream_context_length": contract.context_length,
        "common_downstream_scoring_protocol": contract.scoring_protocol,
        "common_downstream_canonical_unit": contract.canonical_unit,
        "common_downstream_total_nll": normalized.total_nll,
        "common_downstream_scored_tokens": normalized.tokens,
        "common_downstream_characters": normalized.characters,
        "common_downstream_bytes": normalized.bytes,
        "common_downstream_canonical_units": normalized.canonical_units,
        "common_downstream_bits_per_character": normalized.bits_per_character,
        "common_downstream_bits_per_byte": normalized.bits_per_byte,
        "bits_per_canonical_unit": normalized.bits_per_canonical_unit,
        "common_downstream_final_train_loss": losses[-1],
        "common_downstream_checkpoint": checkpoint_path.relative_to(artifact_dir).as_posix(),
        "common_downstream_finite": all(
            math.isfinite(value)
            for value in (
                normalized.total_nll,
                normalized.bits_per_character,
                normalized.bits_per_byte,
                normalized.bits_per_canonical_unit,
                losses[-1],
            )
            if value is not None
        ),
    }
    return DownstreamResult(metrics=metrics, checkpoint_path=checkpoint_path)
