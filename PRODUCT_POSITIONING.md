# Product positioning

`openclaw-mem` is a local-first memory governance layer and context supply chain for teams running AI agents that need memory they can inspect, cite, constrain, and roll back. OpenClaw is the first-class deployment target.

It is not trying to be a generic memory SDK, hosted memory API, vector database, or opaque second brain. Its job is narrower: govern what becomes context.

> Store operational records locally. Pack only bounded, cited context. Observe why each memory was included, excluded, or quarantined.

## Core product

The first evaluation path is intentionally small.

1. **Store** — capture or ingest memory records into local JSONL/SQLite artifacts.
2. **Pack** — produce bounded `ContextPack` output with citations, trust policy, and trace receipts.
3. **Observe** — inspect timelines, exact records, pack traces, and rollback-friendly artifacts.

That core should work on synthetic test memory before it ever touches a real operator memory store.

## First user

The first user is an advanced OpenClaw operator or agent-infra builder who has at least one of these problems:

- memory retrieval is opaque enough that they cannot explain why a fact entered context
- prompt context is bloated by old, untrusted, or contradictory memories
- memory changes need receipts, rollback, and auditability
- local-first operation matters more than a hosted memory cloud

## Differentiation

| Alternative | What `openclaw-mem` adds |
| --- | --- |
| Native memory slots | sidecar-first audit, traceable packs, governed promotion, one-line rollback posture |
| Memory SDKs / engines | governance over storage: trust policy, pack receipts, citation coverage, and rollback posture |
| Vector databases | operational records, trust policy, citations, and pack receipts instead of embeddings alone |
| Hosted memory APIs | local artifacts, inspectable SQLite/JSONL, no required SaaS hop |
| Plain logs | search, timeline, get, and `ContextPack` assembly for agent recall |

## Public proof standard

A public proof should be synthetic, reproducible, and small enough to review.

The current proof target is:

- use a small synthetic memory fixture
- compare an ungated pack with a trust-aware pack
- show selected refs, citation coverage, quarantined-row exclusion, bundle size, and trust-policy reasons
- avoid reading any real OpenClaw memory, private workspace, or operator state

## Advanced labs

The repository also contains advanced and experimental lanes such as graph routing, GBrain, continuity, Dream Lite, and deeper optimization loops. They are valuable research/product options, but they should not be required to understand or trust the core product.

Public onboarding should lead with Store / Pack / Observe first. Advanced labs come after the evaluator has seen the core proof.
