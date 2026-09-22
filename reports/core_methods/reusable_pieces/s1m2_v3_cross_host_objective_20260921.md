# S1M2 V3 symmetric cross-host reusable objective

Date: 2026-09-21; qualification addendum 2026-09-22
Status: pre-freeze qualification complete; pending researcher scientific freeze decision

## Qualification addendum

The bounded E000/E100 gates below were subsequently run under the exact V3
identity and passed the read-only pre-freeze forensic audit. The authoritative
qualification evidence, occurrence-paired analysis, selection provenance,
production-contract closure, and S2/S3 host invariant are in
`s1m2_v3_prefreeze_forensic_audit_20260922.md` and its machine-readable
evidence manifest. V3 remains pending the researcher's scientific freeze
decision; it is not declared frozen here.

## Versioned scientific contract

- V1 (`reusable_pieces_v1`) is the historical raw-count whole-form-collapse
  state.
- V2 (`reusable_pieces_v2`) is the strongest-host deletion baseline with
  `R=C-M`.
- V3 (`reusable_pieces_v3`) is the symmetric cross-host corroboration
  objective described below.

V1 and V2 state are not reinterpreted as V3. V3 has a distinct training
configuration signature, explicit SQLite objective identity, state layout,
and scorer admission check.

For a script-neutral phonological piece form `q` and latent phonological
wordform host type `h`:

```text
S(q,h) = posterior expected usage of q under host wordform type h
C(q)   = sum_h S(q,h)
Q(q)   = sum_h S(q,h)^2
M(q)   = max_h S(q,h)                         # diagnostic only
R_cross(q) = 0                                if C(q)=0
R_cross(q) = C(q) - Q(q)/C(q)                 otherwise
```

`Q` is computed after all occurrences sharing `(q,h)` have been aggregated in
the disk-backed host-support table. It is not a sum of squared occurrence
support. Pass finalization stores `C`, `Q`, `M`, and `R_cross` in the V3
`piece_lexicon`. Both probability and reweighted-MDL complexity read only
`reusable_count=R_cross`; `Q` and `M` do not enter scoring. The V2 alpha, base
measure, kappa, beta, tau, and whole-form legality are unchanged.

The scientific interpretation is limited to cross-wordform corroboration. It
is not a morphological truth estimator.

## Host and piece identity

`host` means one latent phonological wordform type. It is not a lemma, lexeme,
DCS LemmaId, surface spelling, or occurrence identity. Repeated occurrences
of the same phonological wordform aggregate into one host; different latent
wordforms remain distinct. DCS gold is used only by held-out diagnostics.

Learned piece identity remains the script-neutral phonological form alone.
`WHOLE`, `LEFT`, `RIGHT`, and `INTERNAL` remain lattice structure and
diagnostic metadata. The V3 scorer is roleless.

## Bounded role-source shadow diagnostic

The diagnostic probe can enable `piece_role_diagnostics`. Existing exact
inference already emits role-bearing `PieceIdentity`, so the optional path
streams aggregate `S(q,h,r)` into a crash-safe disk-backed table without
retaining occurrence histories or lattices. At pass finalization it reduces
that table to compact per-piece/per-role state:

```text
C_r(q) = sum_h S(q,h,r)
Q_r(q) = sum_h S(q,h,r)^2
R_r(q) = C_r(q) - Q_r(q)/C_r(q), or zero when C_r(q)=0
R_role_separated(q) = sum_r R_r(q)
role_pooling_gain(q) = R_cross(q) - R_role_separated(q)
```

The read-only evaluator reports the top 100 pieces by pooled `R_cross`, role
raw usage and share, role entropy/effective role count, the role-separated
shadow value, and pooling gain. These are descriptive quantities with no
good/bad threshold. The compact role table is diagnostic state, not a learned
parameter, and is never read by the scorer. Collection is off by default and
does not change learned state.

## Held-out diagnostics

V3 uses new v4 artifacts and never overwrites the published V2 v3 artifacts.

