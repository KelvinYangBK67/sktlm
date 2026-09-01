# Non-continuous representation checkpoint (2026-09-01)

## Status and scope

This report closes the completed **non-continuous 2×2 checkpoint** for the
unrestricted latent-lexicon condition:

| Script | Spacing condition | Run | Local benchmark source | Provenance commit |
|---|---|---|---|---|
| IAST | `surface_word` | `cloud_full_m0_iast_surface_word_p10_rep01_w8_p3` | `artifacts/cloud_scientific/cloud_full_m0_iast_surface_word_p10_rep01_w8_p3/benchmark/` | `cd3a092b116ad236c4ad96d7c24868e79e9a47ce` |
| IAST | `legacy_joined` | `cloud_full_m0_iast_legacy_joined_p10_w8_p3` | `artifacts/post_gate/collected/cloud_full_m0_iast_legacy_joined_p10_w8_p3/benchmark/` | `375178ba50bd1a1644d65525907692b31413b33d` |
| Devanagari | `surface_word` | `cloud_full_m0_devanagari_surface_word_p10_w8_p3` | `artifacts/post_gate/collected/cloud_full_m0_devanagari_surface_word_p10_w8_p3/benchmark/` | `375178ba50bd1a1644d65525907692b31413b33d` |
| Devanagari | `legacy_joined` | `cloud_full_m0_devanagari_legacy_joined_p10_w8_p3` | `artifacts/post_gate/collected/cloud_full_m0_devanagari_legacy_joined_p10_w8_p3/benchmark/` | `375178ba50bd1a1644d65525907692b31413b33d` |

All four provenance records name the same frozen M₀ freeze ID
`9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`,
the same 240-document manifest SHA-256
`c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520`,
and the same 1,218-rule inventory SHA-256
`55a204169a1ec442e8ac6e9ca90da1e6510b24998cdeba2d76f95f513bab7e90`.
The quantitative results below were established from the completed runs and
cross-checked against their small `summary.json`, `iteration_metrics.json`,
and `rule_usage.tsv` evidence. No large scientific artifact was re-audited or
re-hashed for this report.

The continuous cells are not part of this checkpoint. Their completion is
still required before the six-cell gate can be closed, so this report is not a
final M1 conclusion.

## Quantitative result

### Script effect within `surface_word`

IAST to Devanagari gives **exact scientific equivalence except raw character
count**. Of 26 common numeric summary fields, 25 are exactly equal. The sole
change is `characters`, from 53,233,989 to 48,678,812 (-8.556896%). Rule TV and
JSD are both 0, and top-20 rule overlap is 20/20. Across the three passes, 42 of
45 numeric fields are exactly equal; the only changed field in each pass is
`characters`.

### Script effect within `legacy_joined`

This pair shows near-equivalence, not exact equality:

| Metric, IAST → Devanagari | Relative change |
|---|---:|
| characters | -9.843212% |
| candidate edges | -0.008110% |
| candidate factors | +0.001413% |
| candidate nodes | -0.003335% |
| active lexical types | +0.002094% |
| low-count types | +0.002095% |
| expected lexical tokens | +0.001690% |
| mean identity mass | -0.000293% |
| mean entropy | +0.004974% |
| mean top-1 posterior | -0.000780% |

Rule TV is `1.3080489453873241e-05`; JSD is
`2.339464786880391e-06` nats; top-20 overlap is 20/20. These residuals support
a negligible script effect in this condition, but they must not be described
as exact equality.

### Spacing effect within each script

| Metric, `surface_word` → `legacy_joined` | IAST | Devanagari | DEV delta minus IAST delta (percentage points) |
|---|---:|---:|---:|
| active lexical types | +36.227805% | +36.230658% | +0.002853 |
| low-count types | +36.703865% | +36.706730% | +0.002864 |
| expected lexical tokens | -21.335704% | -21.334375% | +0.001329 |
| mean identity mass | +25.133947% | +25.133580% | -0.000367 |
| mean latent mass | -4.320038% | -4.319975% | +0.000063 |
| mean entropy | -19.545603% | -19.541601% | +0.004002 |
| mean top-1 posterior | +5.036431% | +5.035612% | -0.000819 |
| rule expected usage | -28.788099% | -28.787904% | +0.000195 |
| candidate edges | +15.996962% | +15.987554% | -0.009407 |
| candidate factors | -21.379752% | -21.378641% | +0.001111 |
| candidate nodes | -6.471913% | -6.475032% | -0.003119 |

