from __future__ import annotations

import importlib.util
import json
import sys
from importlib import metadata
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[2] / "scripts/repro/capture_environment.py"
SPEC = importlib.util.spec_from_file_location("capture_environment_for_tests", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
capture = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = capture
SPEC.loader.exec_module(capture)


def test_capture_writes_machine_readable_environment(tmp_path: Path) -> None:
    output_dir = tmp_path / "provenance"
    environment_path, requirements_path = capture.capture_environment(
        output_dir,
        repo_dir=Path.cwd(),
    )

    assert environment_path == output_dir / "environment.json"
    assert requirements_path == output_dir / "requirements-freeze.txt"
    assert environment_path.read_bytes().endswith(b"\n")
    assert requirements_path.read_bytes().endswith(b"\n")

    payload = json.loads(environment_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert set(payload) == {
        "git",
        "installed_distributions",
        "key_packages",
        "machine",
        "python",
        "requirements_freeze",
        "schema_version",
        "torch",
    }
    assert {"version", "implementation", "executable"} <= set(payload["python"])
    assert {
        "platform",
        "system",
        "release",
        "architecture",
        "processor",
        "hostname",
        "logical_cpu_count",
    } <= set(payload["machine"])
    assert {"commit", "branch", "dirty"} <= set(payload["git"])
    assert payload["key_packages"]["pytest"] == metadata.version("pytest")

    requirements = requirements_path.read_text(encoding="utf-8").splitlines()
    assert requirements == sorted(
        set(requirements),
        key=lambda value: (value.casefold(), value),
    )
    assert payload["installed_distributions"] == requirements
    assert payload["requirements_freeze"]["distribution_count"] == len(requirements)


def test_optional_torch_and_git_metadata_can_be_unavailable(tmp_path: Path) -> None:
    def unavailable(_name: str) -> object:
        raise ImportError("simulated CPU-only/unavailable Torch")

    torch = capture.capture_torch(import_module=unavailable)
    git = capture.capture_git(tmp_path)

    assert torch["importable"] is False
    assert torch["cuda_available"] is None
    assert torch["visible_cuda_device_count"] is None
    assert torch["import_error_type"] == "ImportError"
    assert git == {
        "available": False,
        "commit": None,
        "branch": None,
        "dirty": None,
    }


def test_capture_refuses_to_overwrite_provenance(tmp_path: Path) -> None:
    output_dir = tmp_path / "provenance"
    capture.capture_environment(output_dir, repo_dir=Path.cwd())

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        capture.capture_environment(output_dir, repo_dir=Path.cwd())
