"""Representation-validity gates downstream of the immutable M0 data layer."""

from __future__ import annotations


IAST_CONTINUOUS_RETIREMENT_ID = "iast-continuous-representation-validity-v1"
IAST_CONTINUOUS_RETIREMENT_REASON = (
    "IAST continuous is not injective: removing word spaces can make cross-word "
    "vowel hiatus indistinguishable from standard IAST diphthong spelling"
)


class RetiredRepresentationError(ValueError):
    """Raised when experimental code requests a retired representation."""


def require_valid_experimental_representation(
    script: str,
    spacing: str,
    *,
    context: str,
) -> None:
    """Reject IAST continuous without changing or regenerating frozen M0."""
    if script.lower() == "iast" and spacing == "continuous":
        raise RetiredRepresentationError(
            f"{context} rejects retired IAST/continuous: "
            f"{IAST_CONTINUOUS_RETIREMENT_REASON}; "
            f"decision_id={IAST_CONTINUOUS_RETIREMENT_ID}"
        )
