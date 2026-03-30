# openclaw-mem

**Trust-aware context packing for OpenClaw.**

This docs site is organized around one core idea:

- keep prompt packs **small**
- keep selection **inspectable**
- keep trust tiers and provenance **visible**
- keep stale / untrusted / hostile content from quietly polluting future answers

This docs site is organized around a practical product journey:

1. what problem is being solved,
2. how trust-aware packing addresses it,
3. where to verify the proof quickly,
4. and how to adopt with a low-risk rollout path.

Two-plane framing:

- **Query plane (default):** recall + trust-aware context packing with citations and receipts.
- **Action plane (optional):** recommendation-only hygiene and maintenance review queues (no silent writeback to durable memory).

## Recommended rollout sequence

1. **Prove it locally (5 minutes)** — [Trust-aware pack proof](showcase/trust-aware-context-pack-proof.md)
2. **Run sidecar on existing OpenClaw (default)** — [Choose an install path](install-modes.md)
3. **Promote to optional mem engine when needed** — [Mem Engine reference](mem-engine.md)

## Start here

- [Trust-aware pack proof](showcase/trust-aware-context-pack-proof.md) — canonical before/after artifact
- [About openclaw-mem](about.md) — product scope, audience, and boundaries
- [Quickstart](quickstart.md) — fastest local proof from a fresh clone
- [Portable pack capsules](portable-pack-capsules.md) — `openclaw-mem capsule` seal / inspect / verify / diff + bounded `export-canonical` writer (`--dry-run` preview preserved)
- [Reality check & status](reality-check.md) — what is done, partial, and roadmap

## Proof artifacts

- [Metrics JSON](showcase/artifacts/trust-aware-context-pack.metrics.json)
- [Synthetic fixture + receipts](showcase/artifacts/index.md)
- [Inside-Out demo](showcase/inside-out-demo.md)

## Product shape

`openclaw-mem` is intentionally split into two layers:

- **Sidecar (default)** — capture, ingest, local recall, pack receipts, graph query/drift checks, hygiene review
- **Mem Engine (optional)** — memory-slot backend for hybrid recall and bounded automation

Start with the inspectable sidecar, then add the engine only when you need it.

## Most common next stops

- [Choose an install path](install-modes.md)
- [Deployment guide](deployment.md)
- [Auto-capture plugin](auto-capture.md)
- [Mem Engine reference](mem-engine.md)

## Deeper reference

- [Context pack](context-pack.md)
- [Architecture](architecture.md)
- [Importance grading](importance-grading.md)
- [Agent memory skill (SOP)](agent-memory-skill.md)
- [Automation status](automation-status.md)
- [Roadmap](roadmap.md)

## Releases

- [GitHub releases](https://github.com/phenomenoner/openclaw-mem/releases)
- [Repository](https://github.com/phenomenoner/openclaw-mem)
