# openclaw-mem

**Local-first memory sidecar for OpenClaw, with an optional hybrid memory engine when you want more control.**

This docs site is organized to answer three questions in order:

1. **What is this product, really?**
2. **Which install path fits my setup?**
3. **Where do I go for proof, deployment, and deep reference?**

## Start here

- [About openclaw-mem](about.md) — product story, problem, audience, and boundaries
- [Choose an install path](install-modes.md) — the three adoption modes and when each one makes sense
- [Quickstart](quickstart.md) — fastest local proof
- [Reality check & status](reality-check.md) — what is done, partial, and roadmap

## Product shape

`openclaw-mem` is intentionally split into two layers:

- **Sidecar (default)** — capture, ingest, local recall, triage, receipts
- **Mem Engine (optional)** — memory-slot backend for hybrid recall and bounded automation

That split is the core design choice: start with something inspectable and rollbackable, then add power only when it earns its keep.

## Most common next stops

- [Deployment guide](deployment.md)
- [Auto-capture plugin](auto-capture.md)
- [Ecosystem fit](ecosystem-fit.md)
- [Mem Engine reference](mem-engine.md)

## Deeper reference

- [Architecture](architecture.md)
- [Context pack](context-pack.md)
- [Importance grading](importance-grading.md)
- [Automation status](automation-status.md)
- [Roadmap](roadmap.md)
- [Release checklist](release-checklist.md)

## Releases

- [GitHub releases](https://github.com/phenomenoner/openclaw-mem/releases)
- [Repository](https://github.com/phenomenoner/openclaw-mem)
