# Compounding Context OS roadmap

Status: **PUBLIC ROADMAP / DESIGN NOTE**

`openclaw-mem` is evolving from a memory sidecar into the memory and context
layer for a compounding agent operating system. The goal is not to make a larger
chat transcript. The goal is to maintain a small, governed, explainable context
supply chain that improves as agents work.

## Product stance

Keep the stable split:

- **Store** captures durable records with provenance, trust, importance, and
  rollback-friendly receipts.
- **Pack** compiles a bounded `ContextPack` for the current task. It owns the
  injection contract.
- **Observe** keeps artifacts, traces, and review receipts inspectable without
  flooding the live prompt.

Graphs, docs memory, GBrain-style sidecars, and lifecycle jobs may enrich this
loop, but they should not become competing sources of truth.

## Why this matters

Long-running agents fail when memory becomes a pile of stale snippets. A useful
context system needs to answer four questions on every turn:

1. What should be remembered?
2. What should be packed right now?
3. What should be archived, quarantined, or rechecked?
4. What receipt proves why that choice was made?

The compounding path is therefore a governance loop, not only a retrieval loop.

## Capability map

| Capability | Home surface | First-class contract |
| --- | --- | --- |
| Durable record capture | Store | provenance, trust, importance, citations |
| Task context assembly | Pack | `openclaw-mem.context-pack.v1` |
| Memory lifecycle review | Store + Observe | review-only steward receipts |
| Source ingestion | Store | public-safe candidate records and entity hints |
| Skill/workflow learning | Observe | lifecycle receipts before apply |
| Active execution lines | External controller | goal/status/stop-loss receipts that Pack can cite |

## Memory steward review

The first additive slice is a deterministic, review-only steward contract:

- classify candidate records as promotion, keep-observed, archive/ignore, or
  quarantine candidates;
- surface public-safety review markers before public docs are written;
- emit no side effects;
- require a separate checkpointed apply path for any mutation.

This keeps the system safe-by-default: the steward can recommend changes, while
Store/Pack/Observe remain auditable and rollbackable.

## Design rules

1. **Review before apply** — steward output is advisory until a separate apply
   path checkpoints, mutates, and verifies.
2. **Pack remains bounded** — lifecycle jobs may influence ranking, but they do
   not justify dumping more raw memory into the prompt.
3. **Trust is separate from usefulness** — frequent retrieval must not promote
   untrusted content to trusted content.
4. **Public docs stay public-safe** — examples should avoid private paths,
   identities, channel IDs, tokens, and local operator details.
5. **Receipts beat vibes** — every automation loop should leave machine-readable
   evidence plus a human-readable summary when operators need debugging context.

## Shipped public-safe slices

- `openclaw-mem steward review --file <json-or-jsonl>` reviews candidate records
  without mutating storage.
- `openclaw-mem ingest-review source --file <text-or-markdown>` turns a source
  into candidate records, entity hints, follow-up actions, and risk markers.
- `openclaw-mem active-line pack --file <receipt.json>` converts an active-line
  or goal receipt into a small ContextPack-compatible fragment.

## Suggested next slices

1. Connect steward receipts to `pack --trace` so included records can refresh
   lifecycle metadata through a governed apply path.
2. Add richer synthetic ingestion fixtures for articles, transcripts, PDFs, and
   repository notes.
3. Let Pack accept active-line context fragments directly as protected L0 inputs
   without loading a whole operations log.

## Non-goals

- Replacing the operator's canonical memory backend by force.
- Auto-mutating trusted memory from untrusted input.
- Making graph or sidecar experiments the source of durable truth.
- Treating a human-readable report as a machine gate unless that gate is
  separately specified and tested.
