"""Independent TransLIST prediction adapter and comparable evaluation metrics."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sktlm.experiments.artifacts import current_git_commit, payload_sha256
from sktlm.experiments.environment import write_environment
from sktlm.representations.validity import require_valid_experimental_representation


TRANSLIST_SCHEMA_VERSION = "sktlm-translist-adapter-v1"


@dataclass(frozen=True, slots=True)
class TranslistIdentity:
    document_id: str
    segment_id: str
    split: str
    script: str
    spacing: str
    input_text: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "TranslistIdentity":
        identity = cls(
            document_id=str(value["document_id"]),
            segment_id=str(value["segment_id"]),
            split=str(value["split"]),
            script=str(value["script"]),
            spacing=str(value["spacing"]),
            input_text=str(value["input_text"]),
        )
        if identity.split not in {"train", "dev", "test"}:
            raise ValueError(f"invalid TransLIST split: {identity.split}")
        require_valid_experimental_representation(
            identity.script,
            identity.spacing,
            context="TransLIST adapter",
        )
        return identity

    def as_dict(self) -> dict[str, str]:
        return {
            "document_id": self.document_id,
            "segment_id": self.segment_id,
            "split": self.split,
            "script": self.script,
            "spacing": self.spacing,
            "input_text": self.input_text,
        }


@dataclass(frozen=True, slots=True)
class TranslistOutput:
    identity: TranslistIdentity
    surface_segments: tuple[str, ...]
    desandhi_segments: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "TranslistOutput":
        if value.get("schema_version") != TRANSLIST_SCHEMA_VERSION:
            raise ValueError("unsupported TransLIST adapter schema")
        surface = value.get("surface_segments")
        desandhi = value.get("desandhi_segments")
        if (
            not isinstance(surface, list)
            or not surface
            or not all(isinstance(item, str) and item for item in surface)
            or not isinstance(desandhi, list)
            or not desandhi
            or not all(isinstance(item, str) and item for item in desandhi)
        ):
            raise ValueError("TransLIST outputs require non-empty string segment lists")
        identity = TranslistIdentity.from_mapping(value)
        if "".join(surface) != identity.input_text:
            raise ValueError(
                f"TransLIST surface segments do not reconstruct {identity.segment_id}"
            )
        return cls(identity, tuple(surface), tuple(desandhi))


def _load_jsonl(path: Path) -> tuple[TranslistOutput, ...]:
    outputs: list[TranslistOutput] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid TransLIST JSONL at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"TransLIST JSONL row must be an object: {path}:{line_number}")
        output = TranslistOutput.from_mapping(value)
        if output.identity.segment_id in seen:
            raise ValueError(f"duplicate TransLIST segment_id: {output.identity.segment_id}")
        seen.add(output.identity.segment_id)
        outputs.append(output)
    if not outputs:
        raise ValueError(f"TransLIST JSONL is empty: {path}")
    return tuple(outputs)


def _boundaries(segments: tuple[str, ...]) -> set[int]:
    offsets: set[int] = set()
    cursor = 0
    for segment in segments[:-1]:
        cursor += len(segment)
        offsets.add(cursor)
    return offsets


def _edit_distance(reference: tuple[str, ...], prediction: tuple[str, ...]) -> int:
    previous = list(range(len(prediction) + 1))
    for row, expected in enumerate(reference, 1):
        current = [row]
        for column, actual in enumerate(prediction, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + int(expected != actual),
                )
            )
        previous = current
    return previous[-1]


def evaluate_translist_outputs(
    references: tuple[TranslistOutput, ...],
    predictions: tuple[TranslistOutput, ...],
) -> dict[str, Any]:
    reference_by_id = {item.identity.segment_id: item for item in references}
    prediction_by_id = {item.identity.segment_id: item for item in predictions}
    if set(reference_by_id) != set(prediction_by_id):
        missing = sorted(set(reference_by_id) - set(prediction_by_id))
        extra = sorted(set(prediction_by_id) - set(reference_by_id))
        raise ValueError(f"TransLIST prediction membership mismatch: missing={missing}, extra={extra}")
    true_positive = 0
    predicted_total = 0
    reference_total = 0
    segmentation_exact = 0
    desandhi_exact = 0
    desandhi_edits = 0
    desandhi_reference_tokens = 0
    split_counts: Counter[str] = Counter()
    ordered_identity: list[dict[str, str]] = []
    for reference in references:
        prediction = prediction_by_id[reference.identity.segment_id]
        if prediction.identity != reference.identity:
            raise ValueError(
                f"TransLIST identity mismatch: {reference.identity.segment_id}"
            )
        reference_boundaries = _boundaries(reference.surface_segments)
        prediction_boundaries = _boundaries(prediction.surface_segments)
        true_positive += len(reference_boundaries & prediction_boundaries)
        predicted_total += len(prediction_boundaries)
        reference_total += len(reference_boundaries)
        segmentation_exact += int(reference.surface_segments == prediction.surface_segments)
        desandhi_exact += int(reference.desandhi_segments == prediction.desandhi_segments)
        desandhi_edits += _edit_distance(
            reference.desandhi_segments, prediction.desandhi_segments
        )
        desandhi_reference_tokens += len(reference.desandhi_segments)
        split_counts[reference.identity.split] += 1
        ordered_identity.append(reference.identity.as_dict())
    precision = true_positive / predicted_total if predicted_total else 1.0
    recall = true_positive / reference_total if reference_total else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    count = len(references)
    return {
        "adapter": "translist",
        "adapter_schema_version": TRANSLIST_SCHEMA_VERSION,
        "matrix_condition": False,
        "example_count": count,
        "split_counts": dict(sorted(split_counts.items())),
        "split_identity_sha256": payload_sha256(ordered_identity),
        "segmentation_boundary_precision": precision,
        "segmentation_boundary_recall": recall,
        "segmentation_boundary_f1": f1,
        "segmentation_exact_match_rate": segmentation_exact / count,
        "desandhi_exact_match_rate": desandhi_exact / count,
        "desandhi_token_error_rate": (
            desandhi_edits / desandhi_reference_tokens
            if desandhi_reference_tokens
            else 0.0
        ),
    }


def run_translist_adapter(
    reference_path: Path,
    prediction_path: Path,
    artifact_root: Path,
    *,
    repo_root: Path = Path("."),
) -> Path:
    """Evaluate external predictions without training or entering the baseline matrix."""
    references = _load_jsonl(reference_path)
    predictions = _load_jsonl(prediction_path)
    metrics = evaluate_translist_outputs(references, predictions)
    source_fingerprint = payload_sha256(
        [
            {
                **item.identity.as_dict(),
                "surface_segments": item.surface_segments,
                "desandhi_segments": item.desandhi_segments,
            }
            for item in references
        ]
    )
    prediction_fingerprint = payload_sha256(
        [
            {
                **item.identity.as_dict(),
                "surface_segments": item.surface_segments,
                "desandhi_segments": item.desandhi_segments,
            }
            for item in predictions
        ]
    )
    run_id = f"translist_{payload_sha256([source_fingerprint, prediction_fingerprint])[:12]}"
    artifact_dir = artifact_root / run_id
    if artifact_dir.exists():
        raise FileExistsError(f"refusing to overwrite TransLIST artifact: {artifact_dir}")
    artifact_dir.mkdir(parents=True)
    environment = write_environment(artifact_dir)
    config = {
        "adapter_schema_version": TRANSLIST_SCHEMA_VERSION,
        "reference_path": reference_path.as_posix(),
        "prediction_path": prediction_path.as_posix(),
        "artifact_layout": "artifacts/references/translist/<run_id>",
        "matrix_condition": False,
    }
    provenance = {
        "adapter": "translist",
        "adapter_schema_version": TRANSLIST_SCHEMA_VERSION,
        "code_commit": current_git_commit(repo_root),
        "source_fingerprint_sha256": source_fingerprint,
        "prediction_fingerprint_sha256": prediction_fingerprint,
        "split_identity_sha256": metrics["split_identity_sha256"],
        "environment_fingerprint_sha256": environment[
            "environment_fingerprint_sha256"
        ],
        "artifact_location": artifact_dir.as_posix(),
        "matrix_condition": False,
    }
    (artifact_dir / "config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return artifact_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate TransLIST adapter JSONL")
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("artifacts/references/translist"),
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    artifact_dir = run_translist_adapter(
        args.references,
        args.predictions,
        args.artifact_root,
        repo_root=args.repo_root,
    )
    print(f"TransLIST evaluation artifacts: {artifact_dir}")


if __name__ == "__main__":
    main()
