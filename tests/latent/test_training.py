from __future__ import annotations

import csv
import json
from pathlib import Path

from sktlm.latent.training import EXPECTED_FREEZE_ID, TrainingConfig, run_training


def test_bounded_training_writes_research_artifacts(tmp_path: Path) -> None:
    corpus_path = tmp_path / "surface.txt"
    corpus_path.write_text(
        "devo'pi devaḥ ca api ca\n"
        "rāmo'pi rāmaḥ ca api tat\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "representations.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "freeze_id",
                "relative_path",
                "script",
                "condition",
                "representation_path",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "freeze_id": EXPECTED_FREEZE_ID,
                "relative_path": "tiny.txt",
                "script": "iast",
                "condition": "surface_word",
                "representation_path": str(corpus_path),
            }
        )

    result = run_training(
        TrainingConfig(
            manifest=manifest,
            output_root=tmp_path / "artifacts",
            run_id="tiny",
            passes=2,
            analysis_top_k=4,
        ),
        repo_root=Path("."),
    )

    expected = {
        "config.json",
        "provenance.json",
        "checkpoint.json",
        "iteration_metrics.json",
        "learner.sqlite",
        "latent_lexicon.tsv",
        "analyses.jsonl",
        "boundary_posteriors.jsonl",
        "rule_usage.tsv",
        "summary.json",
        "inspection_report.md",
    }
    assert expected <= {path.name for path in result.run_dir.iterdir()}
    summary = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["segments"] == 2
    assert summary["complexity"]["active_lexical_types"] > 0
    analysis = json.loads(
        (result.run_dir / "analyses.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert analysis["top_analyses"]
    assert "residual_posterior" in analysis
