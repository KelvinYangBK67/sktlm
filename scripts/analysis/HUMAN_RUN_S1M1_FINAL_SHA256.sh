#!/usr/bin/env bash
# Human-run, resumable hashing of the twelve large local S1M1 exports.
# This script never deletes source or partial files and never overwrites final output.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

output_root="${1:-artifacts/s1m1_final/source_hashes}"
parts_dir="$output_root/parts"
final_manifest="$output_root/SHA256SUMS.tsv"

if [[ -e "$final_manifest" ]]; then
  echo "REFUSING: final manifest already exists: $final_manifest" >&2
  exit 2
fi
mkdir -p "$parts_dir"

entries=(
  "iast__surface_word|analyses|artifacts/cloud_scientific/cloud_full_m0_iast_surface_word_p10_rep01_w8_p3/benchmark/analyses.jsonl"
  "iast__surface_word|boundaries|artifacts/cloud_scientific/cloud_full_m0_iast_surface_word_p10_rep01_w8_p3/benchmark/boundary_posteriors.jsonl"
  "iast__surface_word|lexicon|artifacts/cloud_scientific/cloud_full_m0_iast_surface_word_p10_rep01_w8_p3/benchmark/latent_lexicon.tsv"
  "iast__legacy_joined|analyses|artifacts/post_gate/collected/cloud_full_m0_iast_legacy_joined_p10_w8_p3/benchmark/analyses.jsonl"
  "iast__legacy_joined|boundaries|artifacts/post_gate/collected/cloud_full_m0_iast_legacy_joined_p10_w8_p3/benchmark/boundary_posteriors.jsonl"
  "iast__legacy_joined|lexicon|artifacts/post_gate/collected/cloud_full_m0_iast_legacy_joined_p10_w8_p3/benchmark/latent_lexicon.tsv"
  "devanagari__surface_word|analyses|artifacts/post_gate/collected/cloud_full_m0_devanagari_surface_word_p10_w8_p3/benchmark/analyses.jsonl"
  "devanagari__surface_word|boundaries|artifacts/post_gate/collected/cloud_full_m0_devanagari_surface_word_p10_w8_p3/benchmark/boundary_posteriors.jsonl"
  "devanagari__surface_word|lexicon|artifacts/post_gate/collected/cloud_full_m0_devanagari_surface_word_p10_w8_p3/benchmark/latent_lexicon.tsv"
  "devanagari__legacy_joined|analyses|artifacts/post_gate/collected/cloud_full_m0_devanagari_legacy_joined_p10_w8_p3/benchmark/analyses.jsonl"
  "devanagari__legacy_joined|boundaries|artifacts/post_gate/collected/cloud_full_m0_devanagari_legacy_joined_p10_w8_p3/benchmark/boundary_posteriors.jsonl"
  "devanagari__legacy_joined|lexicon|artifacts/post_gate/collected/cloud_full_m0_devanagari_legacy_joined_p10_w8_p3/benchmark/latent_lexicon.tsv"
)

for index in "${!entries[@]}"; do
  IFS='|' read -r cell_id artifact_role relative_path <<< "${entries[$index]}"
  part="$parts_dir/$(printf '%02d' "$index").tsv"
  if [[ -e "$part" ]]; then
    recorded_path="$(awk -F '\t' 'NR == 2 {print $3}' "$part")"
    if [[ "$recorded_path" != "$relative_path" ]]; then
      echo "REFUSING: completed part has wrong path: $part" >&2
      exit 2
    fi
    echo "SKIP completed: $relative_path"
    continue
  fi
  if [[ ! -f "$relative_path" ]]; then
    echo "MISSING: $relative_path" >&2
    exit 2
  fi
  partial="$part.partial.$$"
  bytes="$(wc -c < "$relative_path" | tr -d '[:space:]')"
  sha256="$(sha256sum "$relative_path" | awk '{print $1}')"
  printf 'cell_id\tartifact_role\trelative_path\tsize_bytes\tsha256\n%s\t%s\t%s\t%s\t%s\n' \
    "$cell_id" "$artifact_role" "$relative_path" "$bytes" "$sha256" > "$partial"
  mv "$partial" "$part"
  echo "DONE: $relative_path"
done

for index in "${!entries[@]}"; do
  part="$parts_dir/$(printf '%02d' "$index").tsv"
  [[ -s "$part" ]] || { echo "INCOMPLETE: $part" >&2; exit 2; }
done

final_partial="$final_manifest.partial.$$"
printf 'cell_id\tartifact_role\trelative_path\tsize_bytes\tsha256\n' > "$final_partial"
for index in "${!entries[@]}"; do
  tail -n +2 "$parts_dir/$(printf '%02d' "$index").tsv" >> "$final_partial"
done
mv "$final_partial" "$final_manifest"
echo "COMPLETE: $final_manifest"
