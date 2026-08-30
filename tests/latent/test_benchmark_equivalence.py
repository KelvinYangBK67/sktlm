from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from sktlm.latent.equivalence import compare_runs
from sktlm.latent.training import (
    EXPECTED_FREEZE_ID,
    TrainingConfig,
    load_documents,
    run_training,
)


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    manifest = tmp_path / "representations.csv"
    document_list = tmp_path / "documents.txt"
    rows = []
    for name, text in (
        ("a.txt", "devo'pi devaḥ ca\n"),
        ("b.txt", "rāmo'pi rāmaḥ ca\n"),
    ):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        rows.append(
            {
                "freeze_id": EXPECTED_FREEZE_ID,
                "relative_path": name,
                "script": "iast",
                "condition": "surface_word",
                "representation_path": str(path),
            }
        )
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=tuple(rows[0]),
        )
        writer.writeheader()
        writer.writerows(rows)
    document_list.write_text("# fixed subset\nb.txt\n", encoding="utf-8")
    return manifest, document_list


def test_document_list_is_ordered_and_exact(tmp_path: Path) -> None:
    manifest, document_list = _fixture(tmp_path)
    documents = load_documents(
        manifest,
        repo_root=Path("."),
        max_documents=None,
        document_list=document_list,
    )
    assert [document.relative_path for document in documents] == ["b.txt"]


def test_equivalence_compares_candidate_and_posterior_artifacts(
    tmp_path: Path,
) -> None:
    manifest, document_list = _fixture(tmp_path)

    def run(run_id: str) -> Path:
        return run_training(
            TrainingConfig(
                manifest=manifest,
                document_list=document_list,
                output_root=tmp_path / "runs",
                run_id=run_id,
                passes=1,
                equivalence_diagnostics=True,
            ),
            repo_root=Path("."),
        ).run_dir

    reference = run("reference")
    candidate = run("candidate")
    result = compare_runs(reference, candidate)
    assert result["equivalent"]

    changed = tmp_path / "changed"
    shutil.copytree(candidate, changed)
    summary_path = changed / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["identity_mass_total"] += 0.1
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    result = compare_runs(reference, changed)
    assert not result["equivalent"]
    assert any("identity_mass_total" in item for item in result["mismatches"])
