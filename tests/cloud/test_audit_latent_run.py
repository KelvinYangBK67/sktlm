from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _load_audit_module() -> ModuleType:
    path = Path("scripts/cloud/audit_latent_run.py")
    spec = importlib.util.spec_from_file_location("audit_latent_run", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = _load_audit_module()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_fixture(
    tmp_path: Path,
    *,
    script: str = "iast",
    condition: str = "surface_word",
    scoped: bool = False,
    benchmark: bool = False,
) -> tuple[Path, dict[str, object], dict[str, object], dict[str, object]]:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    history = [
        {"pass": index, "overflowed_tokens": 0}
        for index in range(1, 4)
    ]
    config: dict[str, object] = {
        "passes": 3,
        "workers": 8,
        "script": script,
        "condition": condition,
        "document_list": "smoke.txt" if scoped else None,
        "max_documents": None,
        "max_lines_per_document": None,
        **audit.EXPECTED_HYPERPARAMETERS,
    }
    checkpoint: dict[str, object] = {
        "completed_passes": 3,
        "inspection_complete": True,
        "history": history,
    }
    summary: dict[str, object] = {
        "documents": 240,
        "segments": 2,
        "characters": 10,
        "overflowed_tokens": 0,
    }
    provenance: dict[str, object] = {
        "script": script,
        "condition": condition,
        "freeze_id": audit.EXPECTED_FREEZE_ID,
        "external_rule_count": audit.EXPECTED_RULES,
    }
    timing = {"timings_seconds": {"training": 1.0}}
    for name, payload in (
        ("config.json", config),
        ("checkpoint.json", checkpoint),
        ("summary.json", summary),
        ("provenance.json", provenance),
        ("timing_metrics.json", timing),
        ("iteration_metrics.json", history),
    ):
        _write_json(run_dir / name, payload)
    for name in audit.SCIENTIFIC_FILES:
        path = run_dir / name
        if not path.exists():
            path.write_text(f"{name}\n", encoding="utf-8")
    (run_dir / "learner.sqlite").touch()
    if benchmark:
        _write_json(
            run_dir / "benchmark_metrics.json",
            {
                "passes": 3,
                "workers": 8,
                "runtime": timing,
                "inspection_segments": 2,
                "inspection_characters": 10,
            },
        )
    return run_dir, config, checkpoint, summary


@pytest.fixture(autouse=True)
def healthy_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        audit,
        "audit_database",
        lambda path: {
            "quick_check": "ok",
            "lexicon_rows": 2,
            "lexicon_expected_count": 2.0,
            "inspection_rows": 2,
            "inspection_expected_count": 2.0,
            "surface_usage_rows": 2,
            "context_usage_rows": 2,
        },
    )


def test_direct_full_run_does_not_require_benchmark_metrics(tmp_path: Path) -> None:
    run_dir, _config, _checkpoint, _summary = _run_fixture(
        tmp_path,
        script="devanagari",
        condition="continuous",
    )
    result = audit.audit_run(run_dir, None)
    assert result["valid"] is True
    assert result["run_kind"] == "direct_full_m0"
    assert result["completion"]["script"] == "devanagari"


def test_scoped_run_still_requires_benchmark_metrics(tmp_path: Path) -> None:
    run_dir, _config, _checkpoint, _summary = _run_fixture(tmp_path, scoped=True)
    result = audit.audit_run(run_dir, None)
    assert result["valid"] is False
    assert "benchmark_metrics.json is required" in result["failures"][0]


def test_benchmark_contract_remains_supported(tmp_path: Path) -> None:
    run_dir, _config, _checkpoint, _summary = _run_fixture(
        tmp_path,
        scoped=True,
        benchmark=True,
    )
    result = audit.audit_run(run_dir, None)
    assert result["valid"] is True
    assert result["run_kind"] == "benchmark_harness"


def test_metrics_directory_requires_successful_process_summary(tmp_path: Path) -> None:
    run_dir, _config, _checkpoint, _summary = _run_fixture(tmp_path)
    metrics = tmp_path / "metrics"
    metrics.mkdir()
    _write_json(metrics / "process_tree_summary.json", {"return_code": 9})
    result = audit.audit_run(run_dir, None, metrics)
    assert result["valid"] is False
    assert "process-tree metrics reports nonzero return code" in result["failures"]


def test_fixed_vocabulary_sha_and_capacity_contract(tmp_path: Path) -> None:
    run_dir, config, checkpoint, summary = _run_fixture(tmp_path)
    keys = [f"BASE_{index}" for index in range(50)] + ["LEXICAL"]
    allowed_sha = hashlib.sha256(
        "".join(f"{key}\n" for key in sorted(keys)).encode("utf-8")
    ).hexdigest()
    vocabulary = {
        "status": "frozen",
        "total_budget": 51,
        "base_unit_count": 50,
        "actual_vocabulary_size": 51,
        "allowed_key_sha256": allowed_sha,
        "surface_realizations_consume_slots": False,
    }
    config["vocab_budget"] = 51
    checkpoint["vocabulary_budget"] = vocabulary
    summary["vocabulary_budget"] = vocabulary
    provenance = json.loads((run_dir / "provenance.json").read_text(encoding="utf-8"))
    provenance["vocabulary_budget"] = vocabulary
    _write_json(run_dir / "config.json", config)
    _write_json(run_dir / "checkpoint.json", checkpoint)
    _write_json(run_dir / "summary.json", summary)
    _write_json(run_dir / "provenance.json", provenance)
    _write_json(run_dir / "vocabulary_budget.json", vocabulary)
    lines = ["rank\tkind\tform_key\tlatent_form\tphoneme_ids\tpass1_expected_count"]
    for index, key in enumerate(keys, 1):
        kind = "base" if index <= 50 else "lexical"
        lines.append(f"{index}\t{kind}\t{key}\tx\tx\t0.0")
    (run_dir / "vocabulary.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = audit.audit_run(run_dir, None)
    assert result["valid"] is True
    assert result["vocabulary"]["allowed_key_sha256"] == allowed_sha
