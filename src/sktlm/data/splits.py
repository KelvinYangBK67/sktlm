"""Stable document identifiers and manifest-level dataset splits."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping


DEFAULT_SPLIT_SEED = "sktlm_document_split_v1"
DEFAULT_SPLIT_RATIOS: dict[str, float] = {
    "train": 0.8,
    "dev": 0.1,
    "test": 0.1,
}


def make_document_id(source: str, relative_path: str) -> str:
    """Return a stable ID based only on source and source-relative path."""
    normalized_path = relative_path.replace("\\", "/")
    while normalized_path.startswith("./"):
        normalized_path = normalized_path[2:]
    key = f"{source.strip().lower()}|{normalized_path}".encode("utf-8")
    return f"doc_{hashlib.blake2b(key, digest_size=12).hexdigest()}"


def assign_split(
    document_id: str,
    seed: str = DEFAULT_SPLIT_SEED,
    ratios: Mapping[str, float] = DEFAULT_SPLIT_RATIOS,
) -> str:
    """Assign a deterministic split using the ordered ratio mapping."""
    if not ratios:
        raise ValueError("at least one split ratio is required")
    if any(weight < 0 for weight in ratios.values()):
        raise ValueError("split ratios must be non-negative")
    total = sum(ratios.values())
    if total <= 0:
        raise ValueError("split ratios must have a positive total")

    key = f"{seed}|{document_id}".encode("utf-8")
    value = int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big") / 2**64
    cumulative = 0.0
    last_name = ""
    for name, weight in ratios.items():
        last_name = name
        cumulative += weight / total
        if value < cumulative:
            return name
    return last_name
