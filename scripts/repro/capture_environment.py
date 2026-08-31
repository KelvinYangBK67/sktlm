#!/usr/bin/env python3
"""Capture an installed environment without editable dependency paths."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = 1
ENVIRONMENT_FILENAME = "environment.json"
REQUIREMENTS_FILENAME = "requirements-freeze.txt"
KEY_PACKAGES = (
    "numpy",
    "sentencepiece",
    "PyYAML",
    "regex",
    "torch",
    "pytest",
)


def distribution_version(name: str) -> str | None:
    """Return installed distribution version without importing the package."""

    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def installed_distributions() -> list[str]:
    """Return a deterministic name==version snapshot with no editable URLs."""

    requirements: set[str] = set()
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if not name or not version or any(char in name + version for char in "\r\n"):
            continue
        requirements.add(f"{name}=={version}")
    return sorted(requirements, key=lambda value: (value.casefold(), value))


def capture_torch(
    *,
    import_module: Callable[[str], Any] = importlib.import_module,
) -> dict[str, Any]:
    """Capture optional Torch/CUDA metadata and remain valid on CPU-only hosts."""

    result: dict[str, Any] = {
        "importable": False,
        "version": distribution_version("torch"),
        "cuda_available": None,
        "cuda_runtime_version": None,
        "cudnn_version": None,
        "visible_cuda_device_count": None,
    }
    try:
        torch = import_module("torch")
        result.update(
            {
                "importable": True,
                "version": str(torch.__version__),
                "cuda_available": bool(torch.cuda.is_available()),
                "cuda_runtime_version": getattr(torch.version, "cuda", None),
                "cudnn_version": torch.backends.cudnn.version(),
                "visible_cuda_device_count": int(torch.cuda.device_count()),
            }
        )
    except Exception as exc:  # Torch can fail for reasons other than ImportError.
        result["import_error_type"] = type(exc).__name__
    return result


def _run_git(repo_dir: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=repo_dir,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def capture_git(repo_dir: Path) -> dict[str, Any]:
    """Capture repository provenance without requiring Git or a repository."""

    root = _run_git(repo_dir, "rev-parse", "--show-toplevel")
    if root is None:
        return {
            "available": False,
            "commit": None,
            "branch": None,
            "dirty": None,
        }
    commit = _run_git(repo_dir, "rev-parse", "HEAD")
    branch = _run_git(repo_dir, "symbolic-ref", "--quiet", "--short", "HEAD")
    status = _run_git(repo_dir, "status", "--porcelain", "--untracked-files=normal")
    return {
        "available": commit is not None and status is not None,
        "commit": commit,
        "branch": branch,
        "dirty": None if status is None else bool(status),
    }


def build_environment_payload(
    *,
    repo_dir: Path,
    requirements: list[str],
) -> dict[str, Any]:
    requirements_text = "".join(f"{item}\n" for item in requirements)
    return {
        "schema_version": SCHEMA_VERSION,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "machine": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "processor": platform.processor() or None,
            "hostname": platform.node() or None,
            "logical_cpu_count": os.cpu_count(),
        },
        "key_packages": {
            name: distribution_version(name) for name in KEY_PACKAGES
        },
        "torch": capture_torch(),
        "git": capture_git(repo_dir),
        "installed_distributions": requirements,
        "requirements_freeze": {
            "filename": REQUIREMENTS_FILENAME,
            "distribution_count": len(requirements),
            "sha256": hashlib.sha256(requirements_text.encode("utf-8")).hexdigest(),
        },
    }


def capture_environment(output_dir: Path, *, repo_dir: Path) -> tuple[Path, Path]:
    """Write environment artifacts, refusing to overwrite either output."""

    environment_path = output_dir / ENVIRONMENT_FILENAME
    requirements_path = output_dir / REQUIREMENTS_FILENAME
    existing = [path for path in (environment_path, requirements_path) if path.exists()]
    if existing:
        raise FileExistsError(
            "refusing to overwrite environment provenance: "
            + ", ".join(str(path) for path in existing)
        )
    if output_dir.exists() and not output_dir.is_dir():
        raise NotADirectoryError(output_dir)

    requirements = installed_distributions()
    requirements_text = "".join(f"{item}\n" for item in requirements)
    payload = build_environment_payload(
        repo_dir=repo_dir,
        requirements=requirements,
    )
    environment_text = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    with requirements_path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(requirements_text)
    with environment_path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(environment_text)
    return environment_path, requirements_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture machine-readable Python, OS, package, Torch, and Git provenance."
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        environment_path, requirements_path = capture_environment(
            args.output_dir,
            repo_dir=Path.cwd(),
        )
    except (FileExistsError, NotADirectoryError, OSError) as exc:
        parser.error(str(exc))
    print(f"environment: {environment_path}")
    print(f"requirements: {requirements_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
