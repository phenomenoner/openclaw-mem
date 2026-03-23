# About openclaw-mem

`openclaw-mem` is a **trust-aware context packing layer for OpenClaw**.

It helps operators recover the right durable facts, keep prompt packs small, and avoid letting stale, untrusted, or hostile content quietly become durable memory or pollute future context.

In practical terms, it helps answer four questions:
- **what changed**
- **why it changed**
- **what should still be trusted**
- **what should stay out of the pack**

## Start with proof, not adjectives

If you want the wedge in one artifact first:

- [Canonical trust-aware pack proof](showcase/trust-aware-context-pack-proof.md)
- [Before/after metrics JSON](showcase/artifacts/trust-aware-context-pack.metrics.json)
- [Synthetic fixture + receipts](showcase/artifacts/index.md)

The proof is intentionally **synthetic** so it is safe to run publicly and easy to inspect.

## The problem it solves

Most agent-memory stories sound fine until a long-running system starts doing one of these:

- injecting stale notes because they still match the query text
- packing untrusted or hostile content because it retrieved well
- bloating prompts with giant memory dumps instead of a small cited pack
- losing the ability to explain *why* a given memory entered context
- making rollback harder because the memory layer behaves like a black box

`openclaw-mem` exists to make memory admission and recall more transparent, bounded, and inspectable.

## What operators can do today (v1.1)

- run deterministic local recall (`search → timeline → get`) against SQLite
- build compact packs with `pack`
- emit redaction-safe pack receipts with `--trace`
- apply `--pack-trust-policy exclude_quarantined_fail_open` to drop quarantined rows while keeping unknown trust explicit
- inspect `policy_surface` and `lifecycle_shadow` to see what was selected, excluded, and logged
- inspect topology relationships and drift via `graph query ...` and `graph query drift`
- gate graph-derived candidates with graph provenance policy surfaces
- run recommendation-only hygiene checks with `optimize review` (zero write path)
- capture/ingest episodic events with redaction-first defaults
- optionally promote to `openclaw-mem-engine` for hybrid recall + policy controls

## Product shape

`openclaw-mem` is one product family, but it ships in two operator roles and therefore two plugin install units when packaged for a marketplace.

Marketplace/install mapping:
- `@phenomenoner/openclaw-mem` → sidecar role
- `@phenomenoner/openclaw-mem-engine` → engine role

That split is there to preserve clean install and rollback boundaries. It is **not** a product-brand split.

### Sidecar (default)

This is the normal starting point.

`openclaw-mem` captures observations into JSONL, ingests them into SQLite, and gives you a local recall / packing loop you can inspect:

`search → timeline → get → pack`

What you get:

- local SQLite ledger with FTS
- deterministic CLI and JSON receipts
- trust-aware pack surfaces and lifecycle logs
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

A memory system gets harder to trust when it gets harder to inspect.

`openclaw-mem` keeps the base layer simple:

- JSONL for append-only capture
- SQLite for local search, timeline inspection, and pack generation
- exportable artifacts you can diff, back up, and reason about
- recordRef citations and trace receipts for packed context

That means you can start small, prove value, and only add semantic layers where they genuinely help.

## Who it’s for

### OpenClaw operators
You want durable capture, smaller safer prompt packs, and a cleaner incident trail.

### Builders experimenting with agent memory
You want something more useful than a toy demo, but less fragile than a giant hosted stack.

### Teams that need memory with receipts
You care about decisions, preferences, specs, notes, and operational breadcrumbs being retrievable later — with enough evidence to inspect them.

## What it is not

- **Not** a hosted SaaS memory product.
- **Not** a mandate to capture everything forever.
- **Not** a promise that retrieval quality comes from embeddings alone.
- **Not** a requirement to replace OpenClaw native memory on day one.

The sidecar-first posture is deliberate: prove the pack, then expand.

## Recommended way to adopt it

1. **Start with the trust-aware proof** — run the synthetic fixture and compare pack receipts before/after trust policy.
2. **Add the sidecar** — wire capture + harvest into your existing OpenClaw install.
3. **Promote the engine only if needed** — switch slot ownership when hybrid recall and policy controls justify it.

## Read next

- [Home / docs index](index.md)
- [Choose an install path](install-modes.md)
- [Quickstart](quickstart.md)
- [Reality check & status](reality-check.md)
- [Context pack](context-pack.md)
- [Mem Engine reference](mem-engine.md)
