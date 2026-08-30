"""Compatibility imports for :mod:`sktlm.models.transformer`."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sktlm.models.transformer import *  # noqa: F403,E402
