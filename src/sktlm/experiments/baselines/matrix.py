"""Exact schema and dry-run plan for the formal 22-condition M₀ baseline matrix."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


FROZEN_M0_ID = "9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40"
FORMAL_SCRIPTS = ("iast", "devanagari")
FORMAL_SPACINGS = ("surface_word", "legacy_joined", "continuous")
STANDARD_METHODS = ("bpe", "unigram", "unicode_codepoint")
FORMAL_METHODS = (*STANDARD_METHODS, "aksara_safe_bpe", "surface_lattice")
TOKENIZER_SUPPORTED_METHODS = frozenset(FORMAL_METHODS)
REQUIRED_PROVENANCE = (
    "method",
    "script",
    "spacing",
    "config",
    "seed",
    "code_commit",
    "corpus_freeze_id",
    "canonical_manifest_sha256",
    "representation_manifest_sha256",
    "software_versions",
    "artifact_location",
)


@dataclass(frozen=True, slots=True)
class BaselineCell:
    """One independently trained method × script × spacing condition."""

    method: str
    script: str
    spacing: str

    def __post_init__(self) -> None:
        if self.method not in FORMAL_METHODS:
            raise ValueError(f"unsupported formal baseline method: {self.method}")
        if self.script not in FORMAL_SCRIPTS:
            raise ValueError(f"unsupported formal script: {self.script}")
        if self.spacing not in FORMAL_SPACINGS:
            raise ValueError(f"unsupported formal spacing: {self.spacing}")
        if self.method == "aksara_safe_bpe" and (
            self.script != "devanagari" or self.spacing != "continuous"
        ):
            raise ValueError("aksara_safe_bpe is formal only for devanagari/continuous")
        if self.method == "surface_lattice" and self.script != "iast":
            raise ValueError("surface_lattice is formal only for IAST")

    @property
    def condition_id(self) -> str:
        return f"{self.method}__{self.script}__{self.spacing}"

    @property
    def tokenizer_supported(self) -> bool:
        return self.method in TOKENIZER_SUPPORTED_METHODS

    def tokenizer_config(self, *, vocab_size: int) -> dict[str, Any] | None:
        if self.method in {"bpe", "unigram"}:
            return {"type": self.method, "vocab_size": vocab_size}
        if self.method == "unicode_codepoint":
            return {"type": "character"}
        if self.method == "aksara_safe_bpe":
            return {
                "type": "aksara_safe_bpe",
                "vocab_size": vocab_size,
                "max_piece_atoms": 16,
                "atomizer_contract": "devanagari_aksara_bpe_v1",
            }
        if self.method == "surface_lattice":
            return {
                "type": "surface_lattice",
                "vocab_size": vocab_size,
                "max_piece_atoms": 16,
                "unknown_log_score": -20.0,
                "atomizer_contract": "iast_surface_lattice_v1",
                "likelihood": "complete_dag_logsumexp",
            }
        raise RuntimeError(f"formal method has no tokenizer config: {self.method}")


def formal_matrix() -> tuple[BaselineCell, ...]:
    """Return the canonical deterministic ordering of all 22 formal cells."""
    cells = [
        BaselineCell(method, script, spacing)
        for method in STANDARD_METHODS
        for script in FORMAL_SCRIPTS
        for spacing in FORMAL_SPACINGS
    ]
    cells.append(BaselineCell("aksara_safe_bpe", "devanagari", "continuous"))
    cells.extend(BaselineCell("surface_lattice", "iast", spacing) for spacing in FORMAL_SPACINGS)
    return tuple(cells)


def validate_formal_matrix(cells: Iterable[BaselineCell]) -> tuple[BaselineCell, ...]:
    """Reject missing, duplicate, extra, or renamed formal matrix cells."""
    actual = tuple(cells)
    actual_keys = tuple((cell.method, cell.script, cell.spacing) for cell in actual)
    if len(actual_keys) != len(set(actual_keys)):
        raise ValueError("formal baseline matrix contains duplicate cells")

    expected = formal_matrix()
    expected_keys = {(cell.method, cell.script, cell.spacing) for cell in expected}
    actual_key_set = set(actual_keys)
    if actual_key_set != expected_keys:
        missing = sorted(expected_keys - actual_key_set)
        extra = sorted(actual_key_set - expected_keys)
        raise ValueError(f"formal baseline matrix mismatch: missing={missing}, extra={extra}")
    if len(actual) != 22:
        raise ValueError(f"formal baseline matrix must contain 22 cells, found {len(actual)}")
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

    def __post_init__(self) -> None:
        if self.freeze_id != FROZEN_M0_ID:
            raise ValueError(f"unexpected M₀ freeze ID: {self.freeze_id}")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        if self.vocab_size <= 4:
            raise ValueError("vocab_size must exceed the four reserved tokenizer IDs")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BaselineMatrixSettings":
        return cls(
            freeze_id=str(value["freeze_id"]),
            canonical_manifest=Path(str(value["canonical_manifest"])),
            representation_manifest=Path(str(value["representation_manifest"])),
            artifact_root=Path(str(value["artifact_root"])),
            seed=int(value["seed"]),
            vocab_size=int(value["vocab_size"]),
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "BaselineMatrixSettings":
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("baseline matrix config must be a YAML mapping")
        return cls.from_mapping(value)


@dataclass(frozen=True, slots=True)
class BaselineRunSpec:
    """One independently addressed formal run and its frozen-input provenance."""

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
            "seed": self.settings.seed,
            "corpus_freeze_id": self.settings.freeze_id,
            "canonical_manifest": self.settings.canonical_manifest.as_posix(),
            "representation_manifest": self.settings.representation_manifest.as_posix(),
            "tokenizer": self.cell.tokenizer_config(vocab_size=self.settings.vocab_size),
            "implementation_status": (
                "implemented" if self.cell.tokenizer_supported else "pending_method_contract"
            ),
            "artifact_location": self.artifact_dir.as_posix(),
            "required_provenance": list(REQUIRED_PROVENANCE),
        }


def build_run_specs(settings: BaselineMatrixSettings) -> tuple[BaselineRunSpec, ...]:
    cells = validate_formal_matrix(formal_matrix())
    specs = tuple(BaselineRunSpec(cell, settings) for cell in cells)
    artifact_dirs = tuple(spec.artifact_dir for spec in specs)
    if len(artifact_dirs) != len(set(artifact_dirs)):
        raise ValueError("formal cells do not have independent artifact directories")
    return specs


def build_plan(settings: BaselineMatrixSettings) -> dict[str, Any]:
    specs = build_run_specs(settings)
    supported = sum(spec.cell.tokenizer_supported for spec in specs)
    return {
        "matrix": "formal_m0_baselines",
        "freeze_id": settings.freeze_id,
        "formal_cell_count": len(specs),
        "tokenizer_supported_cell_count": supported,
        "pending_method_contract_cell_count": len(specs) - supported,
        "cells": [spec.as_dict() for spec in specs],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and print the formal M₀ baseline plan")
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
