# S1M1 selective SQLite retention

This workflow preserves scientifically non-redundant microscopic state after
the formal S1M1 analysis. It does not change that analysis. Run source-host
commands only after the researcher starts the required VM. The SQLite-only
export hashes the potentially large database/WAL and may exceed five minutes;
Codex must not run it automatically.

The exporter opens SQLite with `mode=ro` and `query_only`, performs no
checkpoint or journal-mode change, and refuses an existing output directory.
If `--wal` is omitted, WAL identity is resolved as `<database>-wal`. A missing
or empty WAL is recorded as `present: false` with null size and SHA-256.

Every successful compact directory contains exactly:

```text
final_scorer.tsv.gz
surface_usage.tsv.gz
context_usage.tsv.gz
manifest.json
SHA256SUMS
```

## A. Devanagari `surface_word`

Run on the source host from the repository root:

```bash
sktlm_db='artifacts/latent_benchmarks/cloud_full_m0_devanagari_surface_word_p10_w8_p3/learner.sqlite'
sktlm_out='artifacts/s1m1_final/sqlite_state/devanagari__surface_word'

stat --printf='%n\t%s bytes\n' "$sktlm_db"
if [ -s "${sktlm_db}-wal" ]; then
  stat --printf='%n\t%s bytes\n' "${sktlm_db}-wal"
else
  printf '%s\tabsent-or-empty\n' "${sktlm_db}-wal"
fi

PYTHONPATH="$PWD/src" python3 scripts/analysis/export_s1m1_sqlite_state.py \
  --cell-id devanagari__surface_word \
  --database "$sktlm_db" \
  --output-dir "$sktlm_out"

ls -lh "$sktlm_out"
python3 -m json.tool "$sktlm_out/manifest.json"
```

Set current connection values on the local receiving host; do not reuse an
unverified historical address:

```bash
export SKTLM_SOURCE_HOST='user@current-source-host'
export SKTLM_REMOTE_REPO='/absolute/path/to/skt-tokenizer'
export SKTLM_REMOTE_DB_REL='artifacts/latent_benchmarks/cloud_full_m0_devanagari_surface_word_p10_w8_p3/learner.sqlite'
export SKTLM_REMOTE_COMPACT_REL='artifacts/s1m1_final/sqlite_state/devanagari__surface_word'
mkdir -p artifacts/s1m1_final/retained/devanagari__surface_word/raw
mkdir -p artifacts/s1m1_final/retained/devanagari__surface_word/compact

rsync --archive --partial --progress \
  "$SKTLM_SOURCE_HOST:$SKTLM_REMOTE_REPO/$SKTLM_REMOTE_DB_REL" \
  artifacts/s1m1_final/retained/devanagari__surface_word/raw/

rsync --archive --partial --progress \
  "$SKTLM_SOURCE_HOST:$SKTLM_REMOTE_REPO/$SKTLM_REMOTE_COMPACT_REL/" \
  artifacts/s1m1_final/retained/devanagari__surface_word/compact/
```

If the `manifest.json` `source_artifacts` entry whose `artifact_role` is
`learner_sqlite_wal` records `present: true`, also retrieve the WAL that was
hashed by the export:

```bash
rsync --archive --partial --progress \
  "$SKTLM_SOURCE_HOST:$SKTLM_REMOTE_REPO/${SKTLM_REMOTE_DB_REL}-wal" \
  artifacts/s1m1_final/retained/devanagari__surface_word/raw/
```

Return both the raw database/WAL set and the complete compact directory.

## B. Devanagari `legacy_joined`

Run on the source host from the repository root:

```bash
sktlm_db='artifacts/latent_benchmarks/cloud_full_m0_devanagari_legacy_joined_p10_w8_p3/learner.sqlite'
sktlm_out='artifacts/s1m1_final/sqlite_state/devanagari__legacy_joined'

stat --printf='%n\t%s bytes\n' "$sktlm_db"
if [ -s "${sktlm_db}-wal" ]; then
  stat --printf='%n\t%s bytes\n' "${sktlm_db}-wal"
else
  printf '%s\tabsent-or-empty\n' "${sktlm_db}-wal"
fi

PYTHONPATH="$PWD/src" python3 scripts/analysis/export_s1m1_sqlite_state.py \
  --cell-id devanagari__legacy_joined \
  --database "$sktlm_db" \
  --output-dir "$sktlm_out"

ls -lh "$sktlm_out"
python3 -m json.tool "$sktlm_out/manifest.json"
```

Retrieve only the compact association state:

```bash
export SKTLM_SOURCE_HOST='user@current-source-host'
export SKTLM_REMOTE_REPO='/absolute/path/to/skt-tokenizer'
export SKTLM_REMOTE_COMPACT_REL='artifacts/s1m1_final/sqlite_state/devanagari__legacy_joined'
mkdir -p artifacts/s1m1_final/retained/devanagari__legacy_joined/compact

rsync --archive --partial --progress \
  "$SKTLM_SOURCE_HOST:$SKTLM_REMOTE_REPO/$SKTLM_REMOTE_COMPACT_REL/" \
  artifacts/s1m1_final/retained/devanagari__legacy_joined/compact/
```

Do not retrieve the raw Devanagari `legacy_joined` database/WAL for permanent
retention. Its source identities remain recorded in the compact manifest so
deletion readiness can be assessed after return and validation. Codex never
performs deletion.
