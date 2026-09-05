# M0-prime formal substrate checkpoint

Date: 2026-09-05

```text
M0_PRIME_GENERATION=COMPLETE
M0_PRIME_VALIDATION=VALID
DOWNSTREAM_SUBSTRATE=AVAILABLE
```

## Identity and provenance

The formal derivation `m0-prime-iast-continuous-v1` ran once as the detached
Windows Scheduled Task `sktlm-m0-prime-iast-continuous-v1`. Generation began
at `2026-09-05T02:00:00.8320745+02:00` and generation plus validation finished
at `2026-09-05T02:22:01.7800953+02:00`; both commands exited zero and Task
Scheduler recorded result zero.

The clean committed implementation identity was:

```text
Git commit: e7f5b7d8e57b81868c97000b3058347160030df2
implementation: sktlm.representations.m0_prime
implementation file SHA-256:
  9e3eb0705aac2c0f5164d79f7129188f289ba7e9e115094581ab6bcf62b33406
config SHA-256:
  648a0f68f3ad4dfcb057ca06b93d960a1cb1105844667c54144d28c7c9860478
output manifest SHA-256:
  3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922
```

The only source was frozen M0 Devanagari `continuous`:

```text
freeze ID:
  9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40
representation manifest SHA-256:
  c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520
canonical manifest SHA-256:
  ccec95eedc9ab37634d24d7d8fa2c47fc3189c3960b07cceb87fd48417ab3cb5
```

Frozen M0, its manifests, representations, freeze metadata, and tag were not
modified.

## Formal totals

| Quantity | Value |
|---|---:|
| documents / output files | 240 |
| source bytes | 134,379,881 |
| output bytes | 64,932,981 |
| output characters | 51,409,280 |
| output lines | 2,107,648 |
| script-neutral phonemes | 46,255,133 |
| lexical `/ai/` (`ē`) | 276,978 |
| lexical `/au/` (`ō`) | 116,388 |
| separate `a+i` (`ai`) | 25,078 |
| separate `a+u` (`au`) | 23,397 |
| lexical aspirated consonants (`ʰ`) | 1,558,270 |
| plain consonant+`h` sequences | 423 |

## Validation

The formal validator returned `VALID`. It verified exact source-manifest and
canonical-manifest identity, all 240 source hashes, document membership,
document IDs and splits, ordered relative paths, all output hashes,
line/whitespace preservation, deterministic regeneration, allowed output
representation, lexical-diphthong/hiatus and aspirate/cluster distinctions,
and exact equality of source/output script-neutral phoneme sequences.

The compact artifact checksum set was independently checked after the detached
job and all four entries passed:

```text
f3883cc1b58241ac224782d96e5d08f26e87f4f5155ffe1d8cb661a62a50f746  config.snapshot.json
871783d7c3c80761a1e1e7d77f47169ed640ef300a54d96ae1d4eb7f446886d1  generation.json
3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922  manifest.csv
d872826e31f82954f9718e04413cfb5854a4215b2435f390e9ce3a0c739e9a2a  validation.json
```

The generated text and formal artifacts remain ignored data under
`data/derived/m0_prime/iast/continuous/` and
`artifacts/m0_prime/m0_prime_iast_continuous_v1/`. The manifest is the durable
downstream interface; this tracked checkpoint records its identity without
placing generated payloads under Git.

## Downstream contract

The corrected six-cell substrate for downstream work is:

```text
M0 IAST:        surface_word, legacy_joined
M0 Devanagari:  surface_word, legacy_joined, continuous
M0-prime IAST:  continuous (script id iast_m0_prime)
```

Original M0 IAST `continuous` remains `NA_SCIENTIFICALLY_EXCLUDED`; M0-prime
does not overwrite or retroactively relabel it. This checkpoint establishes a
validated substrate interface, not an S1M2 scientific result and not authority
to launch an S1M2 full-corpus experiment.
