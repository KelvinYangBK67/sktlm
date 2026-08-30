from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class SandhiRule:
    rule_id: str
    left: str
    right: str
    surface: str
    variant: int
    status: str


def _repo_root() -> Path:
    """
    Resolve the repository root from this file location.

    Expected layout:
        <repo>/
            data/
                rules/
                    external_sandhi.tsv
            src/
                sktlm/
                    sandhi/
                        rules.py
    """
    return Path(__file__).resolve().parents[3]


DEFAULT_EXTERNAL_SANDHI_PATH = (
    _repo_root() / "data" / "rules" / "external_sandhi.tsv"
)


def _is_nfc(text: str) -> bool:
    return unicodedata.normalize("NFC", text) == text


def validate_rules(rules: Iterable[SandhiRule]) -> tuple[SandhiRule, ...]:
    """
    Validate a complete external-sandhi rule inventory.

    Raises:
        ValueError: if any rule or inventory-level invariant is violated.
    """
    rules = tuple(rules)

    if not rules:
        raise ValueError("Sandhi rule inventory is empty.")

    seen_ids: set[str] = set()
    seen_transitions: set[tuple[str, str, str]] = set()

    for rule in rules:
        if not rule.rule_id:
            raise ValueError("Encountered rule with empty rule_id.")
        if rule.rule_id in seen_ids:
            raise ValueError(f"Duplicate rule_id: {rule.rule_id}")
        seen_ids.add(rule.rule_id)

        if not rule.left:
            raise ValueError(f"{rule.rule_id}: left is empty.")
        if not rule.right:
            raise ValueError(f"{rule.rule_id}: right is empty.")
        if not rule.surface:
            raise ValueError(f"{rule.rule_id}: surface is empty.")

        if rule.variant < 1:
            raise ValueError(
                f"{rule.rule_id}: variant must be a positive integer, "
                f"got {rule.variant}."
            )

        if not rule.status:
            raise ValueError(f"{rule.rule_id}: status is empty.")

        for field_name, value in (
            ("rule_id", rule.rule_id),
            ("left", rule.left),
            ("right", rule.right),
            ("surface", rule.surface),
            ("status", rule.status),
        ):
            if not _is_nfc(value):
                raise ValueError(
                    f"{rule.rule_id}: {field_name} is not Unicode NFC: {value!r}"
                )

        if "V̆" in rule.left or "V̆" in rule.right or "V̆" in rule.surface:
            raise ValueError(
                f"{rule.rule_id}: unexpanded V̆ placeholder remains."
            )

        if "|" in rule.surface:
            raise ValueError(
                f"{rule.rule_id}: surface still contains '|' alternative syntax."
            )

        transition = (rule.left, rule.right, rule.surface)
        if transition in seen_transitions:
            raise ValueError(
                "Duplicate left/right/surface transition: "
                f"{rule.left!r} + {rule.right!r} -> {rule.surface!r}"
            )
        seen_transitions.add(transition)

    return rules


def load_external_sandhi_rules(
    path: str | Path = DEFAULT_EXTERNAL_SANDHI_PATH,
    *,
    active_only: bool = True,
    validate: bool = True,
) -> tuple[SandhiRule, ...]:
    """
    Load the tracked machine-readable external sandhi inventory.

    Expected TSV columns:
        rule_id
        left
        right
        surface
        variant
        status

    Args:
        path:
            Path to external_sandhi.tsv.
        active_only:
            If True, return only rows whose status is "active".
        validate:
            If True, validate the loaded inventory before returning it.
    """
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"Sandhi rule file not found: {path}")

    required_fields = {
        "rule_id",
        "left",
        "right",
        "surface",
        "variant",
        "status",
    }

    rules: list[SandhiRule] = []

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")

        if reader.fieldnames is None:
            raise ValueError(f"{path}: missing TSV header.")

        fields = set(reader.fieldnames)
        missing = required_fields - fields
        if missing:
            raise ValueError(
                f"{path}: missing required columns: {sorted(missing)}"
            )

        for line_no, row in enumerate(reader, start=2):
            try:
                variant = int(row["variant"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{path}:{line_no}: invalid variant {row.get('variant')!r}"
                ) from exc

            rule = SandhiRule(
                rule_id=row["rule_id"],
                left=row["left"],
                right=row["right"],
                surface=row["surface"],
                variant=variant,
                status=row["status"],
            )

            if active_only and rule.status != "active":
                continue

            rules.append(rule)

    loaded = tuple(rules)
    return validate_rules(loaded) if validate else loaded


def lookup(
    rules: Iterable[SandhiRule],
    left: str,
    right: str,
) -> tuple[SandhiRule, ...]:
    """
    Return all rules licensed for one literal left/right input pair.

    The result preserves file order, so variant order is deterministic.
    """
    return tuple(
        rule
        for rule in rules
        if rule.left == left and rule.right == right
    )


def lookup_surfaces(
    rules: Iterable[SandhiRule],
    left: str,
    right: str,
) -> tuple[str, ...]:
    """
    Convenience wrapper returning only licensed surface outputs.
    """
    return tuple(
        rule.surface
        for rule in lookup(rules, left, right)
    )
