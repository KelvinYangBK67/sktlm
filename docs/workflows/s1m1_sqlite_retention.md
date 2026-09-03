# S1M1 selective SQLite retention

This workflow preserves scientifically non-redundant microscopic state after
the formal S1M1 analysis. It does not change that analysis. Run source-host
commands only after the researcher starts the required VM **and confirms that
the learner process has stopped and the database/WAL are quiescent**. Never run
the export while a learner, resume job, checkpoint process, or other writer can
still change either file. The SQLite-only export hashes the potentially large
database/WAL and may exceed five minutes; Codex must not run it automatically.

The exporter opens SQLite with `mode=ro` and `query_only`, performs no
checkpoint or journal-mode change, and refuses an existing output directory.
If `--wal` is omitted, WAL identity is resolved as `<database>-wal`. A missing
or empty WAL is recorded as `present: false` with null size and SHA-256.

## Exact exporter checkout and source isolation

Do not switch, pull, reset, clean, or otherwise modify the scientific source
checkout. Fetch the audited exporter commit and run it from a separate detached
worktree. Set `SKTLM_ARCHIVAL_EXPORT_COMMIT` to the exact 40-character commit
reported with this workflow revision:

```bash
export SKTLM_SCIENTIFIC_CHECKOUT='/absolute/path/to/scientific/source/checkout'
export SKTLM_EXPORT_WORKTREE='/absolute/path/to/sktlm-s1m1-archival-export'
export SKTLM_ARCHIVAL_OUTPUT_ROOT='/absolute/path/to/s1m1-archival-output'
export SKTLM_ARCHIVAL_EXPORT_COMMIT='<exact-40-character-archival-export-commit>'

git -C "$SKTLM_SCIENTIFIC_CHECKOUT" fetch origin exp/s1m1-core-methods
git -C "$SKTLM_SCIENTIFIC_CHECKOUT" cat-file -e "${SKTLM_ARCHIVAL_EXPORT_COMMIT}^{commit}"
test ! -e "$SKTLM_EXPORT_WORKTREE"
git -C "$SKTLM_SCIENTIFIC_CHECKOUT" worktree add --detach \
  "$SKTLM_EXPORT_WORKTREE" "$SKTLM_ARCHIVAL_EXPORT_COMMIT"
test "$(git -C "$SKTLM_EXPORT_WORKTREE" rev-parse HEAD)" = \
  "$SKTLM_ARCHIVAL_EXPORT_COMMIT"
test -z "$(git -C "$SKTLM_EXPORT_WORKTREE" status --porcelain)"
mkdir -p "$SKTLM_ARCHIVAL_OUTPUT_ROOT"
```

The fetch updates Git object/ref metadata only; it must not update the checked
out scientific files. Compact outputs go under `SKTLM_ARCHIVAL_OUTPUT_ROOT`,
not inside the scientific source checkout. The manifest fails closed if Git
provenance cannot be resolved and records the exact exporter commit, schema and
implementation-file hashes.

Artifact classifications use only `PENDING`, `RETAIN`,
`SAFE_TO_DELETE_REGENERABLE`, and `NOT_SAFE`. `NOT_READY` is reserved for the
overall deletion gate.

Every successful compact directory contains exactly:

```text
final_scorer.tsv.gz
surface_usage.tsv.gz
context_usage.tsv.gz
manifest.json
SHA256SUMS
```

## A. Devanagari `surface_word`

After independently confirming that the source learner has stopped, run on the
source host. The `pgrep`/`lsof` commands are inspection aids: do not continue if
they reveal the learner or any writer holding the DB/WAL.

```bash
sktlm_db="$SKTLM_SCIENTIFIC_CHECKOUT/artifacts/latent_benchmarks/cloud_full_m0_devanagari_surface_word_p10_w8_p3/learner.sqlite"
sktlm_out="$SKTLM_ARCHIVAL_OUTPUT_ROOT/devanagari__surface_word"

pgrep -af 'sktlm-train-latent-lexicon|latent_lexicon' || true
lsof -- "$sktlm_db" "${sktlm_db}-wal" || true
test -s "$sktlm_db"

stat --printf='%n\t%s bytes\n' "$sktlm_db"
if [ -s "${sktlm_db}-wal" ]; then
  stat --printf='%n\t%s bytes\n' "${sktlm_db}-wal"
else
  printf '%s\tabsent-or-empty\n' "${sktlm_db}-wal"
fi

PYTHONPATH="$SKTLM_EXPORT_WORKTREE/src" \
python3 "$SKTLM_EXPORT_WORKTREE/scripts/analysis/export_s1m1_sqlite_state.py" \
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
export SKTLM_REMOTE_SCIENTIFIC_CHECKOUT='/absolute/path/to/scientific/source/checkout'
export SKTLM_REMOTE_ARCHIVAL_OUTPUT='/absolute/path/to/s1m1-archival-output'
export SKTLM_REMOTE_DB_REL='artifacts/latent_benchmarks/cloud_full_m0_devanagari_surface_word_p10_w8_p3/learner.sqlite'
export SKTLM_ARCHIVAL_EXPORT_COMMIT='<same-exact-40-character-commit-used-on-source-host>'
mkdir -p artifacts/s1m1_final/retained/devanagari__surface_word/raw
mkdir -p artifacts/s1m1_final/retained/devanagari__surface_word/compact

rsync --archive --partial --progress \
  "$SKTLM_SOURCE_HOST:$SKTLM_REMOTE_SCIENTIFIC_CHECKOUT/$SKTLM_REMOTE_DB_REL" \
  artifacts/s1m1_final/retained/devanagari__surface_word/raw/

rsync --archive --partial --progress \
  "$SKTLM_SOURCE_HOST:$SKTLM_REMOTE_ARCHIVAL_OUTPUT/devanagari__surface_word/" \
  artifacts/s1m1_final/retained/devanagari__surface_word/compact/

(cd artifacts/s1m1_final/retained/devanagari__surface_word/compact && \
  sha256sum --check SHA256SUMS)
```

