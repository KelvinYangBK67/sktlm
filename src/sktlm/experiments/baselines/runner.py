"""Independent, bounded-memory tokenizer runs over frozen M₀ representations."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import unicodedata
from collections import Counter
from importlib import metadata
from pathlib import Path
from typing import Any, Iterator

import yaml

from sktlm.corpus.dataset import file_sha256
from sktlm.evaluation.reporting import write_result_table
from sktlm.evaluation.tokenizer import SandhiFragmentConfig, evaluate_tokenizer
from sktlm.experiments.artifacts import (
    build_tokenizer_fingerprint,
    current_git_commit,
    payload_sha256,
)
from sktlm.experiments.baselines.frozen import FrozenRepresentationCatalog, load_frozen_catalog
from sktlm.experiments.baselines.matrix import (
    REQUIRED_PROVENANCE,
    RETIRED,
    VALID,
    BaselineMatrixSettings,
    BaselineRunSpec,
    RetiredConditionError,
    build_run_specs,
)
from sktlm.representations.canonical import RepresentedSegment
from sktlm.tokenizers.aksara_bpe import train_aksara_safe_bpe
from sktlm.tokenizers.base import Encoding, Tokenizer
from sktlm.tokenizers.factory import build_tokenizer
from sktlm.tokenizers.surface_lattice import (
    SurfaceLatticeTokenizer,
    train_surface_lattice,
)


class _SegmentTrace:
    """Accumulate ordered segment identity and volume without retaining text."""

    def __init__(self) -> None:
        self.segment_count = 0
        self.character_count = 0
        self.byte_count = 0
        self.split_counts: Counter[str] = Counter()
        self._identity_digest = hashlib.sha256()

    def observe(self, segment: RepresentedSegment) -> None:
        self.segment_count += 1
        self.character_count += len(segment.text)
        self.byte_count += len(segment.text.encode("utf-8"))
        self.split_counts[segment.split] += 1
        self._identity_digest.update(
            f"{segment.split}\t{segment.segment_id}\n".encode("utf-8")
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "segment_count": self.segment_count,
            "character_count": self.character_count,
            "byte_count": self.byte_count,
            "split_counts": dict(sorted(self.split_counts.items())),
            "segment_id_split_sha256": self._identity_digest.hexdigest(),
        }


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _software_versions() -> dict[str, str]:
    versions = {
        "python": platform.python_version(),
        "unicodedata": unicodedata.unidata_version,
    }
    for distribution in ("sktlm", "sentencepiece", "PyYAML", "regex", "torch"):
        try:
            versions[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            versions[distribution] = "unavailable"
    return versions


def _require_reproducible_git_state(repo_root: Path) -> str:
    commit = current_git_commit(repo_root)
    if commit.startswith("unavailable:"):
        raise RuntimeError(f"formal baseline run requires a Git commit, found {commit}")
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("could not verify the baseline Git worktree state") from exc
    if result.stdout.strip():
        raise RuntimeError("formal baseline run requires a clean Git worktree")
    return commit


def _declared_file_fingerprint(
    catalog: FrozenRepresentationCatalog,
    spec: BaselineRunSpec,
    splits: set[str],
) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    for representation in catalog.files_by_condition[(spec.cell.script, spec.cell.spacing)]:
        document = catalog.documents[representation.relative_path]
        if document.split not in splits:
            continue
        digest.update(
            f"{document.split}\t{representation.relative_path}\t{representation.sha256}\n".encode(
                "utf-8"
            )
        )
        file_count += 1
    return {
        "file_count": file_count,
        "declared_representation_set_sha256": digest.hexdigest(),
    }


def _select_spec(settings: BaselineMatrixSettings, condition_id: str) -> BaselineRunSpec:
    record = settings.condition(condition_id)
    if record.status == RETIRED:
        raise RetiredConditionError(
            f"refusing retired condition {condition_id}: {record.reason}; "
            f"decision_id={record.decision_id}"
        )
    for spec in build_run_specs(settings):
        if spec.cell.condition_id == condition_id:
            return spec
    raise RuntimeError(f"valid condition is missing from the production plan: {condition_id}")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fit_cell_tokenizer(
    spec: BaselineRunSpec,
    tokenizer_config: dict[str, Any],
    catalog: FrozenRepresentationCatalog,
    model_dir: Path,
    max_train_segments: int | None,
) -> Tokenizer:
    def training_texts() -> Iterator[str]:
        segments = catalog.iter_segments(
            spec.cell.script,
            spec.cell.spacing,
            splits={"train"},
            max_segments=max_train_segments,
        )
        return (segment.text for segment in segments)

    if spec.cell.method == "aksara_safe_bpe":
        return train_aksara_safe_bpe(
            training_texts,
            model_dir,
            vocab_size=int(tokenizer_config["vocab_size"]),
            max_piece_atoms=int(tokenizer_config["max_piece_atoms"]),
        )
    if spec.cell.method == "surface_lattice":
        return train_surface_lattice(
            training_texts,
            model_dir,
            vocab_size=int(tokenizer_config["vocab_size"]),
            max_piece_atoms=int(tokenizer_config["max_piece_atoms"]),
            unknown_log_score=float(tokenizer_config["unknown_log_score"]),
        )
    return build_tokenizer(tokenizer_config, training_texts(), model_dir=model_dir)


def run_supported_cell(
    settings: BaselineMatrixSettings,
    condition_id: str,
    *,
    repo_root: Path = Path("."),
    eval_split: str = "test",
    max_train_segments: int | None = None,
    max_eval_segments: int | None = None,
    prediction_examples: int = 5,
    expected_documents: int = 240,
    require_clean_git: bool = True,
) -> Path:
    """Fit and evaluate one of the 18 valid cells using frozen files directly."""
    if eval_split not in {"dev", "test"}:
        raise ValueError("eval_split must be 'dev' or 'test'")
    for name, value in (
        ("max_train_segments", max_train_segments),
        ("max_eval_segments", max_eval_segments),
        ("prediction_examples", prediction_examples),
    ):
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")
    if max_train_segments == 0 or max_eval_segments == 0:
        raise ValueError("segment limits must be positive when provided")

    spec = _select_spec(settings, condition_id)
    if not spec.cell.tokenizer_supported:
        raise NotImplementedError(
            f"{condition_id} is blocked on its pending method contract; no substitute is allowed"
        )

    git_commit = (
        _require_reproducible_git_state(repo_root)
        if require_clean_git
        else current_git_commit(repo_root)
    )

    catalog = load_frozen_catalog(
        settings,
        repo_root=repo_root,
        expected_documents=expected_documents,
    )
    tokenizer_config = spec.cell.tokenizer_config(vocab_size=settings.vocab_size)
    if tokenizer_config is None:  # guarded by tokenizer_supported; retain a defensive invariant.
        raise RuntimeError(f"missing tokenizer config for supported condition: {condition_id}")

    artifact_dir = _resolve_repo_path(spec.artifact_dir, repo_root)
    if artifact_dir.exists():
        raise FileExistsError(f"refusing to overwrite baseline artifact directory: {artifact_dir}")
    artifact_dir.mkdir(parents=True)

    tokenizer = _fit_cell_tokenizer(
        spec,
        tokenizer_config,
        catalog,
        artifact_dir / "tokenizer",
        max_train_segments,
    )
    train_trace = _SegmentTrace()
    for segment in catalog.iter_segments(
        spec.cell.script,
        spec.cell.spacing,
        splits={"train"},
        max_segments=max_train_segments,
    ):
        train_trace.observe(segment)
    if train_trace.segment_count == 0:
        raise ValueError("baseline cell requires non-empty frozen train segments")

    eval_trace = _SegmentTrace()
    predictions: list[dict[str, Any]] = []
    lattice_log_probability = 0.0
    lattice_arc_count = 0
    lattice_ambiguous_node_count = 0

    def encoded_evaluation() -> Iterator[tuple[str, Encoding]]:
        nonlocal lattice_log_probability
        nonlocal lattice_arc_count
        nonlocal lattice_ambiguous_node_count
        eval_segments = catalog.iter_segments(
            spec.cell.script,
            spec.cell.spacing,
            splits={eval_split},
            max_segments=max_eval_segments,
        )
        for segment in eval_segments:
            eval_trace.observe(segment)
            lattice_stats = None
            if isinstance(tokenizer, SurfaceLatticeTokenizer):
                encoding, lattice_stats = tokenizer.encode_with_lattice(segment.text)
                lattice_log_probability += lattice_stats.log_probability
                lattice_arc_count += lattice_stats.arc_count
                lattice_ambiguous_node_count += lattice_stats.ambiguous_node_count
            else:
                encoding = tokenizer.encode(segment.text)
            if len(predictions) < prediction_examples:
                prediction = {
                    "kind": "tokenization_preview",
                    "segment_id": segment.segment_id,
                    "text": segment.text,
                    "ids": list(encoding.ids),
                    "pieces": list(encoding.pieces),
                    "spans": [list(span) for span in encoding.spans],
                }
                if lattice_stats is not None:
                    prediction["lattice"] = {
                        "log_probability": lattice_stats.log_probability,
                        "arc_count": lattice_stats.arc_count,
                        "ambiguous_node_count": lattice_stats.ambiguous_node_count,
                    }
                predictions.append(prediction)
            yield segment.text, encoding

    diagnostics = evaluate_tokenizer(encoded_evaluation(), SandhiFragmentConfig())
    if eval_trace.segment_count == 0:
        raise ValueError(f"baseline cell requires non-empty frozen {eval_split} segments")

    method_metrics: dict[str, Any] = {}
    bits_per_character: float | None = None
    bits_per_byte: float | None = None
    if isinstance(tokenizer, SurfaceLatticeTokenizer):
        negative_log2 = -lattice_log_probability / math.log(2.0)
        bits_per_character = negative_log2 / eval_trace.character_count
        bits_per_byte = negative_log2 / eval_trace.byte_count
        method_metrics = {
            "lattice_log_probability": lattice_log_probability,
            "lattice_arc_count": lattice_arc_count,
            "lattice_ambiguous_node_count": lattice_ambiguous_node_count,
        }

    canonical_manifest = _resolve_repo_path(settings.canonical_manifest, repo_root)
    representation_manifest = _resolve_repo_path(settings.representation_manifest, repo_root)
    canonical_manifest_sha256 = file_sha256(canonical_manifest)
    representation_manifest_sha256 = file_sha256(representation_manifest)
    data_fingerprint: dict[str, Any] = {
        "corpus_freeze_id": settings.freeze_id,
        "canonical_manifest": settings.canonical_manifest.as_posix(),
        "canonical_manifest_sha256": canonical_manifest_sha256,
        "representation_manifest": settings.representation_manifest.as_posix(),
        "representation_manifest_sha256": representation_manifest_sha256,
        "script": spec.cell.script,
        "spacing": spec.cell.spacing,
        "train": {
            **train_trace.as_dict(),
            **_declared_file_fingerprint(catalog, spec, {"train"}),
        },
        "evaluation": {
            "split": eval_split,
            **eval_trace.as_dict(),
            **_declared_file_fingerprint(catalog, spec, {eval_split}),
        },
    }
    data_fingerprint["fingerprint_sha256"] = payload_sha256(data_fingerprint)
    tokenizer_fingerprint = build_tokenizer_fingerprint(
        tokenizer_config,
        tokenizer.fingerprint_payload(),
    )

    execution_config: dict[str, Any] = {
        "matrix": "formal_m0_baselines",
        "condition_manifest_version": settings.condition_manifest_version,
        "condition_id": condition_id,
        "condition_status": VALID,
        "retirement_reason": None,
        "method": spec.cell.method,
        "script": spec.cell.script,
        "spacing": spec.cell.spacing,
        "seed": settings.seed,
        "corpus_freeze_id": settings.freeze_id,
        "canonical_manifest": settings.canonical_manifest.as_posix(),
        "representation_manifest": settings.representation_manifest.as_posix(),
        "tokenizer": tokenizer_config,
        "evaluation": {
            "split": eval_split,
            "prediction_examples": prediction_examples,
        },
        "limits": {
            "max_train_segments": max_train_segments,
            "max_eval_segments": max_eval_segments,
        },
    }
    provenance: dict[str, Any] = {
        "method": spec.cell.method,
        "script": spec.cell.script,
        "spacing": spec.cell.spacing,
        "condition_status": VALID,
        "retirement_reason": None,
        "condition_manifest_version": settings.condition_manifest_version,
        "config": execution_config,
        "seed": settings.seed,
        "code_commit": git_commit,
        "code_worktree": "clean" if require_clean_git else "check_disabled",
        "corpus_freeze_id": settings.freeze_id,
        "canonical_manifest_sha256": canonical_manifest_sha256,
        "representation_manifest_sha256": representation_manifest_sha256,
        "software_versions": _software_versions(),
        "artifact_location": artifact_dir.as_posix(),
    }
    missing_provenance = set(REQUIRED_PROVENANCE) - set(provenance)
    if missing_provenance:
        raise RuntimeError(f"incomplete baseline provenance: {sorted(missing_provenance)}")

    metrics: dict[str, Any] = {
        "run_id": f"{condition_id}__seed_{settings.seed}",
        "condition_id": condition_id,
        "method": spec.cell.method,
        "script": spec.cell.script,
        "spacing": spec.cell.spacing,
        "condition_status": VALID,
        "retirement_reason": None,
        "tokenizer": tokenizer.name,
        "vocab_size": tokenizer.vocab_size,
        "seed": settings.seed,
        "train_segments": train_trace.segment_count,
        "evaluation_split": eval_split,
        "evaluation_segments": eval_trace.segment_count,
        "bits_per_character": bits_per_character,
        "bits_per_byte": bits_per_byte,
        "phase": "tokenizer_diagnostics",
        **diagnostics,
        **method_metrics,
    }
    logs = [
        f"condition_id={condition_id}",
        "input=frozen representation manifest paths",
        f"freeze_id={settings.freeze_id}",
        f"tokenizer={tokenizer.name}",
        f"train_segments={train_trace.segment_count}",
        f"evaluation_split={eval_split} evaluation_segments={eval_trace.segment_count}",
    ]
    if isinstance(tokenizer, SurfaceLatticeTokenizer):
        logs.append(f"lattice_log_probability={lattice_log_probability}")

    (artifact_dir / "config.yaml").write_text(
        yaml.safe_dump(execution_config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _write_json(artifact_dir / "metrics.json", metrics)
    _write_json(artifact_dir / "provenance.json", provenance)
    _write_json(artifact_dir / "data_fingerprint.json", data_fingerprint)
    _write_json(artifact_dir / "tokenizer_fingerprint.json", tokenizer_fingerprint)
    (artifact_dir / "git_commit.txt").write_text(git_commit + "\n", encoding="utf-8")
    with (artifact_dir / "predictions.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction, ensure_ascii=False, sort_keys=True) + "\n")
    (artifact_dir / "logs.txt").write_text("\n".join(logs) + "\n", encoding="utf-8")
    write_result_table([metrics], artifact_dir / "result.csv")
    return artifact_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one supported formal M₀ baseline tokenizer condition"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/baselines/m0_matrix.yaml"),
    )
    parser.add_argument("--condition", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--eval-split", choices=("dev", "test"), default="test")
    parser.add_argument("--max-train-segments", type=int)
    parser.add_argument("--max-eval-segments", type=int)
    parser.add_argument("--prediction-examples", type=int, default=5)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config_path = _resolve_repo_path(args.config, args.repo_root)
    settings = BaselineMatrixSettings.from_yaml(config_path)
    artifact_dir = run_supported_cell(
        settings,
        args.condition,
        repo_root=args.repo_root,
        eval_split=args.eval_split,
        max_train_segments=args.max_train_segments,
        max_eval_segments=args.max_eval_segments,
        prediction_examples=args.prediction_examples,
    )
    print(f"baseline artifacts: {artifact_dir}")


if __name__ == "__main__":
    main()
