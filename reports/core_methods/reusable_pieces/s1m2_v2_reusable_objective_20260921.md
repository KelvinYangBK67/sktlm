# S1M2 V2 cross-host reusable-count objective

Date: 2026-09-21
Status: implemented; focused deterministic validation only

The historical `S1M2_REUSABLE_PIECES_V1` (`reusable_pieces_v1`) is the
raw-expected-count, whole-form-collapse baseline documented in
`s1m2_full_m0_scientific_failure_20260915.md`. The earlier candidate repair
in `s1m2_v2_semantic_repair_20260916.md` retained that scorer and the old model
label. `S1M2_REUSABLE_PIECES_V2` (`reusable_pieces_v2`) now replaces its learned
objective. Historical V1 checkpoint state is not a V2 starting point.

For phonological piece form `q` and stable lexical host type `h`, the exact
outer/inner posterior accumulator retains:

```text
S(q,h) = sum over host occurrences and derivations
         outer posterior mass(host occurrence)
         * conditional inner expected usage(q | h)
C(q) = sum_h S(q,h)
M(q) = max_h S(q,h)
R(q) = C(q) - M(q)
```

Legal membership alone contributes zero support. The learned reusable
parameter is keyed solely by the script-neutral phonological form `q`.
`WHOLE`, `LEFT`, `RIGHT`, and `INTERNAL` remain edge roles for legal paths,
exact posterior diagnostics, and references. Role-bearing posterior counts
are summed into the same form key when reducing learned state. Within
floating-point tolerance, the form-collapsed host support sums to the
form-collapsed ordinary posterior expected count.

At each completed pass, `piece_lexicon` stores `raw_expected_count` (`C`),
`max_host_expected_usage` (`M`), and `reusable_count` (`R`) for every observed
piece form, including forms with `R=0`. The table is finalized in place.
The scorer reads only `reusable_count`; its denominator is `sum_q R(q)+alpha`.
Its score is:

```text
log((R(q) + alpha*H(q))/(sum_q R(q)+alpha))
  - lambda*(kappa+beta*len(q))*log(1+1/(tau+R(q)))
```

The base measure `H` and all hyperparameters retain their declared values.
No host-conditioned score or binary host-diversity gate enters this equation.
The old host threshold fields remain temporarily in training config only for
inspection host-type diagnostics and compatibility with that diagnostic
output; they do not select or weight learned V2 parameters.

Whole-form segmentation, including the long whole-form fallback past
`max_piece_length`, remains legal. A form repeatedly used inside only its own
lexical host has `C=M`, hence `R=0`; the base measure and segmentation prior
can still favor its whole path. The observed-whitespace fence, visible and
internal joined-sandhi inversions, transformed-event charge, frozen grammar,
and exact compact/shared/reference inference routes remain in place.

The model label is in `TrainingConfig.payload()`, its signature, checkpoint
metadata, and run provenance. V1 config is rejected by the V2 trainer, and the
V2 SQLite scorer rejects the V1 piece schema. Formal corpus/freeze and
representation identity are separate and unchanged. Existing V1 production
contracts, benchmark specifications, and historical artifacts have not been
rewritten as V2 contracts; a new contract/qualification cycle is a separate
follow-up before production use.
The tracked `s1m2_lexeme_evidence_probe.yaml` is a historical V1 pilot
specification and is not a V2 experiment authorization.

Focused local tests exercise self repetition, cross-host growth, 1000/1
dominance, role collapse, conservation, scorer use of `R`, SQLite C/M/R,
whole fallback, and retained candidate/inference semantics. No corpus-scale
success is claimed. The next scientific gate is a bounded local DCS
experiment selected by the researcher. No Full M0, VM, representative/stress
corpus, or long benchmark was run for this implementation.
