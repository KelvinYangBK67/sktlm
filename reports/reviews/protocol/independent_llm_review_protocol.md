# Independent LLM review protocol

Status: **workflow frozen; no reviewer has been invoked**.

The researcher-authored sources of truth are:

- `notes/reviewer/reviewer_prompt.txt` — 10,258 bytes, SHA-256
  `d5efc209de1f3a6dbf76726ecbd638d08acc91c98bf9c5ec2058fa00af27d0a1`;
- `notes/reviewer/method.txt` — 4,267 bytes, SHA-256
  `f7bcf017be5c4c912a2e2e3b0a4b49398da27df1c6921fc9469a686f05f42015`.

At the start of this consolidation they were ignored by `/notes/`, untracked,
and unmodified. They contained no credentials, private infrastructure values,
or session secrets. They are now preserved byte-for-byte as tracked research
protocol sources; their prose has not been rewritten.

The current prompt names repository snapshot
`add634ef88ad63f33f65b04eafee959af7fe4763`. The helper never rewrites this
identity. Before a later formal S1M1 panel begins, the human researcher must
confirm that the prompt's requested snapshot is the intended frozen packet
snapshot. Any researcher-authored target update must occur before packet
freeze and creates a new prompt/packet identity. It cannot occur between
reviewers.

## Formal prerequisite

Do not run independent review until all of the following are true:

    six unrestricted representation cells complete
    AND every process return_code == 0
    AND every final audit valid == true
    AND results collected
    AND post-gate analysis complete
    AND S1M1 method/result packet frozen

Partial artifacts, a RUNNING job, or preliminary interpretation do not satisfy
this gate. This checkpoint does not invoke an LLM, API, browser, or network.

## Panel identity and independence

A completed panel contains exactly five raw reviews:

- `reviewer_01`;
- `reviewer_02`;
- `reviewer_03`;
- `reviewer_04`;
- `reviewer_05`.

Every reviewer receives the same content-identical frozen packet, the same
reviewer prompt, and the same method instruction in a fresh session/context.
A reviewer sees no other raw review, synthesis, author response, or reported
attitude. Reviewer 2 is not asked to evaluate Reviewer 1. Providers/models may
differ, but packet and instructions do not. Recurrence is evidence for
adjudication, not a mechanical vote.

## Frozen packet

The packet spec explicitly lists tracked repository files and assigns each a
role and packet-relative path. It must include at least:

- scientific commit SHA;
- frozen method/specification;
- experimental design;
- relevant decisions;
- provenance;
- final six-representation summary;
- formal quantitative tables;
- fixed qualitative inspection material;
- limitations;
- reviewer prompt;
- reviewer method instruction.

No placeholder final result may enter a formal packet. The builder requires a
clean Git working tree, tracked source files, safe repository-relative source
paths, safe packet-relative destinations, a full scientific SHA, and a new
output directory. It copies source bytes without transformation and records
source path, packet path, role, bytes, SHA-256, repository HEAD, scientific
commit, prompt hash, method hash, and the five expected reviewer IDs.

`packet_sha256` is SHA-256 over canonical UTF-8 JSON of the manifest identity
excluding the `packet_sha256` field itself. Files are ordered by
`(role, packet_path, source_path)`, so input list order cannot change packet
identity. Packet verification checks the manifest identity, every copied file,
and, when a repository root is supplied, every frozen source file.

After the S1M1 freeze, the human operator creates the final spec according to
`review_packet_spec.schema.json` and runs:

    ./.venv/bin/python scripts/review/review_packet.py build \
      --spec reports/reviews/s1m1_freeze_<sha>/protocol/packet_spec.json \
      --output-dir reports/reviews/s1m1_freeze_<sha>/packet

Then verify before every reviewer invocation:

    ./.venv/bin/python scripts/review/review_packet.py verify \
      --packet-dir reports/reviews/s1m1_freeze_<sha>/packet \
      --repo-root .

## Prompt immutability and panel restart

Once `reviewer_01` begins, no packet, prompt, method instruction, or packet
file may change. If a prompt defect or packet defect is discovered mid-panel,
the panel is invalid or incomplete and must be restarted under a new packet
identity. Reviews from different packet or prompt identities cannot be mixed
into one independent panel.

Reviewer findings do not trigger performance-oriented retuning of the frozen
milestone. A genuine implementation/validity defect or proof that execution
did not satisfy the frozen specification may invalidate the milestone; that is
a validity repair with explicit provenance, not an attempt to make results
prettier.

## Raw review preservation

The eventual layout is:

    reports/reviews/s1m1_freeze_<sha>/
        protocol/
        packet/
        reviews/
            reviewer_01/
                metadata.json
                raw_review.md
            ... reviewer_05/
        synthesis/
            review_matrix.tsv
            synthesis.md
            adjudication.md

No fake `raw_review.md` is created during preparation. Each actual raw response
is saved independently and unedited: no polishing, rewriting, criticism
removal, summarizing-over, or merging. Metadata conforms to
`raw_review_metadata.schema.json` and binds the reviewer ID, packet hash,
prompt hash, method hash, raw path, and raw-response SHA-256. Model, provider,
version, and timestamp are recorded when reliably obtainable; otherwise use
`unknown`. Credentials, API keys, and session secrets are never recorded.

Validate a preserved raw review with:

    ./.venv/bin/python scripts/review/review_packet.py verify \
      --packet-dir reports/reviews/s1m1_freeze_<sha>/packet \
      --review-metadata reports/reviews/s1m1_freeze_<sha>/reviews/reviewer_01/metadata.json

## Completion, synthesis, and adjudication

Synthesis starts only after 5/5 metadata-bound raw reviews are preserved.
Three or four reviews are not a completed panel. The author must not use early
reviews to change the packet before remaining reviewers run.

Raw reviews remain immutable and separate from synthesis. The tracked matrix
header in `reports/reviews/synthesis/review_matrix.template.tsv` supports
recurring and isolated concerns without pretending that count alone decides
severity. Synthesis may group novelty, identifiability, lexical-discovery vs
compression, fixed-grammar prior, exact reconstruction, lexicon-grammar
competition, script/spacing, evaluation, morphology-claim, robustness,
reproducibility, falsifiability, scalability, and limitation concerns. These
are reviewer questions, not leading conclusions.

Author adjudication is a separate artifact. Each response is one of accept,
partially accept, reject with evidence, defer, require additional analysis,
require wording limitation, or require method change, and links to a result,
code, specification, evidence, or limitation. Adjudication never edits raw
review text. Under the forward-only principle, accepted critique informs the
next milestone unless it exposes a validity defect in the frozen one.