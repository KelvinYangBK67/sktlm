"""Versioned 22-cell production contract for frozen M0 plus derived M0-prime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from sktlm.experiments.baselines.matrix import (
    CONDITION_MANIFEST_VERSION,
FROZEN_M0_ID,
    REQUIRED_PROVENANCE,
    RETIRED,
    VALID,
    BaselineCell,
    BaselineMatrixSettings,
    ConditionRecord,
    DownstreamLMSettings,
    expected_condition_manifest,
)


FULL_M0_DEFINITION_VERSION = "full-m0-v1"
FULL_M0_CONDITION_MANIFEST_VERSION = "full-m0-baselines-v1"
FULL_M0_AGGREGATE_SCHEMA = "full-m0-baseline-aggregate/v1"
M0_PRIME_DERIVATION_ID = "m0-prime-iast-continuous-v1"
M0_PRIME_MANIFEST_SCHEMA = "sktlm-m0-prime-representation/v1"
M0_PRIME_MANIFEST_SHA256 = (
    "3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922"
)
M0_PRIME_SCRIPT = "iast_m0_prime"
M0_PRIME_SPACING = "continuous"
M0_PRIME_SUBSTRATE = "M0-prime"
M0_SUBSTRATE = "M0"
FROZEN_M0_CANONICAL_MANIFEST_SHA256 = (
    "ccec95eedc9ab37634d24d7d8fa2c47fc3189c3960b07cceb87fd48417ab3cb5"
)
FROZEN_M0_REPRESENTATION_MANIFEST_SHA256 = (
    "c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520"
)
M0_PRIME_TOKENIZER_COMPATIBILITY_CONTRACT = "m0-prime-tokenizer-compatibility-v1"
M0_PRIME_SURFACE_LATTICE_CONTRACT = "iast_m0_prime_surface_lattice_v1"

FULL_M0_REQUIRED_PROVENANCE = REQUIRED_PROVENANCE + (
    "substrate",
    "observation_manifest",
    "observation_manifest_sha256",
    "full_m0_definition_version",
    "input_compatibility_contract",
)


@dataclass(frozen=True, slots=True)
class M0PrimeConsumerContract:
    """Pinned read-only identity for one M0-prime manifest and payload tree."""

    manifest: Path
    payload_root: Path
    manifest_sha256: str = M0_PRIME_MANIFEST_SHA256
    derivation_id: str = M0_PRIME_DERIVATION_ID
    manifest_schema: str = M0_PRIME_MANIFEST_SCHEMA
    formal: bool = True

    def __post_init__(self) -> None:
        if self.derivation_id != M0_PRIME_DERIVATION_ID:
            raise ValueError(f"unexpected M0-prime derivation ID: {self.derivation_id}")
        if self.manifest_schema != M0_PRIME_MANIFEST_SCHEMA:
            raise ValueError(f"unexpected M0-prime manifest schema: {self.manifest_schema}")
        if len(self.manifest_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.manifest_sha256
        ):
            raise ValueError("M0-prime manifest SHA-256 must be lowercase hexadecimal")
        if self.formal and self.manifest_sha256 != M0_PRIME_MANIFEST_SHA256:
            raise ValueError("formal M0-prime manifest identity differs from the frozen checkpoint")

    @classmethod
    def fixture(
        cls, *, manifest: Path, payload_root: Path, manifest_sha256: str
    ) -> "M0PrimeConsumerContract":
        """Construct an explicitly non-formal contract for bounded tests only."""
        return cls(
            manifest=manifest,
            payload_root=payload_root,
            manifest_sha256=manifest_sha256,
            formal=False,
        )


@dataclass(frozen=True, slots=True)
class FullM0Cell:
    """One runnable cell in the full-M0 production view."""

    method: str
    script: str
    spacing: str
    substrate: str
    observation_manifest: Path

    def __post_init__(self) -> None:
        if self.substrate == M0_SUBSTRATE:
            BaselineCell(self.method, self.script, self.spacing)
            if self.script == "iast" and self.spacing == "continuous":
                raise ValueError("original M0 IAST continuous is scientifically excluded")
        elif self.substrate == M0_PRIME_SUBSTRATE:
            if self.script != M0_PRIME_SCRIPT or self.spacing != M0_PRIME_SPACING:
                raise ValueError("M0-prime is exposed only as iast_m0_prime/continuous")
            if self.method not in {"bpe", "unigram", "unicode_codepoint", "surface_lattice"}:
                raise ValueError(f"unsupported M0-prime baseline method: {self.method}")
        else:
            raise ValueError(f"unsupported full-M0 substrate: {self.substrate}")

    @property
    def condition_id(self) -> str:
        return f"{self.method}__{self.script}__{self.spacing}"

    @property
    def tokenizer_supported(self) -> bool:
        return True

    def tokenizer_config(self, *, vocab_size: int) -> dict[str, Any]:
        ordinary_script = "iast" if self.script == M0_PRIME_SCRIPT else self.script
        ordinary_spacing = "surface_word" if self.script == M0_PRIME_SCRIPT else self.spacing
        config = BaselineCell(
            self.method, ordinary_script, ordinary_spacing
        ).tokenizer_config(vocab_size=vocab_size)
        if self.substrate == M0_PRIME_SUBSTRATE:
            config["input_compatibility_contract"] = M0_PRIME_TOKENIZER_COMPATIBILITY_CONTRACT
            if self.method == "surface_lattice":
                config["atomizer_contract"] = M0_PRIME_SURFACE_LATTICE_CONTRACT
        return config


@dataclass(frozen=True, slots=True)
class FullM0ConditionRecord:
    cell: FullM0Cell
    role: str

    @property
    def status(self) -> str:
        return VALID

    @property
    def reason(self) -> None:
        return None

    @property
    def decision_id(self) -> None:
        return None

    def __post_init__(self) -> None:
        expected = "m0_prime_replacement" if self.cell.substrate == M0_PRIME_SUBSTRATE else "unchanged_m0"
        if self.role != expected:
            raise ValueError(
                f"full-M0 role mismatch for {self.cell.condition_id}: expected {expected}"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FullM0ConditionRecord":
        return cls(
            cell=FullM0Cell(
                method=str(value["method"]),
                script=str(value["script"]),
                spacing=str(value["spacing"]),
                substrate=str(value["substrate"]),
                observation_manifest=Path(str(value["observation_manifest"])),
            ),
            role=str(value["role"]),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.cell.condition_id,
            "method": self.cell.method,
            "script": self.cell.script,
            "spacing": self.cell.spacing,
            "substrate": self.cell.substrate,
            "observation_manifest": self.cell.observation_manifest.as_posix(),
            "status": VALID,
            "role": self.role,
        }


def expected_full_m0_keys() -> set[tuple[str, str, str, str]]:
    unchanged = {
        (record.cell.method, record.cell.script, record.cell.spacing, M0_SUBSTRATE)
        for record in expected_condition_manifest()
        if record.status == VALID
    }
    replacements = {
        (method, M0_PRIME_SCRIPT, M0_PRIME_SPACING, M0_PRIME_SUBSTRATE)
        for method in ("bpe", "unigram", "unicode_codepoint", "surface_lattice")
    }
    return unchanged | replacements


def validate_full_m0_conditions(
    records: Iterable[FullM0ConditionRecord],
    *,
    m0_manifest: Path,
    m0_prime_manifest: Path,
) -> tuple[FullM0ConditionRecord, ...]:
    actual = tuple(records)
    keys = tuple(
        (record.cell.method, record.cell.script, record.cell.spacing, record.cell.substrate)
        for record in actual
    )
    if len(keys) != len(set(keys)):
        raise ValueError("full-M0 condition manifest contains duplicate cells")
    if set(keys) != expected_full_m0_keys():
        missing = sorted(expected_full_m0_keys() - set(keys))
        extra = sorted(set(keys) - expected_full_m0_keys())
        raise ValueError(f"full-M0 production matrix mismatch: missing={missing}, extra={extra}")
    if len(actual) != 22:
        raise ValueError(f"full-M0 production matrix must contain 22 cells, found {len(actual)}")
    for record in actual:
        expected_manifest = (
            m0_prime_manifest
            if record.cell.substrate == M0_PRIME_SUBSTRATE
            else m0_manifest
        )
        if record.cell.observation_manifest != expected_manifest:
            raise ValueError(
                f"observation manifest mismatch for {record.cell.condition_id}: "
                f"expected {expected_manifest}"
            )
    if sum(record.role == "unchanged_m0" for record in actual) != 18:
        raise ValueError("full-M0 must contain exactly 18 unchanged M0 production cells")
    if sum(record.role == "m0_prime_replacement" for record in actual) != 4:
        raise ValueError("full-M0 must contain exactly four M0-prime replacement cells")
    return actual


@dataclass(frozen=True, slots=True)
class FullM0MatrixSettings:
    freeze_id: str
    canonical_manifest: Path
    m0_representation_manifest: Path
    m0_prime: M0PrimeConsumerContract
    artifact_root: Path
    seed: int
    vocab_size: int
    condition_manifest: tuple[FullM0ConditionRecord, ...]
    downstream_lm: DownstreamLMSettings
    condition_manifest_version: str = FULL_M0_CONDITION_MANIFEST_VERSION
    full_m0_definition_version: str = FULL_M0_DEFINITION_VERSION

    def __post_init__(self) -> None:
        if self.freeze_id != FROZEN_M0_ID:
            raise ValueError(f"unexpected M0 freeze ID: {self.freeze_id}")
        if self.condition_manifest_version != FULL_M0_CONDITION_MANIFEST_VERSION:
            raise ValueError("unsupported full-M0 condition manifest version")
        if self.full_m0_definition_version != FULL_M0_DEFINITION_VERSION:
            raise ValueError("unsupported full-M0 definition version")
        if self.seed < 0 or self.vocab_size <= 4:
            raise ValueError("full-M0 seed/vocabulary controls are invalid")
        validate_full_m0_conditions(
            self.condition_manifest,
            m0_manifest=self.m0_representation_manifest,
            m0_prime_manifest=self.m0_prime.manifest,
        )

    @property
    def representation_manifest(self) -> Path:
        """Backward-compatible name for frozen M0 consumers."""
        return self.m0_representation_manifest

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FullM0MatrixSettings":
        if value.get("condition_manifest_version") != FULL_M0_CONDITION_MANIFEST_VERSION:
            raise ValueError("not a full-M0 baseline config")
        allowed = {
            "freeze_id",
            "canonical_manifest",
            "m0_representation_manifest",
            "artifact_root",
            "seed",
            "vocab_size",
            "condition_manifest_version",
            "full_m0_definition_version",
            "historical_condition_manifest",
            "matrix_accounting",
            "m0_prime",
            "downstream_lm",
            "m0",
            "m0_prime_manifest",
            "conditions",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown full-M0 config fields: {sorted(unknown)}")
        if value.get("historical_condition_manifest") != {
            "path": "configs/experiments/baselines/m0_matrix.yaml",
            "version": CONDITION_MANIFEST_VERSION,
        }:
            raise ValueError("full-M0 config must reference the unchanged historical contract")
        expected_accounting = {
            "historical_m0_cell_count": 22,
            "historical_retired_cell_count": 4,
            "unchanged_m0_production_cell_count": 18,
            "m0_prime_replacement_cell_count": 4,
            "full_m0_production_cell_count": 22,
            "retired_original_m0_condition_ids": [
                "bpe__iast__continuous",
                "unigram__iast__continuous",
                "unicode_codepoint__iast__continuous",
                "surface_lattice__iast__continuous",
            ],
        }
        if value.get("matrix_accounting") != expected_accounting:
            raise ValueError("full-M0 matrix accounting or retired-cell identity mismatch")
        prime = value.get("m0_prime")
        if not isinstance(prime, Mapping):
            raise ValueError("full-M0 config requires an m0_prime mapping")
        raw_conditions = value.get("conditions")
        if not isinstance(raw_conditions, list):
            raise ValueError("full-M0 config requires an explicit conditions list")
        contract = M0PrimeConsumerContract(
            manifest=Path(str(prime["manifest"])),
            payload_root=Path(str(prime["payload_root"])),
            manifest_sha256=str(prime["manifest_sha256"]),
            derivation_id=str(prime["derivation_id"]),
            manifest_schema=str(prime["manifest_schema"]),
            formal=True,
        )
        return cls(
            freeze_id=str(value["freeze_id"]),
            canonical_manifest=Path(str(value["canonical_manifest"])),
            m0_representation_manifest=Path(str(value["m0_representation_manifest"])),
            m0_prime=contract,
            artifact_root=Path(str(value["artifact_root"])),
            seed=int(value["seed"]),
            vocab_size=int(value["vocab_size"]),
            condition_manifest=tuple(
                FullM0ConditionRecord.from_mapping(item) for item in raw_conditions
            ),
            downstream_lm=DownstreamLMSettings.from_mapping(value["downstream_lm"]),
            condition_manifest_version=str(value["condition_manifest_version"]),
            full_m0_definition_version=str(value["full_m0_definition_version"]),
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "FullM0MatrixSettings":
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("full-M0 matrix config must be a YAML mapping")
        return cls.from_mapping(value)

    def condition(self, condition_id: str) -> FullM0ConditionRecord | ConditionRecord:
        for record in self.condition_manifest:
            if record.cell.condition_id == condition_id:
                return record
        for record in expected_condition_manifest():
            if record.status == RETIRED and record.cell.condition_id == condition_id:
                return record
        raise ValueError(f"unknown full-M0 baseline condition: {condition_id}")


@dataclass(frozen=True, slots=True)
class FullM0RunSpec:
    cell: FullM0Cell
    settings: FullM0MatrixSettings

    @property
    def artifact_dir(self) -> Path:
        return self.settings.artifact_root / self.cell.condition_id / f"seed_{self.settings.seed}"

    @property
    def observation_manifest(self) -> Path:
        return self.cell.observation_manifest

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.cell.condition_id,
            "method": self.cell.method,
            "script": self.cell.script,
            "spacing": self.cell.spacing,
            "substrate": self.cell.substrate,
            "condition_status": VALID,
            "condition_manifest_version": self.settings.condition_manifest_version,
            "full_m0_definition_version": self.settings.full_m0_definition_version,
            "seed": self.settings.seed,
            "corpus_freeze_id": self.settings.freeze_id,
            "canonical_manifest": self.settings.canonical_manifest.as_posix(),
            "observation_manifest": self.observation_manifest.as_posix(),
            "tokenizer": self.cell.tokenizer_config(vocab_size=self.settings.vocab_size),
            "artifact_location": self.artifact_dir.as_posix(),
            "required_provenance": list(FULL_M0_REQUIRED_PROVENANCE),
        }


def build_full_m0_run_specs(
    settings: FullM0MatrixSettings,
) -> tuple[FullM0RunSpec, ...]:
    records = validate_full_m0_conditions(
        settings.condition_manifest,
        m0_manifest=settings.m0_representation_manifest,
        m0_prime_manifest=settings.m0_prime.manifest,
    )
    specs = tuple(FullM0RunSpec(record.cell, settings) for record in records)
    if len({spec.artifact_dir for spec in specs}) != 22:
        raise ValueError("full-M0 cells do not have independent artifact directories")
    return specs


def build_full_m0_plan(settings: FullM0MatrixSettings) -> dict[str, Any]:
    specs = build_full_m0_run_specs(settings)
    retired = [
        record.as_dict()
        for record in expected_condition_manifest()
        if record.status == RETIRED
    ]
    return {
        "matrix": "full_m0_baselines",
        "condition_manifest_version": settings.condition_manifest_version,
        "full_m0_definition_version": settings.full_m0_definition_version,
        "freeze_id": settings.freeze_id,
        "historical_m0_cell_count": 22,
        "historical_retired_cell_count": 4,
        "unchanged_m0_production_cell_count": 18,
        "m0_prime_replacement_cell_count": 4,
        "full_m0_production_cell_count": len(specs),
        "retired_original_m0_conditions": retired,
        "common_downstream_lm": settings.downstream_lm.as_dict(),
        "cells": [spec.as_dict() for spec in specs],
    }


MatrixSettings = BaselineMatrixSettings | FullM0MatrixSettings


def load_matrix_settings(path: Path) -> MatrixSettings:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("baseline matrix config must be a YAML mapping")
    version = value.get("condition_manifest_version")
    if version == CONDITION_MANIFEST_VERSION:
        return BaselineMatrixSettings.from_mapping(value)
    if version == FULL_M0_CONDITION_MANIFEST_VERSION:
        return FullM0MatrixSettings.from_mapping(value)
    raise ValueError(f"unsupported baseline condition manifest version: {version}")


def build_specs(settings: MatrixSettings):
    if isinstance(settings, FullM0MatrixSettings):
        return build_full_m0_run_specs(settings)
    from sktlm.experiments.baselines.matrix import build_run_specs

    return build_run_specs(settings)


def build_plan(settings: MatrixSettings) -> dict[str, Any]:
    if isinstance(settings, FullM0MatrixSettings):
        return build_full_m0_plan(settings)
    from sktlm.experiments.baselines.matrix import build_plan as build_legacy_plan

    return build_legacy_plan(settings)


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate and print a baseline matrix plan")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/baselines/full_m0_matrix.yaml"),
    )
    parser.add_argument("--check-inputs", action="store_true")
    args = parser.parse_args(argv)
    settings = load_matrix_settings(args.config)
    plan = build_plan(settings)
    if args.check_inputs:
        from sktlm.experiments.baselines.frozen import (
            load_frozen_catalog,
            load_full_m0_catalog,
        )

        catalog = (
            load_full_m0_catalog(settings)
            if settings.condition_manifest_version == FULL_M0_CONDITION_MANIFEST_VERSION
            else load_frozen_catalog(settings)
        )
        plan["input_documents"] = catalog.document_count
        plan["input_representation_files"] = catalog.representation_file_count
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
