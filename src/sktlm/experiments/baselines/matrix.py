"""Versioned schema for the historical 22-cell and valid 18-cell M0 matrix."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from sktlm.representations.validity import (
    IAST_CONTINUOUS_RETIREMENT_ID,
    IAST_CONTINUOUS_RETIREMENT_REASON,
)
from sktlm.tokenizers._surrogate import SURROGATE_SENTENCEPIECE_TRAINER_CONTRACT
from sktlm.tokenizers.sentencepiece import SENTENCEPIECE_TRAINER_CONTRACT


FROZEN_M0_ID = "9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40"
CONDITION_MANIFEST_VERSION = "m0-baselines-v2"
RETIREMENT_DECISION_ID = IAST_CONTINUOUS_RETIREMENT_ID
RETIREMENT_REASON = IAST_CONTINUOUS_RETIREMENT_REASON
VALID = "valid"
RETIRED = "retired"
FORMAL_SCRIPTS = ("iast", "devanagari")
FORMAL_SPACINGS = ("surface_word", "legacy_joined", "continuous")
STANDARD_METHODS = ("bpe", "unigram", "unicode_codepoint")
FORMAL_METHODS = (*STANDARD_METHODS, "aksara_safe_bpe", "surface_lattice")
TOKENIZER_SUPPORTED_METHODS = frozenset(FORMAL_METHODS)
REQUIRED_PROVENANCE = (
    "method",
    "script",
    "spacing",
    "condition_status",
    "retirement_reason",
    "condition_manifest_version",
    "config",
    "seed",
    "code_commit",
    "corpus_freeze_id",
    "canonical_manifest_sha256",
    "representation_manifest_sha256",
    "software_versions",
    "artifact_location",
)


class RetiredConditionError(ValueError):
    """Raised when production tooling is asked to run a retired condition."""


@dataclass(frozen=True, slots=True)
class DownstreamLMSettings:
    """One common model/training/scoring protocol shared by every valid cell."""

    contract_version: str = "m0-common-downstream-lm-v1"
    model_class: str = "TinyDecoderOnlyTransformer"
    context_length: int = 32
    n_embd: int = 64
    n_head: int = 2
    n_layer: int = 2
    dropout: float = 0.0
    batch_size: int = 8
    learning_rate: float = 0.001
    max_steps: int = 20
    shuffle_buffer_blocks: int = 1024
    eval_split: str = "test"
    device: str = "cuda"
    optimizer: str = "AdamW"
    context_policy: str = "segment_contained_sliding_context_v1"
    scoring_protocol: str = "each_within_segment_target_once_v1"
    canonical_unit: str = "frozen_iast_surface_word_unicode_codepoint_v1"
    prepend_bos: bool = True
    append_eos: bool = True
    deterministic_algorithms: bool = True

    def __post_init__(self) -> None:
        if self.contract_version != "m0-common-downstream-lm-v1":
            raise ValueError(f"unsupported downstream LM contract: {self.contract_version}")
        if self.model_class != "TinyDecoderOnlyTransformer":
            raise ValueError(f"unsupported common downstream model: {self.model_class}")
        if self.optimizer != "AdamW":
            raise ValueError(f"unsupported common downstream optimizer: {self.optimizer}")
        if self.eval_split not in {"dev", "test"}:
            raise ValueError("common downstream eval_split must be dev or test")
        if self.device not in {"cpu", "cuda", "mps"}:
            raise ValueError("common downstream device must be cpu, cuda, or mps")
        integral_positive = (
            self.context_length,
            self.n_embd,
            self.n_head,
            self.n_layer,
            self.batch_size,
            self.max_steps,
            self.shuffle_buffer_blocks,
        )
        if any(value <= 0 for value in integral_positive):
            raise ValueError("common downstream integer controls must be positive")
        if self.n_embd % self.n_head:
            raise ValueError("n_embd must be divisible by n_head")
        if self.learning_rate <= 0 or not 0.0 <= self.dropout < 1.0:
            raise ValueError("invalid common downstream learning rate or dropout")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DownstreamLMSettings":
        return cls(
            contract_version=str(value["contract_version"]),
            model_class=str(value["model_class"]),
            context_length=int(value["context_length"]),
            n_embd=int(value["n_embd"]),
            n_head=int(value["n_head"]),
            n_layer=int(value["n_layer"]),
            dropout=float(value["dropout"]),
            batch_size=int(value["batch_size"]),
            learning_rate=float(value["learning_rate"]),
            max_steps=int(value["max_steps"]),
            shuffle_buffer_blocks=int(value["shuffle_buffer_blocks"]),
            eval_split=str(value["eval_split"]),
            device=str(value["device"]),
            optimizer=str(value["optimizer"]),
            context_policy=str(value["context_policy"]),
            scoring_protocol=str(value["scoring_protocol"]),
            canonical_unit=str(value["canonical_unit"]),
            prepend_bos=bool(value["prepend_bos"]),
            append_eos=bool(value["append_eos"]),
            deterministic_algorithms=bool(value["deterministic_algorithms"]),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class BaselineCell:
    """One historical method x script x spacing condition."""

    method: str
    script: str
    spacing: str

    def __post_init__(self) -> None:
        if self.method not in FORMAL_METHODS:
            raise ValueError(f"unsupported historical baseline method: {self.method}")
        if self.script not in FORMAL_SCRIPTS:
            raise ValueError(f"unsupported formal script: {self.script}")
        if self.spacing not in FORMAL_SPACINGS:
            raise ValueError(f"unsupported formal spacing: {self.spacing}")
        if self.method == "aksara_safe_bpe" and (
            self.script != "devanagari" or self.spacing != "continuous"
        ):
            raise ValueError("aksara_safe_bpe is historical only for devanagari/continuous")
        if self.method == "surface_lattice" and self.script != "iast":
            raise ValueError("surface_lattice is historical only for IAST")

    @property
    def condition_id(self) -> str:
        return f"{self.method}__{self.script}__{self.spacing}"

    @property
    def tokenizer_supported(self) -> bool:
        return self.method in TOKENIZER_SUPPORTED_METHODS

    @property
    def expected_status(self) -> str:
        return RETIRED if self.script == "iast" and self.spacing == "continuous" else VALID

    def tokenizer_config(self, *, vocab_size: int) -> dict[str, Any]:
        if self.method in {"bpe", "unigram"}:
            return {
                "type": self.method,
                "vocab_size": vocab_size,
                "sentencepiece_trainer_contract": dict(SENTENCEPIECE_TRAINER_CONTRACT),
            }
        if self.method == "unicode_codepoint":
            return {"type": "character"}
        if self.method == "aksara_safe_bpe":
            return {
                "type": "aksara_safe_bpe",
                "vocab_size": vocab_size,
                "max_piece_atoms": 16,
                "atomizer_contract": "devanagari_aksara_bpe_v1",
                "sentencepiece_trainer_contract": dict(
                    SURROGATE_SENTENCEPIECE_TRAINER_CONTRACT
                ),
            }
        if self.method == "surface_lattice":
            return {
                "type": "surface_lattice",
                "vocab_size": vocab_size,
                "max_piece_atoms": 16,
                "unknown_log_score": -20.0,
                "atomizer_contract": "iast_surface_lattice_v1",
                "likelihood": "complete_dag_logsumexp",
                "sentencepiece_trainer_contract": dict(
                    SURROGATE_SENTENCEPIECE_TRAINER_CONTRACT
                ),
            }
        raise RuntimeError(f"historical method has no tokenizer config: {self.method}")


@dataclass(frozen=True, slots=True)
class ConditionRecord:
    """One versioned status record in the historical matrix manifest."""

    cell: BaselineCell
    status: str
    decision_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {VALID, RETIRED}:
            raise ValueError(f"unsupported condition status: {self.status}")
        if self.status != self.cell.expected_status:
            raise ValueError(
                f"condition status mismatch for {self.cell.condition_id}: "
                f"expected {self.cell.expected_status}, found {self.status}"
            )
        if self.status == RETIRED:
            if self.decision_id != RETIREMENT_DECISION_ID or self.reason != RETIREMENT_REASON:
                raise ValueError(
                    f"retired condition {self.cell.condition_id} must use the unified "
                    "IAST-continuous retirement provenance"
                )
        elif self.decision_id is not None or self.reason is not None:
            raise ValueError(f"valid condition {self.cell.condition_id} cannot have retirement fields")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ConditionRecord":
        return cls(
            cell=BaselineCell(
                method=str(value["method"]),
                script=str(value["script"]),
                spacing=str(value["spacing"]),
            ),
            status=str(value["status"]),
            decision_id=(str(value["decision_id"]) if value.get("decision_id") is not None else None),
            reason=(str(value["reason"]) if value.get("reason") is not None else None),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.cell.condition_id,
            "method": self.cell.method,
            "script": self.cell.script,
            "spacing": self.cell.spacing,
            "status": self.status,
            "decision_id": self.decision_id,
            "reason": self.reason,
        }


def historical_matrix() -> tuple[BaselineCell, ...]:
    """Return the frozen historical design ordering, including retired cells."""
    cells = [
        BaselineCell(method, script, spacing)
        for method in STANDARD_METHODS
        for script in FORMAL_SCRIPTS
        for spacing in FORMAL_SPACINGS
    ]
    cells.append(BaselineCell("aksara_safe_bpe", "devanagari", "continuous"))
    cells.extend(BaselineCell("surface_lattice", "iast", spacing) for spacing in FORMAL_SPACINGS)
    return tuple(cells)


def expected_condition_manifest() -> tuple[ConditionRecord, ...]:
    return tuple(
        ConditionRecord(
            cell=cell,
            status=cell.expected_status,
            decision_id=RETIREMENT_DECISION_ID if cell.expected_status == RETIRED else None,
            reason=RETIREMENT_REASON if cell.expected_status == RETIRED else None,
        )
        for cell in historical_matrix()
    )


def validate_condition_manifest(
    records: Iterable[ConditionRecord],
) -> tuple[ConditionRecord, ...]:
    actual = tuple(records)
    ids = tuple(record.cell.condition_id for record in actual)
    if len(ids) != len(set(ids)):
        raise ValueError("condition manifest contains duplicate cells")
    expected = expected_condition_manifest()
    expected_by_id = {record.cell.condition_id: record for record in expected}
    actual_by_id = {record.cell.condition_id: record for record in actual}
    if set(actual_by_id) != set(expected_by_id):
        missing = sorted(set(expected_by_id) - set(actual_by_id))
        extra = sorted(set(actual_by_id) - set(expected_by_id))
        raise ValueError(f"historical condition manifest mismatch: missing={missing}, extra={extra}")
    for condition_id, expected_record in expected_by_id.items():
        if actual_by_id[condition_id] != expected_record:
            raise ValueError(f"condition manifest provenance mismatch: {condition_id}")
    if len(actual) != 22:
        raise ValueError(f"historical condition manifest must contain 22 cells, found {len(actual)}")
    return actual


def formal_matrix() -> tuple[BaselineCell, ...]:
    """Return the 18 representation-valid production cells."""
    return tuple(record.cell for record in expected_condition_manifest() if record.status == VALID)


def retired_matrix() -> tuple[BaselineCell, ...]:
    """Return the four historical IAST-continuous cells that production rejects."""
    return tuple(record.cell for record in expected_condition_manifest() if record.status == RETIRED)


def validate_formal_matrix(cells: Iterable[BaselineCell]) -> tuple[BaselineCell, ...]:
    """Reject missing, duplicate, extra, renamed, or retired production cells."""
    actual = tuple(cells)
    actual_keys = tuple((cell.method, cell.script, cell.spacing) for cell in actual)
    if len(actual_keys) != len(set(actual_keys)):
        raise ValueError("formal production matrix contains duplicate cells")
    expected = formal_matrix()
    expected_keys = {(cell.method, cell.script, cell.spacing) for cell in expected}
    actual_key_set = set(actual_keys)
    if actual_key_set != expected_keys:
        missing = sorted(expected_keys - actual_key_set)
        extra = sorted(actual_key_set - expected_keys)
        raise ValueError(f"formal production matrix mismatch: missing={missing}, extra={extra}")
    if len(actual) != 18:
        raise ValueError(f"formal production matrix must contain 18 valid cells, found {len(actual)}")
    return actual


@dataclass(frozen=True, slots=True)
class BaselineMatrixSettings:
    """Shared controls that do not collapse independent cell training."""

    freeze_id: str
    canonical_manifest: Path
    representation_manifest: Path
    artifact_root: Path
    seed: int
    vocab_size: int
    condition_manifest_version: str = CONDITION_MANIFEST_VERSION
    condition_manifest: tuple[ConditionRecord, ...] = field(
        default_factory=expected_condition_manifest
    )
    downstream_lm: DownstreamLMSettings = field(default_factory=DownstreamLMSettings)

    def __post_init__(self) -> None:
        if self.freeze_id != FROZEN_M0_ID:
            raise ValueError(f"unexpected M0 freeze ID: {self.freeze_id}")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        if self.vocab_size <= 4:
            raise ValueError("vocab_size must exceed the four reserved tokenizer IDs")
        if self.condition_manifest_version != CONDITION_MANIFEST_VERSION:
            raise ValueError(
                f"condition manifest version must be {CONDITION_MANIFEST_VERSION}, "
                f"found {self.condition_manifest_version}"
            )
        validate_condition_manifest(self.condition_manifest)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BaselineMatrixSettings":
        raw_manifest = value.get("conditions")
        if not isinstance(raw_manifest, list):
            raise ValueError("baseline matrix config requires an explicit conditions list")
        return cls(
            freeze_id=str(value["freeze_id"]),
            canonical_manifest=Path(str(value["canonical_manifest"])),
            representation_manifest=Path(str(value["representation_manifest"])),
            artifact_root=Path(str(value["artifact_root"])),
            seed=int(value["seed"]),
            vocab_size=int(value["vocab_size"]),
            condition_manifest_version=str(value["condition_manifest_version"]),
            condition_manifest=tuple(ConditionRecord.from_mapping(item) for item in raw_manifest),
            downstream_lm=DownstreamLMSettings.from_mapping(value["downstream_lm"]),
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "BaselineMatrixSettings":
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("baseline matrix config must be a YAML mapping")
        return cls.from_mapping(value)

    def condition(self, condition_id: str) -> ConditionRecord:
        for record in self.condition_manifest:
            if record.cell.condition_id == condition_id:
                return record
        raise ValueError(f"unknown historical baseline condition: {condition_id}")


@dataclass(frozen=True, slots=True)
class BaselineRunSpec:
    """One independently addressed valid production run."""

    cell: BaselineCell
    settings: BaselineMatrixSettings

    @property
    def artifact_dir(self) -> Path:
        return self.settings.artifact_root / self.cell.condition_id / f"seed_{self.settings.seed}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.cell.condition_id,
            "method": self.cell.method,
            "script": self.cell.script,
            "spacing": self.cell.spacing,
            "condition_status": VALID,
            "retirement_reason": None,
            "condition_manifest_version": self.settings.condition_manifest_version,
            "seed": self.settings.seed,
            "corpus_freeze_id": self.settings.freeze_id,
            "canonical_manifest": self.settings.canonical_manifest.as_posix(),
            "representation_manifest": self.settings.representation_manifest.as_posix(),
            "tokenizer": self.cell.tokenizer_config(vocab_size=self.settings.vocab_size),
            "implementation_status": "implemented",
            "artifact_location": self.artifact_dir.as_posix(),
            "required_provenance": list(REQUIRED_PROVENANCE),
        }


def build_run_specs(settings: BaselineMatrixSettings) -> tuple[BaselineRunSpec, ...]:
    records = validate_condition_manifest(settings.condition_manifest)
    cells = validate_formal_matrix(record.cell for record in records if record.status == VALID)
    specs = tuple(BaselineRunSpec(cell, settings) for cell in cells)
    artifact_dirs = tuple(spec.artifact_dir for spec in specs)
    if len(artifact_dirs) != len(set(artifact_dirs)):
        raise ValueError("formal cells do not have independent artifact directories")
    return specs


def build_plan(settings: BaselineMatrixSettings) -> dict[str, Any]:
    specs = build_run_specs(settings)
    retired = [record.as_dict() for record in settings.condition_manifest if record.status == RETIRED]
    return {
        "matrix": "formal_m0_baselines",
        "condition_manifest_version": settings.condition_manifest_version,
        "freeze_id": settings.freeze_id,
        "historical_cell_count": len(settings.condition_manifest),
        "valid_production_cell_count": len(specs),
        "retired_cell_count": len(retired),
        "tokenizer_supported_cell_count": len(specs),
        "pending_method_contract_cell_count": 0,
        "common_downstream_lm": settings.downstream_lm.as_dict(),
        "retired_conditions": retired,
        "cells": [spec.as_dict() for spec in specs],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and print the formal M0 baseline plan")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/baselines/m0_matrix.yaml"),
    )
    parser.add_argument("--check-inputs", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = BaselineMatrixSettings.from_yaml(args.config)
    plan = build_plan(settings)
    if args.check_inputs:
        from sktlm.experiments.baselines.frozen import load_frozen_catalog

        catalog = load_frozen_catalog(settings)
        plan["frozen_input_documents"] = catalog.document_count
        plan["frozen_input_representation_files"] = catalog.representation_file_count
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
