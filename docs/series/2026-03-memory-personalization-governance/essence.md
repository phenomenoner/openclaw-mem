# Essence

## Load-bearing ideas
- The painful failure mode in modern LLM memory is not only forgetting; it is **over-remembering and over-mentioning**.
- Karpathy's "trying too hard" names a real UX bug: the system performs memory instead of proportioning it.
- The problem is best understood as a stack failure:
  - write too much
  - classify too crudely
  - retrieve too eagerly
  - surface too aggressively
- Decay helps, but it is only lifecycle hygiene. It is not the whole answer.
- Better systems split:
  - retention from activation
  - docs from durable memory
  - retrieval from mention
- `openclaw-mem` is strongest when framed as **trust-aware context packing + memory governance**, not as generic "more memory".
- The right product direction is not bigger prompts; it is smaller, cleaner, cited context with explicit suppression and receipts.
- Consolidation is promising only if it produces reviewable candidates instead of silently rewriting truth.

## One-sentence spine
好的 LLM 記憶不是更會想起你，而是更知道什麼時候不該把想起來的東西說出口。
