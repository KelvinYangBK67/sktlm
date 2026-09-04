from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from sktlm.analysis.association_specialization import analyze_manifest
from sktlm.analysis.six_representation_gate import GateValidationError

EXPORTER_COMMIT = "a" * 40
EXPORTER_ID = "sktlm.analysis.s1m1_compact:export_sqlite_state"
NAMESPACE = "fixture-phoneme-sequence/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gzip_table(
    path: Path, fields: tuple[str, ...], rows: list[tuple[object, ...]]
) -> None:
    with gzip.open(
        path, "wt", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(
            handle, delimiter="\t", lineterminator="\n"
        )
        writer.writerow(fields)
        writer.writerows(rows)


def _write_compact(
    root: Path,
    cell_id: str,
    scorer: list[tuple[str, float, float]],
    surface: list[tuple[str, str, float]],
    context: list[tuple[str, str, float]],
) -> None:
    root.mkdir()
    tables = {
        "final_scorer": (
            "final_scorer.tsv.gz",
            ("form_key", "training_expected_count", "probability"),
            scorer,
            "training_expected_count",
        ),
        "surface_usage": (
            "surface_usage.tsv.gz",
            ("form_key", "surface", "expected_mass"),
            surface,
            "expected_mass",
        ),
        "context_usage": (
            "context_usage.tsv.gz",
            ("form_key", "context", "expected_mass"),
            context,
            "expected_mass",
        ),
    }
    readback: dict[str, dict[str, float | int]] = {}
    artifacts = []
    for name, (filename, fields, rows, numeric_field) in tables.items():
        path = root / filename
        _gzip_table(path, fields, rows)
        readback[name] = {
            "rows": len(rows),
            f"sum_{numeric_field}": sum(
                float(row[fields.index(numeric_field)]) for row in rows
            ),
        }
        artifacts.append(
            {
                "name": filename,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    probability_sum = sum(row[2] for row in scorer)
    manifest = {
        "schema_version": "sktlm-s1m1-sqlite-state/v2",
        "cell_id": cell_id,
        "compact_artifacts": sorted(
            artifacts, key=lambda item: item["name"]
        ),
        "consistency": {"fixture_readback_valid": True},
        "exporter_provenance": {
            "git_commit_sha": EXPORTER_COMMIT,
            "implementation_id": EXPORTER_ID,
        },
        "readback": readback,
        "statistics": {
            "database": {
                "final_scorer": {
                    "database_probability_sum": probability_sum
                }
            }
        },
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksums = {
        item["name"]: item["sha256"] for item in artifacts
    }
    checksums["manifest.json"] = _sha256(manifest_path)
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{digest}  {name}\n"
            for name, digest in sorted(checksums.items())
        ),
        encoding="utf-8",
    )


def _analysis_manifest(
    path: Path,
    cells: list[tuple[str, Path, str]],
    *,
    alignment_status: str = "SUPPORTED",
) -> None:
    comparison = {
        "comparison_id": "a_to_b",
        "cell_a": cells[0][0],
        "cell_b": cells[1][0],
        "strong_count_increase_ratio": 2.0,
        "form_alignment": (
            {"status": "SUPPORTED", "namespace": NAMESPACE}
            if alignment_status == "SUPPORTED"
            else {
                "status": "UNSUPPORTED",
                "reason": "fixture namespaces are intentionally incomparable",
            }
        ),
    }
    diagnostics = (
        [
            {
                "diagnostic_id": "fixture_diagnostic",
                "comparison_id": "a_to_b",
                "target_cell": cells[1][0],
                "reference_cell": cells[0][0],
                "min_phoneme_length": 2,
                "max_training_expected_count": 5.0,
                "min_context_top1_share": 0.8,
                "max_context_effective_support": 2.0,
                "min_context_top1_delta": 0.3,
                "limit_per_category": 5,
            }
        ]
        if alignment_status == "SUPPORTED"
        else []
    )
    value = {
        "schema_version": "sktlm-association-specialization-input/v1",
        "analysis_id": "fixture",
        "input_contract": {
            "compact_schema_version": "sktlm-s1m1-sqlite-state/v2",
            "exporter_implementation_id": EXPORTER_ID,
            "allowed_exporter_git_commits": [EXPORTER_COMMIT],
        },
        "cells": [
            {
                "cell_id": cell_id,
                "compact_dir": str(root),
                "form_key_namespace": namespace,
                "checksum_status": "FIXTURE_VERIFIED",
            }
            for cell_id, root, namespace in cells
        ],
        "comparisons": [comparison],
        "diagnostics": diagnostics,
        "parameters": {
            "association_top_k": 2,
            "bins": {
                "phoneme_length": {
                    "upper_bounds": [1, 2],
                    "labels": ["1", "2", "3+"],
                },
                "training_expected_count": {
                    "upper_bounds": [1.0, 3.0],
                    "labels": ["<=1", "(1,3]", ">3"],
                },
            },
        },
    }
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write_compact(
        left,
        "left",
        [
            ("C_G.V_A", 2.0, 0.2),
            ("C_K.V_A", 3.0, 0.3),
            ("V_A", 4.0, 0.5),
        ],
        [
            ("C_G.V_A", "ga", 2.0),
            ("C_K.V_A", "ka", 1.0),
            ("C_K.V_A", "kaa", 1.0),
            ("V_A", "a", 4.0),
        ],
        [
            ("C_G.V_A", "g", 2.0),
            ("C_K.V_A", "x", 1.0),
            ("C_K.V_A", "y", 1.0),
            ("V_A", "v", 4.0),
        ],
    )
    _write_compact(
        right,
        "right",
        [
            ("C_K.V_A", 3.0, 0.3),
            ("C_T.V_A", 1.0, 0.3),
            ("V_A", 2.0, 0.4),
        ],
        [
            ("C_K.V_A", "ka", 9.0),
            ("C_K.V_A", "kaa", 1.0),
            ("C_T.V_A", "ta", 1.0),
            ("V_A", "a", 1.0),
            ("V_A", "aa", 1.0),
        ],
        [
            ("C_K.V_A", "x", 9.0),
            ("C_K.V_A", "y", 1.0),
            ("C_T.V_A", "z", 1.0),
            ("V_A", "v", 1.0),
            ("V_A", "w", 1.0),
        ],
    )
    manifest = tmp_path / "analysis.json"
    _analysis_manifest(
        manifest,
        [("left", left, NAMESPACE), ("right", right, NAMESPACE)],
    )
    return left, right, manifest


def _read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(
        path, "rt", encoding="utf-8", newline=""
    ) as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_known_metrics_matched_membership_and_diagnostics(
    tmp_path: Path,
) -> None:
    _left, _right, manifest = _fixture(tmp_path)
    output = tmp_path / "output"
    analyze_manifest(manifest, output)

    rows = _read_gzip(output / "per_form_metrics.tsv.gz")
    by_key = {(row["cell_id"], row["form_key"]): row for row in rows}
    uniform = by_key[("left", "C_K.V_A")]
    assert float(uniform["context_top1_share"]) == pytest.approx(0.5)
    assert float(uniform["context_entropy_nats"]) == pytest.approx(
        math.log(2.0)
    )
    assert float(uniform["context_normalized_entropy"]) == pytest.approx(1.0)
    assert float(uniform["context_effective_support_shannon"]) == pytest.approx(
        2.0
    )
    assert float(uniform["context_herfindahl"]) == pytest.approx(0.5)
    assert float(uniform["context_effective_support_simpson"]) == pytest.approx(
        2.0
    )
    concentrated = by_key[("right", "C_K.V_A")]
    assert float(concentrated["context_top1_share"]) == pytest.approx(0.9)
    assert float(concentrated["surface_top1_share"]) == pytest.approx(0.9)
    single = by_key[("left", "V_A")]
    assert float(single["context_entropy_nats"]) == pytest.approx(0.0)
    assert float(single["context_effective_support_shannon"]) == pytest.approx(
        1.0
    )

    comparison = _read_gzip(output / "comparison.tsv.gz")
    membership = {
        row["form_key"]: row["membership"] for row in comparison
    }
    assert membership == {
        "C_G.V_A": "cell_a_only",
        "C_K.V_A": "shared",
        "C_T.V_A": "cell_b_only",
        "V_A": "shared",
    }
    diagnostics = list(
        csv.DictReader(
            (output / "diagnostic_examples.tsv").open(
                encoding="utf-8", newline=""
            ),
            delimiter="\t",
        )
    )
    assert [
        (row["category"], row["form_key"]) for row in diagnostics
    ] == [
        ("shared_more_specialized", "C_K.V_A"),
        ("target_only_specialized", "C_T.V_A"),
    ]
    summary = json.loads(
        (output / "cell_summary.json").read_text(encoding="utf-8")
    )
    right_top1 = summary["cells"][1]["context"]["metrics"]["top1_share"]
    assert right_top1["type_mean"] != pytest.approx(
        right_top1["training_expected_count_weighted_mean"]
    )
    assert right_top1["type_mean"] != pytest.approx(
        right_top1["association_expected_mass_weighted_mean"]
    )
    matched = summary["comparisons"][0]
    assert matched["membership"]["shared"]["forms"] == 2
    assert (
        matched["matched_deltas"]["context_top1_share"][
            "type_mean_delta"
        ]
        == pytest.approx(-0.05)
    )
    assert (output / "SHA256SUMS").is_file()
    assert {path.name for path in output.iterdir()} == {
        "SHA256SUMS",
        "cell_summary.json",
        "comparison.tsv.gz",
        "comparison_strata.tsv",
        "comparison_summary.tsv",
        "count_bins.tsv",
        "diagnostic_examples.tsv",
        "joint_bins.tsv",
        "length_bins.tsv",
        "manifest.json",
        "per_form_metrics.tsv.gz",
        "relationship_summary.tsv",
    }


def test_unsupported_namespace_is_explicit_scientific_na(
    tmp_path: Path,
) -> None:
    left, right, _manifest = _fixture(tmp_path)
    manifest = tmp_path / "unsupported.json"
    _analysis_manifest(
        manifest,
        [("left", left, "left/v1"), ("right", right, "right/v1")],
        alignment_status="UNSUPPORTED",
    )
    output = tmp_path / "unsupported-output"
    analyze_manifest(manifest, output)
    summary = json.loads(
        (output / "cell_summary.json").read_text(encoding="utf-8")
    )
    assert (
        summary["comparisons"][0]["form_alignment"]["status"]
        == "UNSUPPORTED"
    )
    rows = list(
        csv.DictReader(
            (output / "comparison_summary.tsv").open(encoding="utf-8"),
            delimiter="\t",
        )
    )
    assert rows[0]["record_type"] == "scientific_na"


@pytest.mark.parametrize(
    "context, message",
    [
        (
            [("V_A", "z", 1.0), ("C_K.V_A", "x", 1.0)],
            "not sorted",
        ),
        (
            [("V_A", "x", 1.0), ("V_A", "x", 1.0)],
            "duplicate pair",
        ),
        ([("V_A", "x", -1.0)], "nonnegative"),
    ],
)
def test_malformed_association_fails_without_publication(
    tmp_path: Path,
    context: list[tuple[str, str, float]],
    message: str,
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    for root, cell_id, rows in (
        (left, "left", context),
        (right, "right", [("V_A", "x", 1.0)]),
    ):
        _write_compact(
            root,
            cell_id,
            [("V_A", 1.0, 1.0)],
            [("V_A", "a", 1.0)],
            rows,
        )
    manifest = tmp_path / "analysis.json"
    _analysis_manifest(
        manifest,
        [("left", left, NAMESPACE), ("right", right, NAMESPACE)],
    )
    output = tmp_path / "output"
    with pytest.raises(GateValidationError, match=message):
        analyze_manifest(manifest, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".output.*"))
