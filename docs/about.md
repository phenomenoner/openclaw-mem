# About openclaw-mem

`openclaw-mem` is a memory layer for OpenClaw.

Its job is simple to describe and hard to do well: help an agent recover the right memory later **without** dragging stale, untrusted, or oversized context into every prompt.

## What problem it solves

Long-running agents usually fail in one of these ways:

- old notes still match the query even when they are no longer useful
- untrusted or hostile content retrieves well and quietly shapes the answer
- prompts bloat into giant memory dumps instead of a small cited bundle
- when something goes wrong, there is no clear receipt showing why a memory was included

`openclaw-mem` exists to make that behavior more transparent, bounded, and inspectable.

## What it does today

- local recall with `search → timeline → get`
- compact memory packs with `pack`
- trace receipts that show what was included or excluded
- trust-policy controls for pack selection
- sidecar capture on top of an existing OpenClaw install
- optional promotion to `openclaw-mem-engine` later for hybrid recall and stronger policy controls

## How the product is split

There are two roles in this project:

### Sidecar (default)

This is the normal starting point.

- captures observations into JSONL
- ingests them into SQLite
- gives you a local recall and pack loop you can inspect
- does **not** replace your active OpenClaw memory backend

### Memory engine (optional)

This is the controlled next step when sidecar mode already proved useful.

- can become the active OpenClaw memory backend
- adds hybrid recall and tighter policy controls
- keeps rollback explicit and configuration-driven

## Query mode vs maintenance mode

The repo uses a simple internal split:

- **Query mode** = recall and context packing with citations and trace receipts
- **Maintenance mode** = read-only suggestions and review flows; no silent writeback to memory

Most users can ignore that distinction at first. Start with the proof and the sidecar path.

## Who it is for

- **OpenClaw operators** who want smaller, more inspectable memory packs
- **Agent builders** who want a practical memory layer without jumping straight to a hosted stack
- **Teams with decisions, notes, and specs to remember** who care about evidence and rollback, not just retrieval scores

## What it is not

- not a hosted SaaS memory product
- not a requirement to capture everything forever
- not a promise that embeddings alone solve retrieval quality
- not a requirement to replace OpenClaw native memory on day one

## Recommended reading path

1. [Quickstart](quickstart.md)
2. [Trust-aware pack proof](showcase/trust-aware-context-pack-proof.md)
3. [Choose an install path](install-modes.md)
4. [Reality check & status](reality-check.md)
5. [Deployment guide](deployment.md)
