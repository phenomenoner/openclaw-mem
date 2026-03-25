# openclaw-mem

**Trust-aware context packing for OpenClaw.**

This docs site is organized around one wedge first:

- keep prompt packs **small**
- keep selection **inspectable**
- keep trust tiers and provenance **visible**
- keep stale / untrusted / hostile content from quietly polluting future answers

Two-plane framing:

- **Query plane (default):** recall + trust-aware context packing with citations and receipts.
- **Action plane (optional):** recommendation-only hygiene and maintenance review queues (no silent writeback to durable memory).

## Start here

- [Trust-aware pack proof](showcase/trust-aware-context-pack-proof.md) — canonical before/after artifact
- [About openclaw-mem](about.md) — product story, wedge, audience, and boundaries
- [Relaunch information architecture (v0)](launch/relaunch-information-architecture-v0.md) — message hierarchy + page roles
- [Quickstart](quickstart.md) — fastest local proof from a fresh clone
- [Reality check & status](reality-check.md) — what is done, partial, and roadmap

## Proof artifacts

- [Metrics JSON](showcase/artifacts/trust-aware-context-pack.metrics.json)
- [Synthetic fixture + receipts](showcase/artifacts/index.md)
- [Inside-Out demo](showcase/inside-out-demo.md)

## Product shape

`openclaw-mem` is intentionally split into two layers:

- **Sidecar (default)** — capture, ingest, local recall, pack receipts, graph query/drift checks, hygiene review
- **Mem Engine (optional)** — memory-slot backend for hybrid recall and bounded automation

That split is the core design choice: start with something inspectable and rollbackable, then add power only when it earns its keep.

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

## Launch / external copy

- [Relaunch information architecture (v0)](launch/relaunch-information-architecture-v0.md)
- [Trust-aware context pack copy pack](launch/trust-aware-context-pack-copy-pack.md)
- [GitHub repo surface consistency](launch/github-repo-surface-consistency.md)

## Releases

- [GitHub releases](https://github.com/phenomenoner/openclaw-mem/releases)
- [Repository](https://github.com/phenomenoner/openclaw-mem)