For IAST, rule TV is `0.190596533420812`, JSD is
`0.0697227649014552` nats, and top-20 overlap is 16/20. For Devanagari, the
corresponding values are `0.19058822550539367`,
`0.06971220943933126` nats, and 16/20.

The spacing effect is therefore much larger than the script effect, and it
reappears at nearly the same magnitude in both scripts.

## Interpretation

`legacy_joined` produces a sharper posterior: entropy falls by about 19.5%,
mean top-1 posterior rises by about 5.0%, and identity mass rises by about
25.1%. Those changes are not, by themselves, evidence of a better lexical
analysis. Lexical economy moves in the opposite direction: active types rise
by about 36.2%, low-count types by about 36.7%, while expected lexical-token
count falls by about 21.3%.

The joint pattern is consistent with direct lexicalization of
context-specific chunks spanning former surface-word boundaries. Such chunks
can make a local posterior more confident while reducing reuse across
contexts, inflating the lexicon, and worsening its long tail. The roughly
28.8% reduction in expected sandhi-rule usage and the substantial change in
its distribution are also compatible with some strings that previously
required lexical decomposition plus external realization becoming directly
lexicalized.

The qualitative evidence below adds an important qualification: over-long
lexicalization is already visible under `surface_word`; `legacy_joined`
amplifies it by removing boundary evidence. The observed behavior therefore
cannot be reduced to representation degradation alone. It is evidence of a
latent-lexicon/objective-level tendency toward over-long lexical identities
under the present compression pressure. This is an interpretation of model
outputs, not a claim that the learner understands sandhi or morphology.

## Qualitative illustrations

These five examples are illustrations, not a statistical estimate. The first
is the pre-specified anchor. The other four were selected by
`scripts/analysis/noncontinuous_qualitative_examples.py`, which performs a
bounded streaming merge-join over the two Devanagari `analyses.jsonl` files,
requires the stated boundary/unit/identity criteria, excludes the anchor and
duplicate surface-text pairs, and ranks by identity-mass increase, top-1 unit
reduction, then `segment_id`. It stopped deterministically after 64 distinct
qualified candidates: 132 matched records, 1,665,170 surface bytes, and
1,343,510 legacy bytes. The full files were not scanned.

### 1. Pre-specified anchor: line 1

- Document: `1_veda/2_bra/gopbra_u.txt`
- Segment: `1_veda:2_bra:gopbra_u.txt:l00000001:s0000`
- `surface_word`: `ॐ नमो ऽथर्ववेदाय नमः`
- `legacy_joined`: `ॐ नमोऽथर्ववेदाय नमः`

| Condition | identity mass | latent mass | entropy |
|---|---:|---:|---:|
| `surface_word` | 0.000771 | 0.999229 | 0.883652 |
| `legacy_joined` | 0.719938 | 0.280062 | 0.596304 |

`surface_word` top analyses:

1. `p=0.553758` — `oṃ | namaḥ | atharvavedāya | namaḥ` — `EXT_0805, EXT_0033`
2. `p=0.396730` — `om | namaḥ | atharvavedāya | namaḥ` — `EXT_0795, EXT_0805, EXT_0033`
3. `p=0.028003` — `oṃ | namo | atharvavedāya | namaḥ` — `EXT_0421, EXT_0033`

`legacy_joined` top analyses:

1. `p=0.719938` — `oṃ | namotharvavedāya | namaḥ` — `EXT_0033`
2. `p=0.279668` — `om | namotharvavedāya | namaḥ` — `EXT_0795, EXT_0033`
3. `p=0.000272` — `oṃ | namaḥ | atharvavedāya | namaḥ` — `EXT_0805, EXT_0033`

The fourth legacy path, `om | namaḥ | atharvavedāya | namaḥ`, has only
`p=0.000106`. In this segment, `surface_word` strongly favors lexical
decomposition plus external realization, whereas `legacy_joined` assigns
nearly all mass to the longer `namotharvavedāya` identity.

### 2. Line 11

- Document: `1_veda/2_bra/gopbra_u.txt`
- Segment: `1_veda:2_bra:gopbra_u.txt:l00000011:s0000`
- `surface_word`: `तद् अभ्यस्राम्यद् अभ्यतपत् समतपत्`
- `legacy_joined`: `तदभ्यस्राम्यदभ्यतपत्समतपत्`

