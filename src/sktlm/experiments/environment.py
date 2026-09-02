"""Deterministic software-environment capture for reproducible artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from importlib import metadata
from pathlib import Path
from typing import Any


ENVIRONMENT_SCHEMA_VERSION = "sktlm-environment-v1"


def installed_requirements() -> tuple[str, ...]:
    """Return a normalized, sorted freeze without paths, timestamps, or locale state."""
    packages: dict[str, str] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            continue
        normalized = str(name).strip().lower().replace("_", "-")
        version = str(distribution.version).strip()
        previous = packages.get(normalized)
        if previous is not None and previous != version:
            raise RuntimeError(
                f"environment contains conflicting versions for {normalized}: "
                f"{previous}, {version}"
            )
        packages[normalized] = version
    return tuple(f"{name}=={packages[name]}" for name in sorted(packages))


def capture_environment() -> tuple[dict[str, Any], str]:
    """Capture stable runtime facts and the exact deterministic requirements text."""
    requirements = "\n".join(installed_requirements()) + "\n"
    requirements_sha256 = hashlib.sha256(requirements.encode("utf-8")).hexdigest()
    payload: dict[str, Any] = {
        "schema_version": ENVIRONMENT_SCHEMA_VERSION,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "byteorder": sys.byteorder,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "requirements_freeze_sha256": requirements_sha256,
        "package_count": len(requirements.splitlines()),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["environment_fingerprint_sha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return payload, requirements


def write_environment(output_dir: Path) -> dict[str, Any]:
    """Write the two required environment files and return the JSON payload."""
    payload, requirements = capture_environment()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "environment.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "requirements-freeze.txt").write_text(requirements, encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a deterministic sktlm environment")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    payload = write_environment(args.output_dir)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
