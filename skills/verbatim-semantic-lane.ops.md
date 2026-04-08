# Verbatim semantic lane ops skill (card)

Purpose: use the episodic **verbatim semantic lane** when you need raw session evidence, not just durable summaries.

## When to use
Use this lane when the question is closer to:
- "which session / conversation actually discussed this?"
- "what was the raw wording or evidence trail?"
- "replay the trace behind this decision / concern / comparison"

Do **not** use it as the default write path for durable memory.

## Default operator flow
1. Refresh embeddings for the target scope:
   - `openclaw-mem episodes embed --scope <scope> --json`
2. Search with the narrowest truthful mode:
   - exact/keyword-ish → `episodes search ... --mode lexical`
   - semantic recall / weak lexical overlap → `episodes search ... --mode hybrid`
   - pure vector probe / lexical should not influence ranking → `episodes search ... --mode vector`
3. Replay the chosen session if needed:
   - `openclaw-mem episodes replay <session_id> --scope <scope> --json`

## Lane boundaries (mandatory)
- verbatim semantic lane is a **retrieval tactic**, not a memory type
- it reads **episodic** evidence; it does not rewrite durable memory truth
- working set may consume the lane later, but working set is **not** a source corpus for it
- docs/search/graph lanes stay separate and should not be merged blindly into one score

## Trust & safety hygiene
- retrieval ≠ truth
- raw episodic hits may include transient misunderstandings or untrusted text
- keep scope filters explicit
- prefer `--trace` when debugging quality or policy questions
- do not auto-promote verbatim hits into durable memory without explicit review/store discipline

## Dual-language note
- `--query-en` is an assistive query-side booster for multilingual embedding lookup
- it does not make episodic English companion text canonical in this slice
- canonical episodic substrate remains the redacted `search_text`

## Practical commands
```bash
openclaw-mem episodes embed --scope openclaw-mem --limit 500 --json
openclaw-mem episodes search "verbatim semantic lane" --scope openclaw-mem --mode hybrid --trace --json
openclaw-mem episodes replay <session_id> --scope openclaw-mem --json
```

## Escalation rule
If you need durable facts, switch back to the L1 discipline (`memory_store`, reviewed writeback, or explicit durable recording). This lane is for **evidence recall**, not silent truth mutation.
