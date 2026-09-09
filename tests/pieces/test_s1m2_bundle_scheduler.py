from __future__ import annotations

import csv
import hashlib
import json
import runpy
from concurrent.futures import Future
from dataclasses import asdict
from pathlib import Path

import pytest

import sktlm.latent.training as training
from sktlm.latent.execution_bundles import (
    BUNDLE_SCHEMA,
    PLANNER_IMPLEMENTATION,
    ExecutionBundle,
    ExecutionBundlePlan,
    _plan_digest,
    load_execution_bundle_plan,
)
from sktlm.latent.store import LexiconStore
from sktlm.latent.telemetry import RuntimeTelemetry
from sktlm.latent.training import (
    EXPECTED_FREEZE_ID,
    S1M2_MODEL,
    CorpusDocument,
    PassMetrics,
    TrainingConfig,
    _iter_document_segments,
    load_documents,
    run_training,
)
from sktlm.pieces.topology_archive import TopologyArchiveReader, _topology_payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, tuple[CorpusDocument, ...]]:
    manifest = tmp_path / "representations.csv"
    rows = []
    texts = (
        "देवोऽपि।रामोऽपि॥अश्वोऽपि।\n\nअग्निम्।इति॥\n",
        "नरोऽपि।देवश्च॥सोमम्।इति।\nअथ।पुनः॥\n",
    )
    for index, text in enumerate(texts):
        corpus = tmp_path / f"continuous-{index}.txt"
        corpus.write_text(text, encoding="utf-8", newline="")
        rows.append(
            {
                "freeze_id": EXPECTED_FREEZE_ID,
                "relative_path": f"tiny-{index}.txt",
                "script": "devanagari",
                "condition": "continuous",
                "representation_path": str(corpus),
            }
        )
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    documents = load_documents(
        manifest,
        repo_root=Path("."),
        max_documents=None,
        script="devanagari",
        condition="continuous",
    )
    return manifest, documents


def _config(
    tmp_path: Path,
    manifest: Path,
    run_id: str,
    *,
    plan: Path | None = None,
    resume: bool = False,
) -> TrainingConfig:
    return TrainingConfig(
        manifest=manifest,
        output_root=tmp_path / "runs",
        run_id=run_id,
        model=S1M2_MODEL,
        script="devanagari",
        condition="continuous",
        passes=1,
        workers=2,
        analysis_top_k=2,
        flush_types=2,
        piece_max_length=3,
        execution_bundle_plan=plan,
        resume=resume,
    )