| Condition | identity mass | latent mass | entropy |
|---|---:|---:|---:|
| `surface_word` | 0.000003672 | 0.999996328 | 0.344416 |
| `legacy_joined` | 0.999999990 | 0.000000010 | 0.000000225 |

`surface_word` top analyses:

1. `p=0.896647` — `tat | abhyasrāmyadabhyatapat | samatapat` — `EXT_0591, EXT_0632`
2. `p=0.101467` — `tad | abhyasrāmyadabhyatapat | samatapat` — `EXT_0632`
3. `p=0.000771` — `tat | abhyasrāmyad | abhyatapatsamatapat` — `EXT_0591`

`legacy_joined` top analyses:

1. `p=0.999999990` — `tadabhyasrāmyadabhyatapatsamatapat` — no rule
2. `p=8.60e-10` — `tadabhi | asrāmyadabhyatapatsamatapat` — `EXT_0085`
3. `p=8.57e-10` — `tadabhī | asrāmyadabhyatapatsamatapat` — `EXT_0127`

Even the `surface_word` top path over-merges `abhyasrāmyad + abhyatapat`;
`legacy_joined` extends the same tendency to the entire surface string and
makes it effectively certain.

### 3. Line 215

- Document: `1_veda/2_bra/gopbra_u.txt`
- Segment: `1_veda:2_bra:gopbra_u.txt:l00000215:s0000`
- `surface_word`: `यच् च वृत्वातिष्ठंस् तद् वरणो ऽभवत्`
- `legacy_joined`: `यच्च वृत्वातिष्ठंस्तद्वरणोऽभवत्`

| Condition | identity mass | latent mass | entropy |
|---|---:|---:|---:|
| `surface_word` | 0.000007829 | 0.999992171 | 1.912719 |
| `legacy_joined` | 0.999999464 | 0.000000536 | 0.000008735 |

`surface_word` top analyses:

1. `p=0.379310` — `yat | ca | vṛtvātiṣṭhan | tat | varaṇo | abhavat` — `EXT_0607, EXT_0038, EXT_0743, EXT_0628, EXT_0421`
2. `p=0.259625` — `yat | ca | vṛtvātiṣṭhaṃs | tat | varaṇo | abhavat` — `EXT_0607, EXT_0038, EXT_0628, EXT_0421`
3. `p=0.101122` — `yat | ca | vṛtvātiṣṭhan | tat | varaṇaḥ | abhavat` — `EXT_0607, EXT_0038, EXT_0743, EXT_0628, EXT_0805`

`legacy_joined` top analyses:

1. `p=0.999999464` — `yacca | vṛtvātiṣṭhaṃstadvaraṇobhavat` — `EXT_0038`
2. `p=2.57e-7` — `yacca | vṛtvātiṣṭhaṃstadvaraṇaḥ | abhavat` — `EXT_0038, EXT_0805`
3. `p=2.57e-7` — `yacca | vṛtvātiṣṭhaṃstadvaraṇo | abhavat` — `EXT_0038, EXT_0421`

Here the legacy path collapses six top-1 units to two. The output is a direct
observation of longer lexical identities; any linguistic account of their
internal structure remains external interpretation.

### 4. Line 85

- Document: `1_veda/2_bra/gopbra_u.txt`
- Segment: `1_veda:2_bra:gopbra_u.txt:l00000085:s0000`
- `surface_word`: `तास् तत्रैवाभ्यस्राम्यद् अभ्यतपत् समतपत्`
- `legacy_joined`: `तास्तत्रैवाभ्यस्राम्यदभ्यतपत्समतपत्`

| Condition | identity mass | latent mass | entropy |
|---|---:|---:|---:|
| `surface_word` | 0.000000884 | 0.999999116 | 0.136221 |
| `legacy_joined` | 0.999988639 | 0.000011361 | 0.000154140 |

`surface_word` top analyses:

1. `p=0.978792` — `tāḥ | tatraivābhyasrāmyadabhyatapat | samatapat` — `EXT_0871, EXT_0632`
2. `p=0.009116` — `tās | tatraivābhyasrāmyadabhyatapat | samatapat` — `EXT_0632`
3. `p=0.003510` — `tāstatraivābhyasrāmyad | abhyatapatsamatapat` — no rule

`legacy_joined` top analyses:

