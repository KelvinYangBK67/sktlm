"""Full-M0 matrix, M0-prime consumer, runner, and aggregate tests."""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from sktlm.corpus.dataset import file_sha256
from sktlm.experiments.artifacts import payload_sha256
from sktlm.experiments.baselines.aggregate import AggregateValidationError, aggregate_formal_results
from sktlm.experiments.baselines.frozen import load_full_m0_catalog
from sktlm.experiments.baselines.full_m0 import (
    FULL_M0_REQUIRED_PROVENANCE,
    M0_PRIME_MANIFEST_SHA256,
    M0_PRIME_SURFACE_LATTICE_CONTRACT,
    M0_PRIME_TOKENIZER_COMPATIBILITY_CONTRACT,
    FullM0Cell,
    FullM0ConditionRecord,
    FullM0MatrixSettings,
    M0PrimeConsumerContract,
    build_full_m0_plan,
    build_full_m0_run_specs,
)
from sktlm.experiments.baselines.matrix import FROZEN_M0_ID
from sktlm.experiments.baselines.matrix import RetiredConditionError
from sktlm.experiments.baselines.production import build_production_queue
from sktlm.experiments.baselines.runner import run_supported_cell
from sktlm.tokenizers.character import CharacterTokenizer
from sktlm.tokenizers.sentencepiece import SentencePieceBPETokenizer, SentencePieceUnigramTokenizer
from sktlm.tokenizers.surface_lattice import SurfaceLatticeTokenizer, atomize_m0_prime_iast_surface


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _fixture_settings(tmp_path: Path) -> FullM0MatrixSettings:
    canonical_manifest = tmp_path / "canonical.csv"
    representation_manifest = tmp_path / "representations.csv"
    prime_manifest = tmp_path / "prime" / "manifest.csv"
    prime_root = tmp_path / "prime_payload"
    documents = [
        {"relative": "z/train.txt", "id": "doc_train", "split": "train", "text": "gʰkʰēōaiaugʰkʰēō\n"},
        {"relative": "a/test.txt", "id": "doc_test", "split": "test", "text": "gʰōēaiau\n"},
    ]
    canonical_rows = [
        {
            "freeze_id": FROZEN_M0_ID,
            "freeze_input_path": item["relative"],
            "document_id": item["id"],
            "split": item["split"],
            "source": "fixture",
            "layer": "fixture",
            "canonical_hash": f"canonical-{item['id']}",
        }
        for item in documents
    ]
    _write_csv(
        canonical_manifest,
        ["freeze_id", "freeze_input_path", "document_id", "split", "source", "layer", "canonical_hash"],
        canonical_rows,
    )

    representation_rows: list[dict[str, str]] = []
    source_rows: dict[str, dict[str, str]] = {}
    for script in ("iast", "devanagari"):
        for spacing in ("surface_word", "legacy_joined", "continuous"):
            for item in documents:
                path = tmp_path / "representations" / script / spacing / item["relative"]
                path.parent.mkdir(parents=True, exist_ok=True)
                text = item["text"] if script == "iast" else ("कखगघ\n" if item["split"] == "train" else "चछजझ\n")
                path.write_text(text, encoding="utf-8")
                row = {
                    "freeze_id": FROZEN_M0_ID,
                    "relative_path": item["relative"],
                    "script": script,
                    "condition": spacing,
                    "representation_path": path.as_posix(),
                    "representation_hash": file_sha256(path),
                }
                representation_rows.append(row)
                if script == "devanagari" and spacing == "continuous":
                    source_rows[item["relative"]] = row
    _write_csv(
        representation_manifest,
        ["freeze_id", "relative_path", "script", "condition", "representation_path", "representation_hash"],
        representation_rows,
    )

    prime_rows: list[dict[str, str]] = []
    canonical_by_relative = {row["freeze_input_path"]: row for row in canonical_rows}
    for item in sorted(documents, key=lambda row: row["relative"]):
        path = prime_root / item["relative"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item["text"], encoding="utf-8")
        source = source_rows[item["relative"]]
        canonical = canonical_by_relative[item["relative"]]
        prime_rows.append(
            {
                "schema_version": "sktlm-m0-prime-representation/v1",
                "derivation_id": "m0-prime-iast-continuous-v1",
                "freeze_id": FROZEN_M0_ID,
                "relative_path": item["relative"],
                "document_id": item["id"],
                "split": item["split"],
                "canonical_hash": canonical["canonical_hash"],
                "script": "iast_m0_prime",
                "condition": "continuous",
                "representation_path": path.as_posix(),
                "representation_hash": file_sha256(path),
                "byte_count": str(path.stat().st_size),
                "source_script": "devanagari",
                "source_condition": "continuous",
                "source_representation_path": source["representation_path"],
                "source_representation_hash": source["representation_hash"],
            }
        )
    fields = list(prime_rows[0])
    _write_csv(prime_manifest, fields, prime_rows)
    prime_contract = M0PrimeConsumerContract.fixture(
        manifest=prime_manifest,
        payload_root=prime_root,
        manifest_sha256=file_sha256(prime_manifest),
    )

    base = FullM0MatrixSettings.from_yaml(
        Path("configs/experiments/baselines/full_m0_matrix.yaml")
    )
    records = tuple(
        FullM0ConditionRecord(
            FullM0Cell(
                method=record.cell.method,
                script=record.cell.script,
                spacing=record.cell.spacing,
                substrate=record.cell.substrate,
                observation_manifest=(
                    prime_manifest if record.cell.substrate == "M0-prime" else representation_manifest
                ),
            ),
            record.role,
        )
        for record in base.condition_manifest
    )
    return FullM0MatrixSettings(
        freeze_id=FROZEN_M0_ID,
        canonical_manifest=canonical_manifest,
        m0_representation_manifest=representation_manifest,
        m0_prime=prime_contract,
        artifact_root=tmp_path / "artifacts",
        seed=0,
        vocab_size=64,
        condition_manifest=records,
        downstream_lm=replace(base.downstream_lm, device="cpu"),
    )


