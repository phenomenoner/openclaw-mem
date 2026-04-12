# Context packing (ContextPack) — hybrid text + JSON

Status: **SHIPPED** (`openclaw-mem pack` emits a stable `context_pack` object; graph-aware and protected-tail extensions remain roadmap).

## Shipped today vs proposed next

### Shipped today
- `openclaw-mem pack` emits `bundle_text`
- `items[]` are available for structured inspection
- `context_pack` emits a stable `openclaw-mem.context-pack.v1` object
- optional trace receipts exist for debugging selection behavior

For migration safety, the legacy top-level `bundle_text` / `items` / `citations` fields still ship alongside `context_pack`. New consumers should prefer `context_pack` as the canonical contract.

### Planned extensions
- stronger L0/L1/L2 packaging conventions
- protected-tail and expand-style hooks

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

A future packer version may add:
- a **protected recent tail** (recent turns, not evictable), and
- an **evictable prefix** (older summaries/memories dropped first).

This is inspired by LCM-style context assembly and improves continuity while keeping budgets strict.

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