If the `manifest.json` `source_artifacts` entry whose `artifact_role` is
`learner_sqlite_wal` records `present: true`, also retrieve the WAL that was
hashed by the export:

```bash
rsync --archive --partial --progress \
  "$SKTLM_SOURCE_HOST:$SKTLM_REMOTE_SCIENTIFIC_CHECKOUT/${SKTLM_REMOTE_DB_REL}-wal" \
  artifacts/s1m1_final/retained/devanagari__surface_word/raw/
```

After the optional WAL retrieval, verify the returned raw source identities
against the compact manifest. This command also rejects an exporter commit
other than the exact detached-worktree commit selected above:

```bash
python3 - \
  artifacts/s1m1_final/retained/devanagari__surface_word/compact/manifest.json \
  artifacts/s1m1_final/retained/devanagari__surface_word/raw \
  "$SKTLM_ARCHIVAL_EXPORT_COMMIT" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
raw_root = pathlib.Path(sys.argv[2])
expected_commit = sys.argv[3]
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
actual_commit = manifest["exporter_provenance"]["git_commit_sha"]
if actual_commit != expected_commit:
    raise SystemExit(f"exporter commit mismatch: {actual_commit} != {expected_commit}")
artifacts = {item["artifact_role"]: item for item in manifest["source_artifacts"]}

for role, filename in (
    ("learner_sqlite", "learner.sqlite"),
    ("learner_sqlite_wal", "learner.sqlite-wal"),
):
    expected = artifacts[role]
    path = raw_root / filename
    if not expected["present"]:
        if path.exists() and path.stat().st_size:
            raise SystemExit(f"manifest records absent/empty but local file is non-empty: {path}")
        print(f"verified absent/empty: {role}")
        continue
    if not path.is_file():
        raise SystemExit(f"missing retained source artifact: {path}")
    size = path.stat().st_size
    if size != expected["size_bytes"]:
        raise SystemExit(f"size mismatch for {path}: {size} != {expected['size_bytes']}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    actual_sha = digest.hexdigest()
    if actual_sha != expected["sha256"]:
        raise SystemExit(f"SHA-256 mismatch for {path}: {actual_sha} != {expected['sha256']}")
    print(f"verified {role}: {size} bytes {actual_sha}")
PY
```

Return both the verified raw database/WAL set and the complete compact
directory.

## B. Devanagari `legacy_joined`

Again, proceed only after independently confirming that the source learner has
stopped and the DB/WAL are quiescent:

```bash
sktlm_db="$SKTLM_SCIENTIFIC_CHECKOUT/artifacts/latent_benchmarks/cloud_full_m0_devanagari_legacy_joined_p10_w8_p3/learner.sqlite"
sktlm_out="$SKTLM_ARCHIVAL_OUTPUT_ROOT/devanagari__legacy_joined"

pgrep -af 'sktlm-train-latent-lexicon|latent_lexicon' || true
lsof -- "$sktlm_db" "${sktlm_db}-wal" || true
test -s "$sktlm_db"

stat --printf='%n\t%s bytes\n' "$sktlm_db"
if [ -s "${sktlm_db}-wal" ]; then
  stat --printf='%n\t%s bytes\n' "${sktlm_db}-wal"
else
  printf '%s\tabsent-or-empty\n' "${sktlm_db}-wal"
fi

PYTHONPATH="$SKTLM_EXPORT_WORKTREE/src" \
python3 "$SKTLM_EXPORT_WORKTREE/scripts/analysis/export_s1m1_sqlite_state.py" \
  --cell-id devanagari__legacy_joined \
  --database "$sktlm_db" \
  --output-dir "$sktlm_out"

ls -lh "$sktlm_out"
python3 -m json.tool "$sktlm_out/manifest.json"
```

Retrieve only the compact association state:

```bash
export SKTLM_SOURCE_HOST='user@current-source-host'
export SKTLM_REMOTE_ARCHIVAL_OUTPUT='/absolute/path/to/s1m1-archival-output'
mkdir -p artifacts/s1m1_final/retained/devanagari__legacy_joined/compact

rsync --archive --partial --progress \
  "$SKTLM_SOURCE_HOST:$SKTLM_REMOTE_ARCHIVAL_OUTPUT/devanagari__legacy_joined/" \
  artifacts/s1m1_final/retained/devanagari__legacy_joined/compact/

(cd artifacts/s1m1_final/retained/devanagari__legacy_joined/compact && \
  sha256sum --check SHA256SUMS)
```

Do not retrieve the raw Devanagari `legacy_joined` database/WAL for permanent
retention. Its source identities remain recorded in the compact manifest so
deletion readiness can be assessed after return and validation. Codex never
performs deletion.