def _rewrite_manifest(settings: FullM0MatrixSettings, mutate) -> FullM0MatrixSettings:
    path = settings.m0_prime.manifest
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or ())
        rows = list(reader)
    mutate(rows)
    _write_csv(path, fields, rows)
    contract = M0PrimeConsumerContract.fixture(
        manifest=path,
        payload_root=settings.m0_prime.payload_root,
        manifest_sha256=file_sha256(path),
    )
    return replace(settings, m0_prime=contract)


def test_historical_contract_and_full_m0_counts_are_both_preserved() -> None:
    historical = yaml.safe_load(Path("configs/experiments/baselines/m0_matrix.yaml").read_text())
    assert len(historical["conditions"]) == 22
    assert sum(row["status"] == "valid" for row in historical["conditions"]) == 18
    assert sum(row["status"] == "retired" for row in historical["conditions"]) == 4
    settings = FullM0MatrixSettings.from_yaml(Path("configs/experiments/baselines/full_m0_matrix.yaml"))
    plan = build_full_m0_plan(settings)
    assert plan["full_m0_production_cell_count"] == 22
    assert plan["m0_prime_replacement_cell_count"] == 4
    assert len(build_full_m0_run_specs(settings)) == 22
    assert M0_PRIME_MANIFEST_SHA256 == settings.m0_prime.manifest_sha256


def test_full_catalog_exposes_six_conditions_and_validates_prime_identity(tmp_path: Path) -> None:
    settings = _fixture_settings(tmp_path)
    catalog = load_full_m0_catalog(settings, expected_documents=2)
    assert catalog.document_count == 2
    assert catalog.representation_file_count == 12
    assert ("iast", "continuous") not in catalog.files_by_condition
    assert ("iast_m0_prime", "continuous") in catalog.files_by_condition
    assert [row.relative_path for row in catalog.files_by_condition[("iast_m0_prime", "continuous")]] == [
        "z/train.txt", "a/test.txt"
    ]


@pytest.mark.parametrize("corruption", ["derivation", "document", "file_hash"])
def test_prime_consumer_fails_closed_on_manifest_or_payload_corruption(tmp_path: Path, corruption: str) -> None:
    settings = _fixture_settings(tmp_path)
    if corruption == "derivation":
        settings = _rewrite_manifest(settings, lambda rows: rows[0].__setitem__("derivation_id", "wrong"))
    elif corruption == "document":
        settings = _rewrite_manifest(settings, lambda rows: rows[0].__setitem__("document_id", "wrong"))
    else:
        path = settings.m0_prime.payload_root / "a/test.txt"
        path.write_text("tampered\n", encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError), match="M0-prime"):
        load_full_m0_catalog(settings, expected_documents=2)


