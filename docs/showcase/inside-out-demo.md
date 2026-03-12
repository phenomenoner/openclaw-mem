# Inside-Out Memory — 5-minute reproducible demo (synthetic)

> If you want the stricter trust-gating proof first, start with [trust-aware context pack proof](trust-aware-context-pack-proof.md).

This demo is **synthetic** (no private/user data). It is the shortest clean showcase for the `openclaw-mem` wedge:

- a small set of stable preferences / constraints is stored once
- relevant memory can be packed into a compact, cited bundle on demand
- an agent can answer consistently **without bloating chat context**

In product language, this demo proves a simple claim:

> `openclaw-mem` helps the agent recover what still matters, with receipts.

## Who this demo is for

Use this demo when you want to show any of the following fast:
- why local memory is more trustworthy than a vague "AI memory" story
- how a compact recall pack can beat dumping giant memory files into context
- how to keep stable constraints visible without turning memory into a black box

## Prereqs
- `uv`
- In this repo: `uv sync` (or let `uv run ...` build on demand)

## Run

```bash
# From repo root
./scripts/inside_out_demo.sh
```

You should see a packed bundle (plus an optional trace) for a keyword-style query that works even with no API key / no embeddings:

> `timezone privacy demo style`

## Demo talk track

Use this 3-beat flow when showing it to someone:

### 1) Before memory
Ask for a demo plan with no recalled constraints.

The typical agent answer is generic. It may ignore timezone, privacy expectations, or preferred output structure.

### 2) Pull the recall pack
Run the demo and show the packed bundle.

The point is not raw retrieval volume. The point is that a **small, relevant, cited** pack comes back instead of a giant wall of memory.

### 3) After memory
Ask for the same plan again, now with the recalled constraints in view.

The agent should:
- use the preferred timezone for time references
- keep the demo synthetic / privacy-safe
- structure output in the preferred style

That is the core value: not "more memory", but **memory that changes the answer in a controlled, inspectable way**.

## What to look for
- **Timezone preference** is recalled (UTC+8 / Asia-Taipei in this synthetic example).
- **Privacy constraint** is recalled (demo uses synthetic data; do not leak private notes).
- **Style preference** is recalled (index-first / bounded reveal).
- **Pack stays compact** instead of dragging in unrelated memory.

## Before/After (illustrative transcript)

### Before (no memory)
User: “Write a demo plan for my agent system.”

Agent (typical): gives a generic plan, may ignore timezone + privacy constraints.

### After (with packed memories)
User: “Write a demo plan for my agent system.”

Agent (memory-aware):
- uses the preferred timezone for time references
- explicitly keeps the demo synthetic / privacy-safe
- structures output index-first and cites the recalled constraints

## Why this demo matters

This demo is intentionally small.

That is a feature, not a weakness:
- it is a **vertical slice** of the recall contract
- it is reproducible
- it is safe to run publicly
- it gives a clean before/after story for README, docs, and live demos

If you want a first GTM-friendly demo for `openclaw-mem`, start here.

## Architecture diagram
- Mermaid: `docs/showcase/inside-out-architecture.mmd`
