# Verbatim semantic lane

`openclaw-mem` now ships a bounded **verbatim semantic lane** for episodic recall.

The point is narrow on purpose:
- improve retrieval over **raw episodic evidence**
- keep the lane **read-only**
- preserve **scope / redaction / audit** posture
- avoid collapsing durable / episodic / working / docs into one blob

This is a **retrieval tactic**, not a new memory type.

---

## What it is

The lane works over the existing `episodic_events.search_text` substrate.

Shipped operator surfaces:

```bash
openclaw-mem episodes embed --scope <scope> --json
openclaw-mem episodes search "<query>" --scope <scope> --mode hybrid --trace --json
```

- `episodes embed` builds embeddings for the **redacted/bounded** episodic search text
- `episodes search --mode lexical` keeps the existing FTS path
- `episodes search --mode hybrid` fuses FTS + vector results with RRF
- `episodes search --mode vector` uses vector-only ranking when you want a pure semantic probe

The existing `episodes replay` and `episodes query` flows remain unchanged.

---

## What it is not

This slice does **not**:
- create a new durable memory type
- auto-promote verbatim hits into L1 durable truth
- make Working Set a source corpus
- rewrite docs cold-lane retrieval
- merge verbatim scores with synthesis/pack scores as if they were directly comparable

If you need durable truth, use the existing L1 store discipline.
If you need current-turn activation, use Working Set / pack surfaces.
If you need operator-authored docs, use docs cold lane.

---

## Recommended operator use

Use the verbatim lane when you need questions like:
- "which session actually discussed this?"
- "what was the raw wording / evidence?"
- "find the conversation trail, not just the durable summary"

Typical flow:

```bash
# 1) refresh embeddings for the relevant episodic scope
openclaw-mem episodes embed --scope openclaw-mem --limit 500 --json

# 2) semantic-first retrieval over raw episodic evidence
openclaw-mem episodes search "verbatim semantic lane" \
  --scope openclaw-mem \
  --mode hybrid \
  --trace \
  --json

# 3) replay the chosen session when needed
openclaw-mem episodes replay <session_id> --scope openclaw-mem --json
```

---

## Memory-type × retrieval-lane matrix

| memory role | lexical / FTS | hybrid | verbatim semantic | dual-language assist | graph/topology |
|---|---:|---:|---:|---:|---:|
| durable (L1) | yes | yes | evidence-only | yes | optional provenance assist |
| episodic | yes | yes | **yes — primary shipped slice** | later / query-assist only | no |
| working set | consume only | consume only | consume only | no direct writeback role | optional downstream consumer |
| docs cold lane | yes | yes | separate docs substrate, not this slice | yes | optional repo/path routing |

Interpretation:
- **verbatim semantic lane** is strongest on episodic evidence recall
- durable memory may consume it as supporting evidence, not as automatic truth
- working set may later consume the lane, but should not become a source corpus for it
- dual-language remains an assistive retrieval booster, not the lane itself

---

## Dual-language relation

The existing dual-language strategy solves **query-language mismatch**.
The verbatim semantic lane solves **raw-corpus retrieval over episodic evidence**.

Those are related, but not the same thing.

Current shipped posture:
- verbatim lane indexes the canonical episodic `search_text`
- `--query-en` is available as an optional query-side assist for multilingual embedding lookup
- this slice does **not** add a second episodic `text_en` storage plane

That keeps the first production slice bounded while still leaving room for future cross-language recovery work.

See also: [Dual-language memory strategy](dual-language-memory-strategy.md).

---

## Safety and tradeoffs

Tradeoffs to remember:
- stronger semantic retrieval can increase candidate noise
- raw episodic evidence can contain transient misunderstandings
- vector quality depends on embedding freshness and model consistency

Guardrails in this slice:
- scope-aware filtering
- redaction-first episodic substrate
- read-only retrieval
- bounded result counts
- optional `--trace` receipts for lane inspection

---

## Recommended rollout

1. Prove lexical episodic search on your scope.
2. Run `episodes embed` for that scope.
3. Compare `--mode lexical` vs `--mode hybrid` on a small fixed query set.
4. Keep route/pack policy unchanged until the semantic lane shows a real hit-quality gain.

If you need the deeper design rationale, see:
- [Architecture](architecture.md)
- [Mem Engine](mem-engine.md)
- [Verbatim semantic lane v0 spec](specs/verbatim-semantic-lane-v0.md)
