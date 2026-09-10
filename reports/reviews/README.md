# Independent review materials

This tree contains historical protocol/schema preparation and templates only.
No reviewer LLM has been invoked and no raw review is represented as existing.

- `protocol/independent_llm_review_protocol.md` preserves the five-session,
  identical-packet workflow as prepared before final S1M1 closure. Its old
  six-completed-cell prerequisite and tracked-source wording are historical,
  not the current four-AVAILABLE/two-typed-N/A S1M1 authority.
- `protocol/review_packet_spec.schema.json` describes the explicit packet
  input contract; the Python helper additionally enforces exactly one prompt
  and method role, all required roles, safe paths, tracked sources, and a clean
  checkout.
- `protocol/raw_review_metadata.schema.json` describes provenance for an
  eventual immutable raw response.
- `synthesis/` contains header/instruction templates only; it is not populated
  until 5/5 raw reviews exist.

The protocol references researcher-authored files under `notes/reviewer/`.
`notes/**` is local-only and is not tracked in the current repository tree.
Before any future panel, the researcher must freeze a current packet and source
contract; this index does not claim that such a panel or packet exists.
