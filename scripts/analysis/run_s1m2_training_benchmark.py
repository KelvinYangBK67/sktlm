#!/usr/bin/env python3
"""Run the normal training CLI and persist its engineering runtime payload.

This thin harness is intentionally science-neutral.  Set ``PYTHONPATH`` to the
checkout under test; the harness then imports that checkout's CLI and training
implementation, captures the returned ``TrainingResult.runtime``, and writes it
outside the canonical run artifacts for before/after engineering comparison.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-output", required=True, type=Path)
    parser.add_argument("training_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    training_args = args.training_args
    if training_args and training_args[0] == "--":
        training_args = training_args[1:]
    if not training_args:
        parser.error("training CLI arguments are required after --")

    import sktlm.experiments.training.latent_lexicon as training_cli

    original = training_cli.run_training

    def capture_runtime(*call_args: Any, **call_kwargs: Any):
        result = original(*call_args, **call_kwargs)
        _write_json(args.runtime_output, result.runtime)
        return result

    training_cli.run_training = capture_runtime
    training_cli.main(training_args)


if __name__ == "__main__":
    main()
