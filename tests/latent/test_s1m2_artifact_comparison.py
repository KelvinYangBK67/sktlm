import json
import sqlite3
import subprocess
import sys
from pathlib import Path


COMPARATOR = Path("scripts/analysis/compare_s1m2_artifacts.py")


def _write_fixture(
    root: Path,
    *,
    delta: float,
    traversal_count: int,
    reverse_tsv_rows: bool = False,
) -> None:
    root.mkdir()
    (root / "iteration_metrics.json").write_text(
        json.dumps({"value": 1.0 + delta}),
        encoding="utf-8",
    )
    tsv_rows = [f"V_I\t{1.0 + delta}", "V_AA\t2.0"]
    if reverse_tsv_rows:
        tsv_rows.reverse()
    for name in ("piece_inventory.tsv", "lexical_diagnostics.tsv"):
        (root / name).write_text(
            "identity\tvalue\n" + "\n".join(tsv_rows) + "\n",
            encoding="utf-8",
        )
    (root / "analyses.jsonl").write_text(
        json.dumps({"identity": "a", "mass": 1.0 + delta}) + "\n",
        encoding="utf-8",
    )
    (root / "boundary_posteriors.jsonl").write_text(
        json.dumps({"identity": "b", "mass": 0.5 + delta}) + "\n",
        encoding="utf-8",
    )
    (root / "rule_usage.tsv").write_text(
        f"identity\tvalue\nEXT_1\t{0.25 + delta}\n",
        encoding="utf-8",
    )
    (root / "summary.json").write_text(
        json.dumps(
            {
                "scientific_mass": 1.0 + delta,
                "lazy_span_traversals": traversal_count,
            }
        ),
        encoding="utf-8",
    )


def _run(reference: Path, candidate: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(COMPARATOR), str(reference), str(candidate)],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_training_state(
    root: Path,
    *,
    delta: float,
    piece_score_calls: int,
) -> None:
    root.mkdir()
    (root / "checkpoint.json").write_text(
        json.dumps(
            {
                "completed_passes": 1,
                "active_pass": None,
                "inspection_complete": False,
            }
        ),
        encoding="utf-8",
    )
    (root / "iteration_metrics.json").write_text(
        json.dumps(
            [
                {
                    "log_partition": 3.0 + delta,
                    "piece_score_calls": piece_score_calls,
                }
            ]
        ),
        encoding="utf-8",
    )
    with sqlite3.connect(root / "learner.sqlite") as connection:
        connection.execute(
            "CREATE TABLE lexicon("
            "form_key TEXT PRIMARY KEY, expected_count REAL NOT NULL, "
            "probability REAL NOT NULL)"
        )
        connection.execute(
            "INSERT INTO lexicon VALUES (?, ?, ?)",
            ("V_A", 4.0 + delta, 1.0),
        )
        connection.execute(
            "CREATE TABLE piece_lexicon("
            "form_key TEXT PRIMARY KEY, raw_expected_count REAL NOT NULL, "
            "max_host_expected_usage REAL NOT NULL, reusable_count REAL NOT NULL)"
        )
        connection.execute(
            "INSERT INTO piece_lexicon VALUES (?, ?, ?, ?)",
            ("V_A", 2.0 + delta, 1.0, 1.0 + delta),
        )


def test_streaming_comparator_preserves_tolerance_and_contract(tmp_path: Path) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    _write_fixture(reference, delta=0.0, traversal_count=10)
    _write_fixture(
        candidate,
        delta=1e-13,
        traversal_count=2,
        reverse_tsv_rows=True,
    )

    result = _run(reference, candidate)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["numeric_values"] > 0

    analyses = candidate / "analyses.jsonl"
    analyses.write_text(
        json.dumps({"identity": "changed", "mass": 1.0}) + "\n",
        encoding="utf-8",
    )
    mismatch = _run(reference, candidate)
    assert mismatch.returncode != 0
    assert "identity" in mismatch.stderr

def test_streaming_comparator_preserves_matching_nan(tmp_path: Path) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    _write_fixture(reference, delta=0.0, traversal_count=10)
    _write_fixture(candidate, delta=0.0, traversal_count=2)

    for name in ("piece_inventory.tsv", "lexical_diagnostics.tsv"):
        (reference / name).write_text(
            "identity\tvalue\n"
            "V_I\tnan\n"
            "V_AA\t2.0\n",
            encoding="utf-8",
        )
        (candidate / name).write_text(
            "identity\tvalue\n"
            "V_AA\t2.0\n"
            "V_I\tnan\n",
            encoding="utf-8",
        )

    result = _run(reference, candidate)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"

    (candidate / "piece_inventory.tsv").write_text(
        "identity\tvalue\n"
        "V_AA\t2.0\n"
        "V_I\t0.0\n",
        encoding="utf-8",
    )

    mismatch = _run(reference, candidate)

    assert mismatch.returncode != 0
    assert "nan" in mismatch.stderr.lower()


def test_streaming_comparator_keeps_nonfinite_looking_text_exact(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    _write_fixture(reference, delta=0.0, traversal_count=10)
    _write_fixture(candidate, delta=0.0, traversal_count=2)

    for root in (reference, candidate):
        for name in ("piece_inventory.tsv", "lexical_diagnostics.tsv"):
            (root / name).write_text(
                "identity\tpiece\tvalue\n"
                "C_N.V_A.C_N\tnan\t1.0\n",
                encoding="utf-8",
            )

    matching = _run(reference, candidate)
    assert matching.returncode == 0

    (candidate / "piece_inventory.tsv").write_text(
        "identity\tpiece\tvalue\n"
        "C_N.V_A.C_N\tNaN\t1.0\n",
        encoding="utf-8",
    )
    mismatch = _run(reference, candidate)

    assert mismatch.returncode != 0
    assert "'nan' != 'NaN'" in mismatch.stderr


def test_training_state_comparator_checks_pass_boundary_science(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    _write_training_state(reference, delta=0.0, piece_score_calls=50)
    _write_training_state(candidate, delta=1e-13, piece_score_calls=0)

    result = subprocess.run(
        [
            sys.executable,
            str(COMPARATOR),
            str(reference),
            str(candidate),
            "--training-state-only",
            "--expected-completed-passes",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["completed_passes"] == 1
    assert payload["lexicon_rows"] == 1
    assert payload["piece_lexicon_rows"] == 1