- Diagnostic #3 retains the held-out top-1 descriptive wrong-host audit and
  attaches final V3 `C/Q/M/R_cross`. A coalition candidate appears in at least
  two distinct wrong predicted wordform hosts and has `R_cross>0`. This is not
  evidence that those held-out hosts caused training reuse.
- Diagnostic #4 reads the bounded final training role shadow above.
- Diagnostic #5 retains exact canonical DCS `Unsandhied` membership in the
  authoritative selected-training inventory. Lemma identity, predicted
  training hosts, surface spelling, substrings, and segmentation do not affect
  seen/unseen membership. Overall, seen, and unseen denominators retain their
  V2 definitions.

This implementation section does not restate the later V3 E000/E100 result;
the qualification addendum points to its authoritative report.

## Historical qualified run commands

Run E000 V3 training:

```powershell
python -m sktlm.experiments.training.s1m2_lexeme_probe --model reusable_pieces_v3 --corpus data/diagnostics/s1m2_lexeme_probe/controlled/noun_high_deva/E000/corpus.txt --challenge data/diagnostics/s1m2_lexeme_probe/controlled/noun_high_deva/challenge.jsonl --target-id noun_high_deva --level E000 --output-root artifacts/diagnostics/s1m2_lexeme_probe --run-id noun_high_deva_E000_v3 --passes 3 --workers 1 --sandhi-transformation-penalty 1.0 --piece-boundary-probability 0.4
```

Run E000 diagnostics #3/#4/#5:

```powershell
python -m sktlm.experiments.training.s1m2_semantic_diagnostics --run-dir artifacts/diagnostics/s1m2_lexeme_probe/noun_high_deva_E000_v3 --training-selection data/diagnostics/s1m2_lexeme_probe/controlled/background_1000.jsonl --training-gold-sidecar data/diagnostics/s1m2_lexeme_probe/controlled/noun_high_deva/E000/training_gold_wordforms.v1.json
```

Run E100 V3 training:

```powershell
python -m sktlm.experiments.training.s1m2_lexeme_probe --model reusable_pieces_v3 --corpus data/diagnostics/s1m2_lexeme_probe/controlled/noun_high_deva/E100/corpus.txt --challenge data/diagnostics/s1m2_lexeme_probe/controlled/noun_high_deva/challenge.jsonl --target-id noun_high_deva --level E100 --output-root artifacts/diagnostics/s1m2_lexeme_probe --run-id noun_high_deva_E100_v3 --passes 3 --workers 1 --sandhi-transformation-penalty 1.0 --piece-boundary-probability 0.4
```

Build the exact E100 selection from its 100 target rows and the controlled
background pool, writing only inside the new run directory:

```powershell
python -c "import collections,json,pathlib; r=pathlib.Path('data/diagnostics/s1m2_lexeme_probe/controlled'); c=(r/'noun_high_deva/E100/corpus.txt').read_text(encoding='utf-8').splitlines(); p=[]; [p.extend(json.loads(x) for x in f.read_text(encoding='utf-8').splitlines() if x.strip()) for f in (r/'noun_high_deva/E100/target_evidence.jsonl',r/'background_1000.jsonl')]; q=collections.defaultdict(collections.deque); [q[x['text']].append(x) for x in p]; s=[q[x].popleft() for x in c]; o=pathlib.Path('artifacts/diagnostics/s1m2_lexeme_probe/noun_high_deva_E100_v3/training_selection.v1.jsonl'); o.write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in s),encoding='utf-8',newline='\n')"
```

Run E100 diagnostics #3/#4/#5:

```powershell
python -m sktlm.experiments.training.s1m2_semantic_diagnostics --run-dir artifacts/diagnostics/s1m2_lexeme_probe/noun_high_deva_E100_v3 --training-selection artifacts/diagnostics/s1m2_lexeme_probe/noun_high_deva_E100_v3/training_selection.v1.jsonl --training-gold-sidecar artifacts/diagnostics/s1m2_lexeme_probe/noun_high_deva_E100_v3/training_gold_wordforms.v1.json
```

These commands produced the later qualified artifacts. They are recorded for
provenance and must not be rerun automatically.
