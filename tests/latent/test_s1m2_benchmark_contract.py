from __future__ import annotations

import json
from pathlib import Path

import pytest

from sktlm.latent import benchmark as benchmark_module
from sktlm.latent.benchmark import _load_benchmark_spec
from sktlm.latent.training import S1M2_MODEL


S1M2_IDS = (
    "s1m2_continuous_probe_m0_prime_iast",
    "s1m2_continuous_probe_m0_devanagari",
    "s1m2_continuous_representative_m0_prime_iast",
    "s1m2_continuous_representative_m0_devanagari",
    "s1m2_continuous_stress_m0_prime_iast",
    "s1m2_continuous_stress_m0_devanagari",
)


def test_s1m2_continuous_benchmark_contract_excludes_original_iast() -> None:
    specs = tuple(_load_benchmark_spec(item, Path(".").resolve()) for item in S1M2_IDS)

    assert all(spec.model == S1M2_MODEL for spec in specs)
    assert all(spec.condition == "continuous" for spec in specs)
    assert {spec.script for spec in specs} == {"iast_m0_prime", "devanagari"}
    assert all(spec.script != "iast" for spec in specs)
    assert specs[0].max_lines_per_document == 2
    assert specs[2].max_lines_per_document is None


def test_s1m2_benchmark_contract_fails_closed_on_input_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "manifest.csv"
    documents = tmp_path / "documents.txt"
    manifest.write_text("manifest\n", encoding="utf-8")
    documents.write_text("document\n", encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "schema_version": "sktlm-s1m2-continuous-runtime/v1",
                "benchmarks": {
                    "bad": {
                        "model": S1M2_MODEL,
                        "manifest": str(manifest),
                        "manifest_sha256": "0" * 64,
                        "script": "devanagari",
                        "condition": "continuous",
                        "document_list": str(documents),
                        "document_list_sha256": "0" * 64,
                        "max_lines_per_document": 1,
                        "workload": "probe"
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(benchmark_module, "S1M2_BENCHMARK_CONFIG", contract)

    with pytest.raises(RuntimeError, match="manifest.csv"):
        _load_benchmark_spec("bad", tmp_path)
