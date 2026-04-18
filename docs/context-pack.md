# Context packing (ContextPack) — hybrid text + JSON

Status: **SHIPPED + EXTENDED** (`openclaw-mem pack` emits a stable `context_pack` object, supports protected-tail assembly hooks, and now applies graph-aware synthesis preference inside pack selection).

## Shipped today vs proposed next

### Shipped today
- `openclaw-mem pack` emits `bundle_text`
- `items[]` are available for structured inspection
- `context_pack` emits a stable `openclaw-mem.context-pack.v1` object
- optional trace receipts exist for debugging selection behavior

For migration safety, the legacy top-level `bundle_text` / `items` / `citations` fields still ship alongside `context_pack`. New consumers should prefer `context_pack` as the canonical contract.

### Planned extensions
- stronger L0/L1/L2 packaging conventions
- richer expand-style hooks beyond the current protected-tail contract

The JSON contract below is now the shipped baseline for `context_pack`. Future additions should extend it compatibly.

## Why this exists

Long-running OpenClaw sessions drift because the live prompt becomes a soup of:
- stale history,
- partial repeats,
- and mixed trust/provenance.

`openclaw-mem`’s context packing stance is:

- **Build a small bundle per request** (instead of shipping the whole session)
- Keep it **bounded** (token budgets, caps)
- Keep it **auditable** (citations + trace receipts)
- Keep it **safe-by-default** (redaction + trust gating)

## What we mean by “ContextPack”

A **ContextPack** is an injection-ready payload that can be fed to an agent as “relevant state”.

In v0 today, `openclaw-mem pack` already outputs:
- `bundle_text` (injection-friendly bullets)
- `items[]` (structured list)
- optional `trace` (`openclaw-mem.pack.trace.v1`, redaction-safe)

This doc defines the explicit **ContextPack.v1** schema used by `openclaw-mem pack` to keep that structure stable, shallow, and easy for LLMs (and ops tooling) to consume.

Current pack-policy behavior (v1.1 implementation posture):
- prefer graph synthesis cards before raw covered refs when a deterministic coverage relationship already exists
- rank warm candidates by graph preference, trust, importance, retrieval strength, and recency
- optionally reserve a protected tail budget for caller-supplied recent turns
- keep all of that observable in `pack --trace` via `trace.extensions.policy`

Formal contract: `docs/specs/context-pack-policy-v1.1.md`

## Design principles (non-negotiable)

1) **Hybrid encoding**
- LLMs respond well to a short natural-language “how to use this” preface.
- They also benefit from **structured anchors** (keys/arrays) for fast lookup.

So we intentionally ship **both**:
- **Text**: compact bullets (`bundle_text`) for direct injection
- **JSON**: a stable object (`context_pack`) for deterministic parsing/anchoring

2) **Shallow JSON beats deep JSON**
- Prefer flat objects and short arrays.
- Avoid 3+ levels of nesting unless it buys real retrieval/eviction wins.

3) **Deterministic serialization**
- Stable key ordering, stable formatting.
- This improves cache friendliness and makes diffs/bench comparisons sane.

4) **Every included item must have provenance**
- Always include a stable `recordRef` (e.g. `obs:123`).
- Optional `source_kind/source_ref/url` are encouraged when safe.

5) **Trust-aware by default**
- Pack should be able to prefer `trusted` without becoming brittle.
- Fail-open policy should be explicit and observable (in trace receipts).

## Relationship to context engines (important boundary)

Context packing is **not** the same as “lossless compaction”.

- Context engines (e.g., LCM-style plugins) focus on **session history storage + compaction + expansion**.
- `openclaw-mem` packing focuses on **selecting and presenting the right durable facts** (governed, cited, bounded).

We treat lossless context engines as a thought-link: they inspire patterns (fresh-tail protection, provenance, expand tools) without forcing an engine fork.

See: `docs/thought-links.md` (Lossless Context / lossless-claw).

## ContextPack.v1 (shipped baseline)

A minimal, stable schema optimized for LLM absorption.

