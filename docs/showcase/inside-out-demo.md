# Inside-Out Memory — 5-minute reproducible demo (synthetic)

This demo is **synthetic** (no private/user data). It showcases the *contract* for a “durable self” memory layer:

- A small set of **core preferences / decisions / commitments** is stored once.
- On demand, we can **pack** the relevant memories into a compact, cited bundle.
- An agent can then answer consistently (timezone, privacy constraints, style), without bloating its chat context.

## Prereqs
- `uv`
- In this repo: `uv sync` (or just let `uv run ...` build on demand)

## Run

```bash
# From repo root
./scripts/inside_out_demo.sh
```

You should see a packed bundle (plus an optional trace) for a keyword-style query (works even with no API key / no embeddings):
> `timezone privacy demo style`

## What to look for
- **Timezone preference** is recalled (UTC+8 / Asia-Taipei in this synthetic example).
- **Privacy constraint** is recalled (demo uses synthetic data; do not leak private notes).
- **Style preference** is recalled (index-first / bounded reveal).

## Architecture diagram
- Mermaid: `docs/showcase/inside-out-architecture.mmd`

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

## Notes
- This demo is intentionally small: it’s a **vertical slice** + an executable regression.
- It’s OK if not every feature is finished yet — the demo defines the contract and exposes gaps.
