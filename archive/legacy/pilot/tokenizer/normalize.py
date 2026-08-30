"""Compatibility imports for :mod:`sktlm.data.normalize.devanagari`."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sktlm.data.normalize.devanagari import *  # noqa: F403,E402


if __name__ == "__main__":
    main()  # noqa: F405