```json
{
  "schema": "openclaw-mem.context-pack.v1",
  "meta": {
    "ts": "2026-02-25T00:00:00Z",
    "query": "…",
    "scope": null,
    "budgetTokens": 1200,
    "maxItems": 12
  },
  "bundle_text": "- [obs:123] …\n- [obs:456] …",
  "items": [
    {
      "recordRef": "obs:123",
      "layer": "L1",
      "type": "memory",
      "importance": "must_remember",
      "trust": "unknown",
      "text": "…",
      "citations": {"url": null, "recordRef": "obs:123"}
    }
  ],
  "notes": {
    "how_to_use": [
      "Prefer bundle_text for direct injection.",
      "Use items[].recordRef as the citation key.",
      "If you need detail, retrieve L2 by recordRef (bounded)."
    ]
  }
}
```

### Protected tail (“fresh tail”) hook

`openclaw-mem pack` now supports a bounded protected tail at assembly time:
- `--tail-text "..."` (repeatable) for caller-supplied recent turns
- `--tail-file <path>` for plain-text or JSON-list recent turns (`-` means piped stdin)
- `--tail-max-items N` to cap how many recent turns are considered
- `--tail-budget-tokens N` to reserve budget for those turns

Behavior:
- tail budget is reserved before warm durable selection
- tail slots are also reserved when tail budget is enabled, so recent continuity is not crowded out by warm hits
- tail lines land as `L0` / `recent_turn` entries
- when tail is enabled, the payload also exposes a `tail` summary block
- trace receipts expose the reserved and consumed tail budget in `trace.extensions.policy`

This is inspired by LCM-style context assembly and improves continuity while keeping budgets strict.

Golden regression fixture lane:
- editable fixture: `docs/fixtures/context-pack-golden-scenarios.v0.yaml`
- deterministic mirror: `tests/data/CONTEXT_PACK_GOLDEN_SCENARIOS.v0.jsonl`
- verifier: `tests/test_context_pack_golden.py`

### Graph-aware synthesis preference inside pack

Pack selection now reuses the existing synthesis-coverage logic before final admission:
- if a fresh synthesis card deterministically covers selected raw refs, pack prefers the card
- raw refs remain available when not covered or when the synthesis preference does not apply
- this is additive and fail-open, it does not require `--use-graph=on`

The explicit graph preflight lane (`--use-graph=off|auto|on`) still exists for broader graph neighborhood expansion. The new behavior is the smaller, always-safe graph-aware preference inside ordinary pack selection.

### Auto-graph productization guardrails

`pack --use-graph=auto` is now governed by two additional product guardrails:
- scope gate
  - explicit `--graph-scope` always allows scoped auto-graph
  - otherwise, auto mode only allows graph expansion when a deterministic local scope hint can be inferred
  - unresolved scope skips graph preflight and stays baseline-only
- latency gate
  - `--graph-latency-soft-ms` and `--graph-latency-hard-ms` control whether auto mode may compose the graph bundle into `bundle_text_with_graph`
  - over soft threshold: degrade to baseline-primary output while keeping receipts
  - over hard threshold: skip graph bundle composition in auto mode while keeping fail-open baseline behavior

Trace receipts in `trace.extensions.graph` now include scope and latency decisions so the operator can see why auto graph ran, degraded, or skipped.

## Ops: what to benchmark / what to log

- Must-have receipts:
  - `openclaw-mem.pack.trace.v1` include/exclude rationale
  - counts by lane (hot/warm/cold), and by trust/importance tier
- Quality checks:
  - “missing citations” must stay at 0 for included items
  - determinism: same DB + same query should produce the same item set (within defined policy)

## Related docs

- Architecture: `docs/architecture.md`
- Roadmap: `docs/roadmap.md` (Context Packer)
- Agent memory skill (routing contract): `docs/agent-memory-skill.md`
- Trace schema contract: `openclaw_mem/pack_trace_v1.py`
- Thought-links (design references): `docs/thought-links.md`
