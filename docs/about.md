# About openclaw-mem

`openclaw-mem` is a **local-first memory layer for OpenClaw**.

Its job is simple: make long-running OpenClaw work easier to trust.

It gives operators a durable record of what the agent actually did, plus a practical recall surface they can inspect, test, and roll back.

In product terms, it helps answer three questions:
- **what changed**
- **why it changed**
- **what should still be trusted**

## The problem it solves

Most agent memory stories sound good until you need one of these in production:

- **fresh recall** of what happened recently
- **auditability** for tool outcomes, decisions, and ops breadcrumbs
- **cheap local lookup** before asking a remote semantic system again
- **safe rollback** when a memory backend or embedding path gets weird
- **memory hygiene** so stale or low-signal context does not quietly poison the next decision

`openclaw-mem` exists to make agent memory more transparent, verifiable, and easy to audit.

## What operators can do today (v1.1)

- run deterministic local recall (`search → timeline → get`) against SQLite
- inspect topology relationships and drift via `graph query ...` and `graph query drift`
- run recommendation-only hygiene checks with `optimize review` (zero write path)
- capture/ingest episodic events with redaction-first defaults
- optionally promote to `openclaw-mem-engine` for hybrid recall + policy controls

## Product shape

### Sidecar (default)

This is the normal starting point.

`openclaw-mem` captures observations into JSONL, ingests them into SQLite, and gives you a local recall loop:

`search → timeline → get`

What you get:

- local SQLite ledger with FTS
- deterministic CLI and JSON receipts
- optional ingest / triage / packaging flows
- no forced change to your active OpenClaw memory slot

### Mem Engine (optional)

When you want `openclaw-mem` to do more than sidecar work, the optional **openclaw-mem-engine** can become the active OpenClaw memory backend.

What it adds:

- hybrid recall (FTS + vector)
- scoped / policy-aware retrieval
- bounded autoRecall / autoCapture behavior
- explicit receipts and rollbackable config knobs

## Why local-first matters

A lot of memory tooling gets harder to trust as soon as it becomes harder to inspect.

`openclaw-mem` keeps the base layer simple:

- JSONL for append-only capture
- SQLite for local search and timeline inspection
- exportable artifacts you can diff, back up, and reason about

That means you can start small, prove value, and only add semantic layers where they genuinely help.

## Who it’s for

### OpenClaw operators
You want durable capture, ingestion freshness, and a cleaner incident trail.

### Builders experimenting with agent memory
You want something more useful than a toy demo, but less fragile than a giant hosted stack.

### Teams that need memory with receipts
You care about decisions, preferences, specs, notes, and operational breadcrumbs being retrievable later.

## What it is not

- **Not** a hosted SaaS memory product.
- **Not** a mandatory replacement for OpenClaw native memory.
- **Not** “capture everything forever and hope.”
- **Not** a promise that embeddings magically fix memory quality.

The sidecar-first posture is deliberate: prove usefulness first, then expand.

## Recommended way to adopt it

1. **Start local** — prove the recall loop on a sample or your own JSONL.
2. **Add the sidecar** — wire capture + harvest into your existing OpenClaw install.
3. **Promote the engine only if needed** — switch slot ownership when hybrid recall and policy controls justify it.

## Read next

- [Choose an install path](install-modes.md)
- [Quickstart](quickstart.md)
- [Reality check & status](reality-check.md)
- [Deployment guide](deployment.md)
- [Ecosystem fit](ecosystem-fit.md)
- [Mem Engine reference](mem-engine.md)