1. `p=0.999989` — `tāstatraivābhyasrāmyadabhyatapatsamatapat` — no rule
2. `p=4.64e-6` — `tā | astatraivābhyasrāmyadabhyatapatsamatapat` — `EXT_0043`
3. `p=4.64e-6` — `tā | āstatraivābhyasrāmyadabhyatapatsamatapat` — `EXT_0044`

The same qualitative transition appears: a surface condition that already
contains a long middle identity becomes an almost-certain whole-string
identity after joining.

### 5. Line 239

- Document: `1_veda/2_bra/gopbra_u.txt`
- Segment: `1_veda:2_bra:gopbra_u.txt:l00000239:s0000`
- `surface_word`: `तम् अङ्गिरसम् ऋषिम् अभ्यस्राम्यद् अभ्यतपत् समतपत्`
- `legacy_joined`: `तमङ्गिरसमृषिमभ्यस्राम्यदभ्यतपत्समतपत्`

| Condition | identity mass | latent mass | entropy |
|---|---:|---:|---:|
| `surface_word` | 0.000015100 | 0.999984900 | 0.763724 |
| `legacy_joined` | 0.999999988 | 0.000000012 | 0.000000262 |

`surface_word` top analyses:

1. `p=0.569361` — `tam | aṅgirasamṛṣim | abhyasrāmyadabhyatapat | samatapat` — `EXT_0763, EXT_0763, EXT_0632`
2. `p=0.417283` — `tam | aṅgirasam | ṛṣim | abhyasrāmyadabhyatapat | samatapat` — `EXT_0763, EXT_0769, EXT_0763, EXT_0632`
3. `p=0.005068` — `tam | aṅgirasam | ṛṣimabhyasrāmyad | abhyatapatsamatapat` — `EXT_0763, EXT_0769`

`legacy_joined` top analyses:

1. `p=0.999999988` — `tamaṅgirasamṛṣimabhyasrāmyadabhyatapatsamatapat` — no rule
2. `p=8.57e-10` — `tamaṅgirasamṛṣimabhyasra | āmyadabhyatapatsamatapat` — `EXT_0002`
3. `p=8.57e-10` — `tamaṅgirasamṛṣimabhyasrā | āmyadabhyatapatsamatapat` — `EXT_0044`

The `surface_word` posterior itself weighs an over-long
`aṅgirasamṛṣim` identity; joining pushes the result to one nearly deterministic
whole-string identity. This again separates the underlying learner tendency
from the degree to which the representation amplifies it.

## Additional inspected failure-mode evidence

The following already-inspected Devanagari outputs are not extra selector
ranks and are not used as quantitative estimates. They sharpen the same
failure-mode interpretation:

- `bhṛgvaṅgirovidāsaṃskṛto | anyān | vedān | adhīyīta` contains an over-merged
  span across `vidā + saṃskṛto`. The observed decoded unit does not recover the
  expected underlying distinction; that linguistic comparison is an analyst's
  interpretation, not a structure represented by the model.
- `tasmāt | ṛgyajuḥsāmānyapakrāntatejāṃsy | āsan` lexicalizes a long surface
  sequence. It retains the surface `y`; there is no evidence in this output of
  a deeper alternation being abstracted.
- `tat | vācy | upalakṣayedvarṇākṣarapadāṅkasaḥ` likewise retains surface `y`
  specifically in `vācy`. The possible underlying relationship `vāc + i` is
  not abstracted. This observation concerns `vācy`, not `upalakṣayed`.
- `tat | abhyasrāmyadabhyatapat | samatapat` over-merges
  `abhyasrāmyad + abhyatapat`, as the detailed line-11 illustration also
  records.

These are natural failure modes for a low-supervision latent lexical learner.
They motivate later objectives that reward abstraction and reuse; they do not
motivate Sanskrit-specific hard constraints. In particular, this checkpoint
does **not** recommend manual sandhi constraints, avagraha rules, morphology
rules, or hard whitespace boundaries. M1 should expose what the learner
actually discovers and where it fails. Later stages should improve abstraction
through objective design rather than injected linguistic supervision.

## Checkpoint decision

The non-continuous evidence establishes two results for subsequent M1 work:

1. script choice has no material scientific effect in `surface_word` and only a
   negligible effect in `legacy_joined`;
2. spacing has a large, reproducible effect, and `legacy_joined` amplifies an
   objective-level over-long lexicalization failure mode already present under
   `surface_word`.

This checkpoint intentionally makes no six-cell or final-M1 selection. The
continuous evidence must be completed and evaluated under the frozen
post-gate protocol before that decision.