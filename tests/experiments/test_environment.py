"""Reproducibility tests for deterministic environment capture."""

import hashlib
import json

from sktlm.experiments.environment import capture_environment, write_environment


def test_environment_capture_is_stable_and_requirements_are_sorted(tmp_path) -> None:
    first_payload = write_environment(tmp_path / "first")
    second_payload = write_environment(tmp_path / "second")

    first_json = (tmp_path / "first/environment.json").read_bytes()
    second_json = (tmp_path / "second/environment.json").read_bytes()
    first_freeze = (tmp_path / "first/requirements-freeze.txt").read_bytes()
    second_freeze = (tmp_path / "second/requirements-freeze.txt").read_bytes()
    assert first_payload == second_payload
    assert first_json == second_json
    assert first_freeze == second_freeze

    lines = first_freeze.decode("utf-8").splitlines()
    assert lines == sorted(lines)
    assert len(lines) == len(set(lines))
    assert first_payload["requirements_freeze_sha256"] == hashlib.sha256(
        first_freeze
    ).hexdigest()
    assert json.loads(first_json)["schema_version"] == "sktlm-environment-v1"


def test_capture_payload_has_no_path_or_timestamp() -> None:
    payload, _ = capture_environment()
    assert "timestamp" not in payload
    assert "executable" not in payload["python"]
    assert payload["environment_fingerprint_sha256"]