def _write_plan(
    tmp_path: Path,
    *,
    name: str,
    manifest: Path,
    documents: tuple[CorpusDocument, ...],
    segments_per_bundle: int,
) -> Path:
    config = _config(tmp_path, manifest, "plan-enumeration")
    by_document = [list(_iter_document_segments(document, config)) for document in documents]
    representation_digest = hashlib.sha256()
    segment_digest = hashlib.sha256()
    bundles: list[ExecutionBundle] = []
    document_rows: list[dict[str, object]] = []
    total_phonemes = 0
    total_pressure = 0
    for document_index, (document, segments) in enumerate(
        zip(documents, by_document, strict=True)
    ):
        representation_digest.update(document.relative_path.encode("utf-8"))
        representation_digest.update(b"\0")
        representation_digest.update(_sha256(document.path).encode("ascii"))
        representation_digest.update(b"\n")
        for ordinal, (line_number, segment_index, segment) in enumerate(segments):
            phonemes = sum(len(token.phonemes) for token in segment.tokens)
            segment_digest.update(
                (
                    f"{document_index}\t{document.relative_path}\t{ordinal}\t"
                    f"{line_number}\t{segment_index}\t{phonemes}\n"
                ).encode("utf-8")
            )
        document_bundles = []
        for first in range(0, len(segments), segments_per_bundle):
            selected = segments[first : first + segments_per_bundle]
            first_line, first_segment, _ = selected[0]
            last_line, last_segment, _ = selected[-1]
            phonemes = sum(
                sum(len(token.phonemes) for token in segment.tokens)
                for _, _, segment in selected
            )
            pressure = sum(
                sum(len(token.phonemes) for token in segment.tokens) ** 2
                for _, _, segment in selected
            )
            document_bundles.append(
                ExecutionBundle(
                    document_index=document_index,
                    relative_path=document.relative_path,
                    bundle_index=len(document_bundles),
                    first_segment_ordinal=first,
                    last_segment_ordinal_exclusive=first + len(selected),
                    first_line_number=first_line,
                    first_segment_index=first_segment,
                    last_line_number=last_line,
                    last_segment_index=last_segment,
                    segment_count=len(selected),
                    phonemes=phonemes,
                    pressure=pressure,
                )
            )
            total_phonemes += phonemes
            total_pressure += pressure
        bundles.extend(document_bundles)
        document_rows.append(
            {
                "document_index": document_index,
                "relative_path": document.relative_path,
                "segments": len(segments),
                "bundles": len(document_bundles),
            }
        )

    planner_config = tmp_path / "planner-config.json"
    planner_config.write_text("{}\n", encoding="utf-8", newline="")
    plans_root = tmp_path / "plans"
    root = plans_root / name
    root.mkdir(parents=True, exist_ok=True)
    scan_signature = hashlib.sha256(
        segment_digest.digest() + representation_digest.digest()
    ).hexdigest()
    scan = {
        "schema_version": "sktlm-s1m2-execution-bundle-scan/v1",
        "planner_implementation": PLANNER_IMPLEMENTATION,
        "config": str(planner_config),
        "config_sha256": _sha256(planner_config),
        "manifest": str(manifest),
        "manifest_sha256": _sha256(manifest),
        "script": "devanagari",
        "condition": "continuous",
        "max_segment_tokens": 128,
        "max_lines_per_document": None,
        "segment_atomicity": "complete_existing_ObservedSegment_never_split",
        "cross_document_bundles": False,
        "scan_signature_sha256": scan_signature,
        "representation_set_sha256": representation_digest.hexdigest(),
        "segment_sequence_sha256": segment_digest.hexdigest(),
    }
    (plans_root / "scan_summary.json").write_text(
        json.dumps(scan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    target_pressure = max(1, total_pressure // max(1, len(bundles)))
    plan_sha = _plan_digest(
        bundles,
        scan_signature=scan_signature,
        target_pressure=target_pressure,
        max_segments_per_bundle=segments_per_bundle,
    )
    summary = {
        "schema_version": "sktlm-s1m2-execution-bundle-plan/v1",
        "planner_implementation": PLANNER_IMPLEMENTATION,
        "scan_signature_sha256": scan_signature,
        "plan_sha256": plan_sha,
        "script": "devanagari",
        "condition": "continuous",
        "max_segment_tokens": 128,
        "max_lines_per_document": None,
        "actual_bundle_count": len(bundles),
        "target_pressure": target_pressure,
        "max_segments_per_bundle": segments_per_bundle,
        "total_segments": sum(len(items) for items in by_document),
    }
    (root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (root / "bundles.jsonl").open("w", encoding="utf-8", newline="") as handle:
        for bundle in bundles:
            handle.write(
                json.dumps(
                    {"schema_version": BUNDLE_SCHEMA, **asdict(bundle)},
                    sort_keys=True,
                )
                + "\n"
            )
    with (root / "documents.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("document_index", "relative_path", "segments", "bundles"),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(document_rows)
    return root


def _piece_state(run_dir: Path) -> tuple[tuple[str, float, int], ...]:
    store = LexiconStore(run_dir / "learner.sqlite")
    try:
        return tuple(
            (str(key), float(count), int(support))
            for key, count, support in store.connection.execute(
                "SELECT form_key, expected_count, occurrence_support "
                "FROM piece_lexicon ORDER BY form_key"
            )
        )
    finally:
        store.close()


def test_planner_uses_training_segment_identity_and_plan_is_complete(
    tmp_path: Path,
) -> None:
    manifest, documents = _fixture(tmp_path)
    plan_root = _write_plan(
        tmp_path,
        name="candidate_identity",
        manifest=manifest,
        documents=documents,
        segments_per_bundle=1,
    )
    planner = runpy.run_path("scripts/analysis/plan_s1m2_execution_bundles.py")
    planned = list(
        planner["_iter_document_segments"](
            documents[0].path,
            document_index=0,
            relative_path=documents[0].relative_path,
            script="devanagari",
            max_segment_tokens=128,
            max_lines_per_document=None,
        )
    )
    trainer = list(_iter_document_segments(documents[0], _config(tmp_path, manifest, "x")))
    assert [
        (item.line_number, item.segment_index, item.phonemes) for item in planned
    ] == [
        (
            line_number,
            segment_index,
            sum(len(token.phonemes) for token in segment.tokens),
        )
        for line_number, segment_index, segment in trainer
    ]
    loaded = load_execution_bundle_plan(
        plan_root,
        repo_root=Path("."),
        manifest=manifest,
        documents=documents,
        script="devanagari",
        condition="continuous",
        max_segment_tokens=128,
        max_lines_per_document=None,
    )
    assert sum(bundle.segment_count for bundle in loaded.bundles) == sum(
        len(list(_iter_document_segments(document, _config(tmp_path, manifest, "y"))))
        for document in documents
    )
    assert all(bundle.segment_count == 1 for bundle in loaded.bundles)


def test_bundle_scheduler_is_bit_exact_with_legacy_document_scheduler(
    tmp_path: Path,
) -> None:
    manifest, documents = _fixture(tmp_path)
    plan_root = _write_plan(
        tmp_path,
        name="candidate_exact",
        manifest=manifest,
        documents=documents,
        segments_per_bundle=1,
    )
    legacy_config = _config(tmp_path, manifest, "legacy")
    bundled_config = _config(tmp_path, manifest, "bundled", plan=plan_root)
    legacy = run_training(
        legacy_config,
        repo_root=Path("."),
        stop_after_training=True,
    )
    bundled = run_training(
        bundled_config,
        repo_root=Path("."),
        stop_after_training=True,
    )
    assert legacy.history == bundled.history
    assert _piece_state(legacy.run_dir) == _piece_state(bundled.run_dir)
    assert (legacy.run_dir / "iteration_metrics.json").read_bytes() == (
        bundled.run_dir / "iteration_metrics.json"
    ).read_bytes()
    for document_index in range(len(documents)):
        name = f"document_{document_index:08d}.bin"
        document = documents[document_index]
        legacy_reader = TopologyArchiveReader(
            legacy.run_dir / "topology" / name,
            training._topology_archive_header(
                training._config_signature(legacy_config),
                document_index,
                document,
            ),
        )
        bundled_reader = TopologyArchiveReader(
            bundled.run_dir / "topology" / name,
            training._topology_archive_header(
                training._config_signature(bundled_config),
                document_index,
                document,
            ),
        )
        try:
            for line_number, segment_index, _segment in _iter_document_segments(
                document, legacy_config
            ):
                legacy_topology = legacy_reader.read(line_number, segment_index)
                bundled_topology = bundled_reader.read(line_number, segment_index)
                assert legacy_topology.factor_ids == bundled_topology.factor_ids
                assert tuple(
                    None if factor is None else _topology_payload(factor)
                    for factor in legacy_topology.factors
                ) == tuple(
                    None if factor is None else _topology_payload(factor)
                    for factor in bundled_topology.factors
                )
            legacy_reader.close()
            bundled_reader.close()
        finally:
            legacy_reader.close(require_eof=False)
            bundled_reader.close(require_eof=False)
    checkpoint = json.loads((bundled.run_dir / "checkpoint.json").read_text("utf-8"))
    assert checkpoint["completed_passes"] == 1
    assert checkpoint["active_pass"] is None
    assert checkpoint["next_document_index"] == 0
    assert checkpoint["history"] == list(legacy.history)
    assert "execution_bundle_plan" not in _config(
        tmp_path, manifest, "identity", plan=plan_root
    ).payload()


def test_bundle_scheduler_refills_while_canonical_first_bundle_waits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundles = tuple(
        ExecutionBundle(
            document_index=0,
            relative_path="tiny.txt",
            bundle_index=index,
            first_segment_ordinal=index,
            last_segment_ordinal_exclusive=index + 1,
            first_line_number=1,
            first_segment_index=index,
            last_line_number=1,
            last_segment_index=index,
            segment_count=1,
            phonemes=1,
            pressure=1,
        )
        for index in range(6)
    )
    plan = ExecutionBundlePlan(
        root=tmp_path,
        scan_signature_sha256="1" * 64,
        plan_sha256="2" * 64,
        materialization_sha256="5" * 64,
        planner_implementation=PLANNER_IMPLEMENTATION,
        representation_set_sha256="3" * 64,
        segment_sequence_sha256="4" * 64,
        bundles=bundles,
        by_document=(bundles,),
    )
    submitted: list[int] = []
    first_future: Future[dict[str, object]] | None = None
    first_completed_after = 0

    class FakeExecutor:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> FakeExecutor:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def submit(self, _function: object, bundle: ExecutionBundle, *_: object) -> Future:
            nonlocal first_future, first_completed_after
            future: Future[dict[str, object]] = Future()
            submitted.append(bundle.bundle_index)
            if bundle.bundle_index == 0:
                first_future = future
            else:
                future.set_result({"bundle_index": bundle.bundle_index})
            if len(submitted) == len(bundles):
                assert first_future is not None
                first_completed_after = len(submitted)
                first_future.set_result({"bundle_index": 0})
            return future

    monkeypatch.setattr(training, "ProcessPoolExecutor", FakeExecutor)
    monkeypatch.setattr(training, "_load_training_shard", lambda *_args: None)
    monkeypatch.setattr(
        training, "_load_training_bundle_shard", lambda **_kwargs: None
    )
    monkeypatch.setattr(
        training,
        "_coalesce_training_bundle_shards",
        lambda **_kwargs: {"document_index": 0},
    )
    monkeypatch.setattr(
        training,
        "_apply_training_shard",
        lambda **kwargs: kwargs["metrics"],
    )
    monkeypatch.setattr(
        training, "_retire_training_bundle_shards", lambda *_args: None
    )
    document = CorpusDocument("tiny.txt", tmp_path / "unused", "tiny", EXPECTED_FREEZE_ID)

    class FakeStore:
        path = tmp_path / "learner.sqlite"

    training._parallel_training_bundles(
        pass_index=1,
        documents=(document,),
        grammar=training.StructuredSandhiGrammar.from_default_inventory(),
        store=FakeStore(),  # type: ignore[arg-type]
        config=TrainingConfig(model=S1M2_MODEL, workers=2),
        run_dir=tmp_path,
        checkpoint={},
        telemetry=RuntimeTelemetry(),
        start_document=0,
        metrics=PassMetrics(),
        vocabulary=None,
        plan=plan,
    )
    assert submitted == list(range(6))
    assert first_completed_after == 6


def test_bundle_resume_reuses_ready_shards_and_rejects_plan_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, documents = _fixture(tmp_path)
    plan_one = _write_plan(
        tmp_path,
        name="candidate_resume_one",
        manifest=manifest,
        documents=documents,
        segments_per_bundle=1,
    )
    plan_two = _write_plan(
        tmp_path,
        name="candidate_resume_two",
        manifest=manifest,
        documents=documents,
        segments_per_bundle=2,
    )
    reference = run_training(
        _config(tmp_path, manifest, "resume-reference", plan=plan_one),
        repo_root=Path("."),
        stop_after_training=True,
    )
    original_commit = LexiconStore.commit_document
    interrupted = False

    def stop_after_first_document(
        self: LexiconStore, checkpoint: dict[str, object]
    ) -> None:
        nonlocal interrupted
        original_commit(self, checkpoint)
        if not interrupted and checkpoint.get("next_document_index") == 1:
            interrupted = True
            raise RuntimeError("synthetic bundle interruption")

    monkeypatch.setattr(LexiconStore, "commit_document", stop_after_first_document)
    with pytest.raises(RuntimeError, match="synthetic bundle interruption"):
        run_training(
            _config(tmp_path, manifest, "resume-target", plan=plan_one),
            repo_root=Path("."),
            stop_after_training=True,
        )
    monkeypatch.setattr(LexiconStore, "commit_document", original_commit)

    with pytest.raises(RuntimeError, match="does not match the active checkpoint"):
        run_training(
            _config(
                tmp_path,
                manifest,
                "resume-target",
                plan=plan_two,
                resume=True,
            ),
            repo_root=Path("."),
            stop_after_training=True,
        )

    original_load = training._load_training_bundle_shard
    resumed_bundle_keys: list[tuple[int, int]] = []

    def track_loaded(**kwargs: object) -> dict[str, object] | None:
        payload = original_load(**kwargs)  # type: ignore[arg-type]
        if payload is not None:
            bundle = kwargs["bundle"]
            assert isinstance(bundle, ExecutionBundle)
            resumed_bundle_keys.append(bundle.key)
        return payload

    monkeypatch.setattr(training, "_load_training_bundle_shard", track_loaded)
    resumed = run_training(
        _config(
            tmp_path,
            manifest,
            "resume-target",
            plan=plan_one,
            resume=True,
        ),
        repo_root=Path("."),
        stop_after_training=True,
    )
    assert any(document_index == 1 for document_index, _ in resumed_bundle_keys)
    assert reference.history == resumed.history
    assert _piece_state(reference.run_dir) == _piece_state(resumed.run_dir)