def test_prime_consumer_rejects_manifest_sha_mismatch(tmp_path: Path) -> None:
    settings = _fixture_settings(tmp_path)
    settings.m0_prime.manifest.write_text("broken\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest SHA-256 mismatch"):
        load_full_m0_catalog(settings, expected_documents=2)


@pytest.mark.parametrize(
    "condition_id",
    [
        "bpe__iast_m0_prime__continuous",
        "unigram__iast_m0_prime__continuous",
        "unicode_codepoint__iast_m0_prime__continuous",
        "surface_lattice__iast_m0_prime__continuous",
    ],
)
def test_four_prime_tokenizers_pass_bounded_lossless_smoke(tmp_path: Path, condition_id: str) -> None:
    settings = _fixture_settings(tmp_path)
    artifact = run_supported_cell(
        settings,
        condition_id,
        repo_root=tmp_path,
        max_train_segments=1,
        max_eval_segments=1,
        prediction_examples=1,
        expected_documents=2,
        require_clean_git=False,
        run_downstream=False,
    )
    prediction = json.loads((artifact / "predictions.jsonl").read_text(encoding="utf-8"))
    text = prediction["text"]
    fingerprint = json.loads((artifact / "tokenizer_fingerprint.json").read_text())
    assert fingerprint["config"]["input_compatibility_contract"] == M0_PRIME_TOKENIZER_COMPATIBILITY_CONTRACT
    if condition_id.startswith("bpe__"):
        tokenizer = SentencePieceBPETokenizer(artifact / "tokenizer/bpe_64.model")
        assert tokenizer.decode(tokenizer.encode(text).ids) == text
        assert tokenizer.unknown_id in tokenizer.encode("Ω").ids
    elif condition_id.startswith("unigram__"):
        tokenizer = SentencePieceUnigramTokenizer(artifact / "tokenizer/unigram_64.model")
        assert tokenizer.decode(tokenizer.encode(text).ids) == text
        assert tokenizer.unknown_id in tokenizer.encode("Ω").ids
    elif condition_id.startswith("surface_lattice__"):
        tokenizer = SurfaceLatticeTokenizer(artifact / "tokenizer/surface_lattice_64.model")
        encoding = tokenizer.encode(text)
        assert tokenizer.decode(encoding.ids) == text
        assert tokenizer.atomizer_contract == M0_PRIME_SURFACE_LATTICE_CONTRACT
        assert tokenizer.encode("Ω").ids == (0,)
    else:
        assert "".join(prediction["pieces"]) == text
        tokenizer = CharacterTokenizer.train(["gʰkʰēōaiau"])
        assert tokenizer.decode(tokenizer.encode(text).ids) == text
        assert tokenizer.encode("Ω").ids == (0,)
    metrics = json.loads((artifact / "metrics.json").read_text())
    assert metrics["exact_reconstruction_checked_segments"] == 1


