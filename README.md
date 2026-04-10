# openclaw-mem

A memory layer for [OpenClaw](https://github.com/openclaw/openclaw) that keeps agent context small, cited, and less likely to be polluted by stale or untrusted content.

## The problem

Long-running agents do not just forget. They also accumulate memory that quietly degrades:

- old notes still match the query even when they are no longer useful
- untrusted or hostile content can retrieve well and slip into context
- prompts bloat into giant memory dumps instead of a small, inspectable bundle
- when something goes wrong, it is hard to explain **why** a memory was included

`openclaw-mem` tackles that by building compact memory packs with citations, trace receipts, and trust-policy controls.

## Try it in 5 minutes

You can prove the core behavior locally without touching OpenClaw config.

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked

DB=/tmp/openclaw-mem-proof.sqlite
uv run --python 3.13 --frozen -- python -m openclaw_mem ingest \
  --db "$DB" \
  --json \
  --file ./docs/showcase/artifacts/trust-aware-context-pack.synthetic.jsonl

uv run --python 3.13 --frozen -- python -m openclaw_mem pack \
  --db "$DB" \
  --query "trust-aware context packing prompt pack receipts hostile durable memory provenance" \
  --limit 5 \
  --budget-tokens 500 \
  --trace \
  --pack-trust-policy exclude_quarantined_fail_open
```

### What this proof shows

- the same query can change its result set when a trust policy is applied
- quarantined content can be excluded with an explicit reason
- every include/exclude decision stays inspectable through receipts and trace output

Start here if you want the full walkthrough:
- [Trust-aware pack proof](docs/showcase/trust-aware-context-pack-proof.md)
- [Metrics JSON](docs/showcase/artifacts/trust-aware-context-pack.metrics.json)
- [Synthetic fixture + receipts](docs/showcase/artifacts/index.md)
- [Inside-out demo](docs/showcase/inside-out-demo.md)

## Install paths

| Path | Use this when | Risk |
|---|---|---|
| Local proof | You want to evaluate the behavior before touching config | None |
| Sidecar plugin | You want capture, recall, and observability on an existing OpenClaw install | Low |
| Memory engine | You want `openclaw-mem` to become the active memory backend | Medium, but rollbackable |

Read the full guide: [Choose an install path](docs/install-modes.md)

## What you can do today

- run deterministic local recall with `search → timeline → get`
- build compact packs with `pack` and inspect the decision trail with `--trace`
- apply trust policies to keep quarantined material out of packs while preserving explicit receipts
- add sidecar capture to an existing OpenClaw install without replacing its active memory backend
- optionally promote to `openclaw-mem-engine` later for hybrid recall and tighter policy controls

## Good next links

- [Docs home](docs/index.md)
- [About the project](docs/about.md)
- [Quickstart](docs/quickstart.md)
- [Deployment guide](docs/deployment.md)
- [Reality check & status](docs/reality-check.md)
- [GitHub releases](https://github.com/phenomenoner/openclaw-mem/releases)

## Idea → project matching (v0)

This repo also includes a bounded **idea → project matching** capability without turning the graph layer into a hard dependency.

What ships in the v0 slice:
- `graph match "<idea/query>"` returns candidate projects with explanation paths + provenance refs
- `graph health` reports freshness, node/edge counts, last-refresh timestamp, and staleness
- `graph readiness` bridges freshness, topology-source drift, and match-support availability into a single autonomous-ready verdict
- `route auto "<query>"` provides a deterministic default router that prefers graph-semantic only when it is ready and returns candidates (otherwise falls back to transcript recall)
- baseline recall / pack still work when graph-semantic data is missing or stale

Use it when you need to answer questions like:
- “which project is this idea most likely related to?”
- “what existing work already points at this concept?”
- “what should I inspect next, and why?”

## Extended local proof (compare before/after)

If you want the fuller before/after walkthrough instead of the quick proof above, use this path.

Goal: prove three things in one pass:
1. the same query can change selection when trust policy is enabled
2. quarantined / hostile memory does not have to pollute the pack
3. citations and receipts stay intact

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked

DB=/tmp/openclaw-mem-proof.sqlite
uv run --python 3.13 --frozen -- python -m openclaw_mem ingest \
  --db "$DB" \
  --json \
  --file ./docs/showcase/artifacts/trust-aware-context-pack.synthetic.jsonl

uv run --python 3.13 --frozen -- python -m openclaw_mem pack \
  --db "$DB" \
  --query "trust-aware context packing prompt pack receipts hostile durable memory provenance" \
  --limit 5 \
  --budget-tokens 500 \
  --trace

uv run --python 3.13 --frozen -- python -m openclaw_mem pack \
  --db "$DB" \
  --query "trust-aware context packing prompt pack receipts hostile durable memory provenance" \
  --limit 5 \
  --budget-tokens 500 \
  --trace \
  --pack-trust-policy exclude_quarantined_fail_open
```

If that works, you have already shown the core behavior:
- the same query can exclude quarantined memory with an explicit reason
- the pack stays compact and cited
- the selection remains inspectable through `trace`, `policy_surface`, and `lifecycle_shadow`

Want the narrated walkthrough? See [`docs/showcase/trust-aware-context-pack-proof.md`](docs/showcase/trust-aware-context-pack-proof.md).

## Portable pack capsules

If you want a **portable memory capsule** without giving up trust/provenance governance, use the first-class command family:

```bash
DB=/tmp/openclaw-mem-proof.sqlite
OUT=/tmp/openclaw-mem-capsules/trust-aware-demo

openclaw-mem capsule seal \
  --db "$DB" \
  --query "trust-aware context packing prompt pack receipts hostile durable memory provenance" \
  --pack-trust-policy exclude_quarantined_fail_open \
  --stash-artifact \
  --gzip-artifact \
  --out "$OUT"

CAPSULE=$(find "$OUT" -mindepth 1 -maxdepth 1 -type d | sort | tail -1)
openclaw-mem capsule inspect "$CAPSULE"
openclaw-mem capsule verify "$CAPSULE"
openclaw-mem capsule diff "$CAPSULE" --db "$DB" --write-receipt --write-report-md

CANONICAL_OUT=/tmp/openclaw-mem-canonical-export
openclaw-mem capsule export-canonical --db "$DB" --to "$CANONICAL_OUT" --json
openclaw-mem capsule export-canonical --db "$DB" --dry-run --to "$CANONICAL_OUT" --json

CANONICAL=$(find "$CANONICAL_OUT" -mindepth 1 -maxdepth 1 -type d | sort | tail -1)
ISOLATED_DB=/tmp/openclaw-mem-restore-isolated.sqlite
openclaw-mem capsule restore "$CANONICAL" --dry-run --db "$ISOLATED_DB" --json
openclaw-mem capsule restore "$CANONICAL" --apply --db "$ISOLATED_DB" --json
```

`seal` creates a small pack capsule directory with:
- `manifest.json`
- `bundle.json`
- `bundle_text.md`
- `trace.json` (when available)
- `artifact_stash.json` (when artifact stash is enabled)
- `diff.latest.json` (when `diff --write-receipt` is used)
- `diff.latest.md` (when `diff --write-report-md` is used)

`export-canonical` writes a separate timestamped canonical artifact directory under `--to` with:
- `manifest.json` (`openclaw-mem.canonical-capsule.v1`)
- `observations.jsonl` (row-level snapshot of the `observations` table)
- `index.json` (counts/ranges/columns + digest pointers)
- `provenance.json` (export provenance + explicit non-goals)

`inspect` is the forward-compat/readability companion command:
- verifies first and shows capsule metadata + bundle preview
- marks v0 pack capsules as portable audit artifacts (not restore artifacts)
- marks canonical capsules as restorable only under bounded isolated-target rules

`diff` is the read-only comparison companion command:
- verifies the capsule first
- compares pack capsule items against a target governed store
- reports `present` vs `missing` with **no mutation**

`export-canonical` is the canonical artifact writer:
- non-dry-run writes a versioned canonical artifact directory and self-verifies file integrity
- `--dry-run` emits a manifest contract preview with planned layout/path
- preserves explicit non-goals for migration/merge/live-target restore

`restore` is the bounded replay lane for canonical artifacts only:
- `--dry-run` performs preflight contract + conflict planning with **no mutation**
- `--apply` is allowed only for isolated/new target store, same-engine, append-only replay
- rejects non-canonical schema/version or live-risky targets cleanly
- emits rollback manifest + restore receipt + readback verifier proof

Compatibility paths still work (including `restore`):
- `openclaw-mem-pack-capsule ...` (wrapper command)
- `python3 ./tools/pack_capsule.py ...` (thin delegator)

## Start here

**Understand the product**
- **About the product:** [`docs/about.md`](docs/about.md)
- **Choose an install path:** [`docs/install-modes.md`](docs/install-modes.md)
- **Docs site index:** [`docs/index.md`](docs/index.md)
- **Reality check / status:** [`docs/reality-check.md`](docs/reality-check.md)

**Get it running**
- **Detailed quickstart:** [`QUICKSTART.md`](QUICKSTART.md)
- **Deployment patterns:** [`docs/deployment.md`](docs/deployment.md)
- **Auto-capture plugin:** [`docs/auto-capture.md`](docs/auto-capture.md)
- **Optional Mem Engine:** [`docs/mem-engine.md`](docs/mem-engine.md)

**Proof / showcase path**
- **Canonical proof:** [`docs/showcase/trust-aware-context-pack-proof.md`](docs/showcase/trust-aware-context-pack-proof.md)
- **5-minute showcase:** [`docs/showcase/inside-out-demo.md`](docs/showcase/inside-out-demo.md)
- **About the product:** [`docs/about.md`](docs/about.md)

**Operate and extend**
- **Release checklist:** [`docs/release-checklist.md`](docs/release-checklist.md)
- **Triage task-marker acceptance (TASK/TODO/REMINDER forms):** [`docs/upgrade-checklist.md`](docs/upgrade-checklist.md)
- **Agent memory skill (SOP):** [`docs/agent-memory-skill.md`](docs/agent-memory-skill.md)
- **Release notes:** <https://github.com/phenomenoner/openclaw-mem/releases>

## Product shape

`openclaw-mem` is **one product family with two install roles**:

- **Sidecar (default):** capture, ingest, local recall, triage, pack receipts.
- **Mem Engine (optional):** an OpenClaw memory-slot backend for hybrid recall and controlled automation.

Marketplace/package mapping keeps install boundaries explicit:
- `@phenomenoner/openclaw-mem` = sidecar package
- `@phenomenoner/openclaw-mem-engine` = engine package

The split keeps install and rollback boundaries clean.

## License

Dual-licensed: **MIT OR Apache-2.0**, at your option.

- MIT terms: `LICENSE` (root canonical text for GitHub/license-scanner detection)
- Apache 2.0 terms: `LICENSE-APACHE` (root canonical text for GitHub/license-scanner detection)
