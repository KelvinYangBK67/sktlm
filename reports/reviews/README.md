# Independent review materials

This tree contains protocol and schema preparation only. No reviewer LLM has
been invoked and no raw review is represented as existing.

- `protocol/independent_llm_review_protocol.md` fixes the five-fresh-session,
  identical-packet workflow and prompt/source provenance.
- `protocol/review_packet_spec.schema.json` describes the explicit packet
  input contract; the Python helper additionally enforces exactly one prompt
  and method role, all required roles, safe paths, tracked sources, and a clean
  checkout.
- `protocol/raw_review_metadata.schema.json` describes provenance for an
  eventual immutable raw response.
- `synthesis/` contains header/instruction templates only; it is not populated
  until 5/5 raw reviews exist.

Researcher-authored source text remains at
`notes/reviewer/reviewer_prompt.txt` and `notes/reviewer/method.txt`. Those files
were originally ignored/untracked and were promoted byte-for-byte for
reproducibility during the 2026-09-01 local consolidation.