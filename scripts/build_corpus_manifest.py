"""Build a weighted corpus manifest for tokenizer/model training.

The manifest keeps all currently processed corpora, but records conservative
weights for broad training:

- GRETIL layer weights: veda=0.8, epic/poetry/sastra=1.0, others=0.7.
- TEI files that visibly duplicate non-TEI GRETIL files get duplicate weight 0.2.
- Ambuda files visibly duplicated by GRETIL get final weight 0.2.
- Ambuda files without visible GRETIL duplicates get final weight 0.7.

This script only writes metadata and reports. It does not train anything.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


MIN_DUPLICATE_CHARS = 1000
PREFIX_SAMPLE_CHARS = 5000
DEVANAGARI_WORD_RE = re.compile(r"[\u0900-\u097F]{3,}")


@dataclass
class FileInfo:
    path: Path
    relative: str
    source: str
    layer: str
    chars: int
    lines: int
    compact_chars: int
    compact_hash: str
    prefix_sample: str
    compact_text: str | None = None
    word_set: set[str] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build weighted corpus manifest.")
    parser.add_argument("--gretil-dir", type=Path, default=Path("data/processed/gretil_devanagari"))
    parser.add_argument("--ambuda-dir", type=Path, default=Path("data/processed/ambuda-text"))
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/corpus_manifest.csv"))
    parser.add_argument("--report", type=Path, default=Path("data/_reports/corpus_manifest_summary.txt"))
    return parser.parse_args()


def compact_text(text: str) -> str:
    """Remove whitespace for duplicate checks while keeping text order."""
    return re.sub(r"\s+", "", text)


def read_info(path: Path, root: Path, source: str, keep_compact: bool, keep_words: bool) -> FileInfo:
    """Read one file and compute lightweight duplicate metadata."""
    text = path.read_text(encoding="utf-8", errors="replace")
    compact = compact_text(text)
    relative = path.relative_to(root).as_posix()
    return FileInfo(
        path=path,
        relative=relative,
        source=source,
        layer=detect_layer(relative, source),
        chars=len(text),
        lines=len(text.splitlines()) if text else 0,
        compact_chars=len(compact),
        compact_hash=hashlib.sha1(compact.encode("utf-8")).hexdigest(),
        prefix_sample=compact[:PREFIX_SAMPLE_CHARS],
        compact_text=compact if keep_compact else None,
        word_set=set(DEVANAGARI_WORD_RE.findall(text)) if keep_words else None,
    )


def detect_layer(relative: str, source: str) -> str:
    """Assign a first-pass corpus layer from the existing directory layout."""
    parts = relative.split("/")
    if source == "ambuda":
        return "ambuda"
    if not parts:
        return "other"
    if parts[0] == "tei":
        return detect_tei_layer(relative)
    top = parts[0]
    if top == "1_veda":
        return "veda"
    if top == "2_epic":
        return "epic"
    if top == "3_purana":
        return "purana"
    if top == "4_rellit":
        return "rellit"
    if top == "5_poetry":
        return "poetry"
    if top == "6_sastra":
        return "sastra"
    return "other"


def detect_tei_layer(relative: str) -> str:
    """Infer a coarse TEI layer from the TEI filename."""
    name = Path(relative).stem.lower()
    if any(token in name for token in ("veda", "upani", "brAhma", "brahma", "zrauta", "sUtra")):
        return "veda"
    if any(token in name for token in ("mahAbhArata", "rAmAyaNa", "raghuvaMza", "kumArasaMbhava")):
        return "epic"
    if "purANa" in name or "bhAgavata" in name:
        return "purana"
    if any(token in name for token in ("kAvya", "nATaka", "zatakam", "zataka", "campU", "kathA")):
        return "poetry"
    if any(
        token in name
        for token in (
            "vyAkara",
            "nyAya",
            "mImAMs",
            "vedAnta",
            "sUtra",
            "bhASya",
            "vRtti",
            "tarka",
            "saMhitA",
            "jyoti",
            "dharma",
        )
    ):
        return "sastra"
    if any(token in name for token in ("buddh", "jaina", "tantra", "stotra", "ziva", "viSNu", "bhakti")):
        return "rellit"
    return "other"


def layer_weight(layer: str) -> float:
    """Return the user-approved first-pass layer weight."""
    if layer == "veda":
        return 0.8
    if layer in {"epic", "poetry", "sastra"}:
        return 1.0
    if layer == "ambuda":
        return 0.7
    return 0.7


def duplicate_match(info: FileInfo, candidates: list[FileInfo], hash_index: dict[str, list[FileInfo]]) -> tuple[str, str]:
    """Return duplicate status and a matched path if a visible duplicate exists."""
    if info.compact_chars < MIN_DUPLICATE_CHARS:
        return "unchecked_short", ""
    exact_matches = [
        item for item in hash_index.get(info.compact_hash, []) if item.path != info.path and item.compact_chars >= MIN_DUPLICATE_CHARS
    ]
    if exact_matches:
        return "exact", exact_matches[0].relative

    sample = info.prefix_sample
    if len(sample) < MIN_DUPLICATE_CHARS:
        return "unique", ""
    for candidate in candidates:
        if candidate.path == info.path or candidate.compact_text is None:
            continue
        if candidate.compact_chars < MIN_DUPLICATE_CHARS:
            continue
        if sample in candidate.compact_text:
            return "prefix_in_candidate", candidate.relative
    return "unique", ""


def word_overlap_duplicate(info: FileInfo, candidates: list[FileInfo]) -> tuple[str, str]:
    """Detect obvious cross-source duplicates using Devanagari word overlap.

    This is used for Ambuda vs GRETIL, where line breaks, punctuation, and
    normalization differ enough that exact compact substrings can miss clear
    duplicate works.
    """
    if not info.word_set or len(info.word_set) < 100:
        return "unchecked_short", ""

    best_candidate = ""
    best_containment = 0.0
    best_jaccard = 0.0
    for candidate in candidates:
        if not candidate.word_set or len(candidate.word_set) < 100:
            continue
        shared = len(info.word_set & candidate.word_set)
        if shared < 100:
            continue
        containment = shared / len(info.word_set)
        jaccard = shared / len(info.word_set | candidate.word_set)
        if (containment, jaccard) > (best_containment, best_jaccard):
            best_candidate = candidate.relative
            best_containment = containment
            best_jaccard = jaccard

    if best_containment >= 0.40 and best_jaccard >= 0.20:
        return "word_overlap", best_candidate
    if best_containment >= 0.70 and best_jaccard >= 0.08:
        return "word_overlap", best_candidate
    return "unique", ""


def build_hash_index(files: list[FileInfo]) -> dict[str, list[FileInfo]]:
    """Group files by compact text hash."""
    index: dict[str, list[FileInfo]] = {}
    for info in files:
        index.setdefault(info.compact_hash, []).append(info)
    return index


def main() -> None:
    args = parse_args()
    gretil_paths = sorted(path for path in args.gretil_dir.rglob("*.txt") if path.is_file())
    ambuda_paths = sorted(path for path in args.ambuda_dir.rglob("*.txt") if path.is_file())

    gretil_files = [read_info(path, args.gretil_dir, "gretil", keep_compact=True, keep_words=True) for path in gretil_paths]
    ambuda_files = [read_info(path, args.ambuda_dir, "ambuda", keep_compact=False, keep_words=True) for path in ambuda_paths]

    non_tei_gretil = [info for info in gretil_files if not info.relative.startswith("tei/")]
    tei_gretil = [info for info in gretil_files if info.relative.startswith("tei/")]
    non_tei_hash_index = build_hash_index(non_tei_gretil)
    gretil_hash_index = build_hash_index(gretil_files)

    rows: list[dict[str, str]] = []
    layer_totals: dict[str, dict[str, float]] = {}
    duplicate_counts: dict[str, int] = {}

    for info in gretil_files:
        base_weight = layer_weight(info.layer)
        duplicate_status = "primary"
        duplicate_of = ""
        duplicate_weight = 1.0
        if info in tei_gretil:
            duplicate_status, duplicate_of = duplicate_match(info, non_tei_gretil, non_tei_hash_index)
            if duplicate_status in {"exact", "prefix_in_candidate"}:
                duplicate_weight = 0.2
            elif duplicate_status == "unchecked_short":
                duplicate_status = "tei_unchecked_short"
            else:
                duplicate_status = "tei_unique"
        final_weight = base_weight * duplicate_weight
        add_row(rows, info, duplicate_status, duplicate_of, base_weight, duplicate_weight, final_weight)
        add_total(layer_totals, info.layer, info.chars, final_weight)
        duplicate_counts[duplicate_status] = duplicate_counts.get(duplicate_status, 0) + 1

    for info in ambuda_files:
        duplicate_status, duplicate_of = duplicate_match(info, gretil_files, gretil_hash_index)
        if duplicate_status in {"unique", "unchecked_short"}:
            duplicate_status, duplicate_of = word_overlap_duplicate(info, gretil_files)
        if duplicate_status in {"exact", "prefix_in_candidate"}:
            final_weight = 0.2
        elif duplicate_status == "word_overlap":
            final_weight = 0.2
        else:
            final_weight = 0.7
        base_weight = 0.7
        duplicate_weight = final_weight / base_weight
        add_row(rows, info, duplicate_status, duplicate_of, base_weight, duplicate_weight, final_weight)
        add_total(layer_totals, "ambuda", info.chars, final_weight)
        duplicate_counts[f"ambuda_{duplicate_status}"] = duplicate_counts.get(f"ambuda_{duplicate_status}", 0) + 1

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "path",
                "source",
                "layer",
                "chars",
                "lines",
                "compact_chars",
                "duplicate_status",
                "duplicate_of",
                "layer_weight",
                "duplicate_weight",
                "final_weight",
                "effective_chars",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    write_report(args.report, rows, layer_totals, duplicate_counts)
    print(f"Manifest: {args.manifest}")
    print(f"Report: {args.report}")
    print(f"Rows: {len(rows)}")


def add_row(
    rows: list[dict[str, str]],
    info: FileInfo,
    duplicate_status: str,
    duplicate_of: str,
    base_weight: float,
    duplicate_weight: float,
    final_weight: float,
) -> None:
    """Append one CSV row."""
    rows.append(
        {
            "path": str(info.path.as_posix()),
            "source": info.source,
            "layer": info.layer,
            "chars": str(info.chars),
            "lines": str(info.lines),
            "compact_chars": str(info.compact_chars),
            "duplicate_status": duplicate_status,
            "duplicate_of": duplicate_of,
            "layer_weight": f"{base_weight:.3f}",
            "duplicate_weight": f"{duplicate_weight:.3f}",
            "final_weight": f"{final_weight:.3f}",
            "effective_chars": f"{info.chars * final_weight:.1f}",
        }
    )


def add_total(layer_totals: dict[str, dict[str, float]], layer: str, chars: int, weight: float) -> None:
    """Accumulate raw and weighted totals for a layer."""
    totals = layer_totals.setdefault(layer, {"files": 0, "chars": 0, "effective_chars": 0.0})
    totals["files"] += 1
    totals["chars"] += chars
    totals["effective_chars"] += chars * weight


def write_report(
    report_path: Path,
    rows: list[dict[str, str]],
    layer_totals: dict[str, dict[str, float]],
    duplicate_counts: dict[str, int],
) -> None:
    """Write a compact human-readable summary."""
    total_chars = sum(float(row["chars"]) for row in rows)
    total_effective = sum(float(row["effective_chars"]) for row in rows)
    lines = [
        "Corpus Manifest Summary",
        "",
        f"Total files: {len(rows)}",
        f"Raw characters: {int(total_chars)}",
        f"Effective weighted characters: {int(total_effective)}",
        "",
        "Layer weights:",
        "- veda: 0.8",
        "- epic: 1.0",
        "- poetry: 1.0",
        "- sastra: 1.0",
        "- other/purana/rellit/ambuda: 0.7",
        "- duplicate TEI: layer_weight * 0.2",
        "- duplicate Ambuda: 0.2; unique Ambuda: 0.7",
        "",
        "Layer totals:",
    ]
    for layer, totals in sorted(layer_totals.items()):
        percent = 100 * totals["effective_chars"] / total_effective if total_effective else 0
        lines.append(
            f"- {layer}: files={int(totals['files'])}, chars={int(totals['chars'])}, "
            f"effective_chars={int(totals['effective_chars'])}, effective_percent={percent:.2f}%"
        )
    lines.extend(["", "Duplicate status counts:"])
    for status, count in sorted(duplicate_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "TEI duplicate examples:"])
    examples = [row for row in rows if row["source"] == "gretil" and row["duplicate_status"] in {"exact", "prefix_in_candidate"}]
    for row in examples[:30]:
        lines.append(f"- {row['duplicate_status']}: {row['path']} -> {row['duplicate_of']} weight={row['final_weight']}")

    lines.extend(["", "Ambuda duplicate examples:"])
    ambuda_examples = [row for row in rows if row["source"] == "ambuda" and row["final_weight"] == "0.200"]
    if ambuda_examples:
        for row in ambuda_examples[:40]:
            lines.append(f"- {row['duplicate_status']}: {row['path']} -> {row['duplicate_of']} weight={row['final_weight']}")
    else:
        lines.append("- none")

    lines.extend(["", "Largest unique-or-unchecked Ambuda files:"])
    unique_ambuda = [row for row in rows if row["source"] == "ambuda" and row["final_weight"] == "0.700"]
    unique_ambuda.sort(key=lambda row: int(row["chars"]), reverse=True)
    for row in unique_ambuda[:20]:
        lines.append(f"- {row['duplicate_status']}: {row['path']} -> {row['duplicate_of']} weight={row['final_weight']}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