def test_prime_surface_atomizer_keeps_new_letters_and_barriers_exact() -> None:
    text = "kʰēō, ai"
    atoms = atomize_m0_prime_iast_surface(text)
    assert "".join(atom.text for atom in atoms) == text
    assert all(atom.mergeable for atom in atoms[:4])
    assert atoms[4].text == "," and atoms[4].mergeable is False
    assert atoms[5].text == " " and atoms[5].mergeable is False


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _complete_formal_bundles(settings: FullM0MatrixSettings) -> Path:
    requirements = b"fixture==1\n"
    requirements_hash = __import__("hashlib").sha256(requirements).hexdigest()
    m0_hash = file_sha256(settings.m0_representation_manifest)
    for spec in build_full_m0_run_specs(settings):
        artifact = spec.artifact_dir
        artifact.mkdir(parents=True)
        observation_hash = settings.m0_prime.manifest_sha256 if spec.cell.substrate == "M0-prime" else m0_hash
        config = {
            "matrix": "full_m0_baselines",
            "condition_manifest_version": settings.condition_manifest_version,
            "condition_id": spec.cell.condition_id,
            "condition_status": "valid",
            "retirement_reason": None,
            "run_scope": "formal_production",
            "method": spec.cell.method,
            "script": spec.cell.script,
            "spacing": spec.cell.spacing,
            "seed": settings.seed,
            "corpus_freeze_id": settings.freeze_id,
            "canonical_manifest": settings.canonical_manifest.as_posix(),
            "representation_manifest": spec.observation_manifest.as_posix(),
            "observation_manifest": spec.observation_manifest.as_posix(),
            "substrate": spec.cell.substrate,
            "full_m0_definition_version": settings.full_m0_definition_version,
            "tokenizer": spec.cell.tokenizer_config(vocab_size=settings.vocab_size),
            "limits": {"max_train_segments": None, "max_eval_segments": None},
            "common_downstream_lm": {
                "enabled": True,
                "contract": settings.downstream_lm.as_dict(),
                "runtime_device_override": None,
                "runtime_max_steps_override": None,
            },
        }
        (artifact / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
        data = {
            "corpus_freeze_id": settings.freeze_id,
            "script": spec.cell.script,
            "spacing": spec.cell.spacing,
            "substrate": spec.cell.substrate,
            "observation_manifest": spec.observation_manifest.as_posix(),
            "observation_manifest_sha256": observation_hash,
            "canonical_manifest_sha256": file_sha256(settings.canonical_manifest),
        }
        data["fingerprint_sha256"] = payload_sha256(data)
        tokenizer = {
            "condition_id": spec.cell.condition_id,
            "config": spec.cell.tokenizer_config(vocab_size=settings.vocab_size),
        }
        tokenizer["fingerprint_sha256"] = payload_sha256(tokenizer)
        environment = {"requirements_freeze_sha256": requirements_hash}
        environment["environment_fingerprint_sha256"] = payload_sha256(environment)
        _write_json(artifact / "data_fingerprint.json", data)
        _write_json(artifact / "tokenizer_fingerprint.json", tokenizer)
        _write_json(artifact / "environment.json", environment)
        (artifact / "requirements-freeze.txt").write_bytes(requirements)
        (artifact / "git_commit.txt").write_text("a" * 40 + "\n", encoding="utf-8")
        provenance = {
            "method": spec.cell.method,
            "script": spec.cell.script,
            "spacing": spec.cell.spacing,
            "substrate": spec.cell.substrate,
            "condition_status": "valid",
            "retirement_reason": None,
            "condition_manifest_version": settings.condition_manifest_version,
            "full_m0_definition_version": settings.full_m0_definition_version,
            "run_scope": "formal_production",
            "config": config,
            "config_sha256": payload_sha256(config),
            "seed": settings.seed,
            "code_commit": "a" * 40,
            "corpus_freeze_id": settings.freeze_id,
            "canonical_manifest_sha256": file_sha256(settings.canonical_manifest),
            "representation_manifest_sha256": observation_hash,
            "observation_manifest": spec.observation_manifest.as_posix(),
            "observation_manifest_sha256": observation_hash,
            "input_compatibility_contract": spec.cell.tokenizer_config(
                vocab_size=settings.vocab_size
            ).get(
                "input_compatibility_contract",
                "frozen-m0-tokenizer-compatibility-v1",
            ),
            "data_fingerprint_sha256": data["fingerprint_sha256"],
            "tokenizer_fingerprint_sha256": tokenizer["fingerprint_sha256"],
            "environment_fingerprint_sha256": environment["environment_fingerprint_sha256"],
            "training_initialization": "fresh_per_cell",
            "training_instance_id": payload_sha256(
                {
                    "condition_id": spec.cell.condition_id,
                    "seed": settings.seed,
                    "data_fingerprint_sha256": data["fingerprint_sha256"],
                    "tokenizer_fingerprint_sha256": tokenizer["fingerprint_sha256"],
                    "observation_manifest_sha256": observation_hash,
                    "common_downstream_contract": settings.downstream_lm.contract_version,
                }
            ),
            "software_versions": {"python": "fixture"},
            "artifact_location": artifact.as_posix(),
        }
        assert set(FULL_M0_REQUIRED_PROVENANCE) <= set(provenance)
        _write_json(artifact / "provenance.json", provenance)
        _write_json(
            artifact / "metrics.json",
            {
                "condition_id": spec.cell.condition_id,
                "condition_status": "valid",
                "run_scope": "formal_production",
                "common_downstream_status": "complete",
                "common_downstream_finite": True,
                "common_downstream_bits_per_character": 1.0,
                "common_downstream_bits_per_byte": 0.5,
                "bits_per_canonical_unit": 1.2,
                "common_downstream_total_nll": 10.0,
                "common_downstream_scored_tokens": 8,
                "unk_count": 0,
                "unk_rate": 0.0,
                "unknown_semantics": "fixture",
                "runtime_seconds": 1.0,
                "peak_rss_bytes": 1024,
                "token_count": 10,
                "occupied_token_types": 5,
            },
        )
        files = {
            path.relative_to(artifact).as_posix(): file_sha256(path)
            for path in artifact.rglob("*")
            if path.is_file()
        }
        _write_json(
            artifact / "COMPLETED.json",
            {
                "schema_version": "m0-baseline-completion-v1",
                "condition_id": spec.cell.condition_id,
                "condition_status": "valid",
                "run_scope": "formal_production",
                "files": files,
            },
        )
    return settings.artifact_root


def test_full_aggregate_requires_exact_22_and_independent_provenance(tmp_path: Path) -> None:
    settings = _fixture_settings(tmp_path)
    root = _complete_formal_bundles(settings)
    aggregate = aggregate_formal_results(settings, root, repo_root=tmp_path)
    assert aggregate["aggregate_schema_version"] == "full-m0-baseline-aggregate/v1"
    assert aggregate["full_m0_production_cell_count"] == 22
    assert len({row["provenance"]["training_instance_id"] for row in aggregate["results"].values()}) == 22
    missing = root / "bpe__iast_m0_prime__continuous"
    held = tmp_path / "held"
    missing.rename(held)
    with pytest.raises(AggregateValidationError, match="condition set mismatch"):
        aggregate_formal_results(settings, root, repo_root=tmp_path)
    held.rename(missing)
    (root / "bpe__iast__continuous").mkdir()
    with pytest.raises(AggregateValidationError, match="retired condition"):
        aggregate_formal_results(settings, root, repo_root=tmp_path)


def test_full_queue_prints_22_jobs_and_never_original_iast_continuous(tmp_path: Path) -> None:
    settings = _fixture_settings(tmp_path)
    queue = build_production_queue(
        settings, config_path=Path("configs/experiments/baselines/full_m0_matrix.yaml")
    )
    assert queue["launches_jobs"] is False
    assert queue["scheduled_job_count"] == 22
    ids = {job["condition_id"] for job in queue["jobs"]}
    assert not ids & {
        "bpe__iast__continuous", "unigram__iast__continuous",
        "unicode_codepoint__iast__continuous", "surface_lattice__iast__continuous",
    }


@pytest.mark.parametrize(
    "condition_id",
    [
        "bpe__iast__continuous",
        "unigram__iast__continuous",
        "unicode_codepoint__iast__continuous",
        "surface_lattice__iast__continuous",
    ],
)
def test_full_runner_and_queue_explicitly_reject_original_iast_continuous(
    tmp_path: Path, condition_id: str
) -> None:
    settings = _fixture_settings(tmp_path)
    with pytest.raises(RetiredConditionError, match="not injective"):
        run_supported_cell(
            settings,
            condition_id,
            repo_root=tmp_path,
            max_train_segments=1,
            max_eval_segments=1,
            require_clean_git=False,
            run_downstream=False,
            expected_documents=2,
        )
    with pytest.raises(RetiredConditionError, match="production scheduling rejects"):
        build_production_queue(
            settings,
            config_path=Path("configs/experiments/baselines/full_m0_matrix.yaml"),
            condition_id=condition_id,
        )


def test_full_aggregate_rejects_wrong_prime_observation_manifest_provenance(tmp_path: Path) -> None:
    settings = _fixture_settings(tmp_path)
    root = _complete_formal_bundles(settings)
    artifact = root / "bpe__iast_m0_prime__continuous/seed_0"
    provenance_path = artifact / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["observation_manifest_sha256"] = file_sha256(settings.m0_representation_manifest)
    _write_json(provenance_path, provenance)
    completion = json.loads((artifact / "COMPLETED.json").read_text(encoding="utf-8"))
    completion["files"]["provenance.json"] = file_sha256(provenance_path)
    _write_json(artifact / "COMPLETED.json", completion)
    with pytest.raises(AggregateValidationError, match="observation-manifest identity mismatch"):
        aggregate_formal_results(settings, root, repo_root=tmp_path)
