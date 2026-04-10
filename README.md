# openclaw-mem

**Trust-aware context packing for OpenClaw.**

`openclaw-mem` is a **local-first memory layer for OpenClaw** that helps you pack the right durable facts into context **without** dragging stale, untrusted, or hostile content into every prompt.

It is built around four operator outcomes:

- **smaller prompt packs** instead of dumping whole memory logs into chat
- **explicit trust tiers** so quarantined material can stay visible without being silently injected
- **recordRef citations + trace receipts** so you can inspect why something was included, excluded, or left fail-open
- **safer memory admission / recall** before low-signal content becomes durable memory

It operates across two planes:

- **Query plane (default):** recall + trust-aware context packing with citations and receipts.
- **Action plane (optional):** recommendation-only hygiene and maintenance review queues (no silent writeback to durable memory).

## What this product focuses on

- Prevent context admission drift when long-running agents accumulate stale or hostile notes.
- Use trust-aware context packing with explicit trust tiers, citations, and receipts.
- Provide a reproducible synthetic proof so you can test behavior before deploying.
- Start as a sidecar, then promote to mem-engine only when needed.

## See the proof first

- **Canonical proof artifact:** [`docs/showcase/trust-aware-context-pack-proof.md`](docs/showcase/trust-aware-context-pack-proof.md)
- **Before/after metrics artifact:** [`docs/showcase/artifacts/trust-aware-context-pack.metrics.json`](docs/showcase/artifacts/trust-aware-context-pack.metrics.json)
- **Synthetic fixture + receipts:** [`docs/showcase/artifacts/index.md`](docs/showcase/artifacts/index.md)
- **Companion 5-minute demo:** [`docs/showcase/inside-out-demo.md`](docs/showcase/inside-out-demo.md)

## Recommended way to get started

1. **Prove it locally (5 minutes):** run the synthetic trust-aware pack proof first.
2. **Run sidecar on existing OpenClaw (default):** keep your current memory backend and add capture/recall hygiene.
3. **Promote to optional mem engine later:** switch slot ownership only when hybrid recall/policy controls are worth it.


## Why people adopt it

- **Long-running agent failures are often admission failures, not storage failures.** Old notes, stale assumptions, scraped suggestions, and hostile instructions can quietly shape future answers.
- **Search alone is not enough.** You need a pack you can inspect, test, and audit before trusting it.
- **Smaller, cited packs beat giant context dumps.** They are cheaper to inject, easier to reason about, and safer to debug.
- **Receipts beat guesswork.** JSON outputs, pack traces, policy surfaces, and lifecycle shadow logs make memory behavior visible.
- **Sidecar-first keeps the risk low.** Test locally before touching your OpenClaw memory slot.

## What ships today in v1.4.0

- **Local operator diagnostics:** `status`, `doctor`, and `backend` provide a compact health/readiness surface before deeper debugging.
- **Local recall loop:** `search → timeline → get` keeps routine lookups fast and inspectable.
- **Trust-aware pack surfaces:** `pack`, `--trace`, `--pack-trust-policy`, `policy_surface`, and `pack_lifecycle_shadow` provide inclusion/exclusion receipts.

### Operator surface quick read

- `status` = **snapshot surface** (`kind` + `ts` + rich state/runtime posture). Read this for current shape, not pass/fail.
- `doctor` = **doctor surface** (`kind` + `ts` + `ok` + `summary` + `checks`). Read this for compact health/readiness.
- `backend` = config/backend posture helper when you need the memory slot/fallback read directly.
- Family compare card: `openclaw-async-coding-playbook/projects/openclaw-ops/docs/operator-surface-contract-family.v0.md`
- **Graph/provenance surfaces:** `graph topology-refresh`, `graph query ...`, `graph health`, `graph readiness`, drift checks, graph provenance gating for graph-derived pack candidates, and `pack --use-graph=off|auto|on` for deterministic graph-preflight consumption.
- **Graph semantic match (v0):** `graph match "<idea/query>"` groups local graph evidence into 3–10 candidate projects with explanation paths + provenance, so idea → project routing stays inspectable and fail-open.
- **Deterministic default routing (recommendation-only):** `route auto "<query>"` consults graph readiness first, then fails open to episodic transcript search when graph routing is not ready or returns no candidates.
- **Review-gated action plane (recommendation-only):** `optimize review`, `optimize consolidation-review`, and `optimize policy-loop` emit review queues for hygiene, recent-use-aware decay protection, dream-style candidate consolidation, and rollout readiness (no silent writeback).
- **Policy-driven safety:** trust policies, graph provenance, and lifecycle logging (`--pack-trust-policy`, `--graph-provenance-policy`, `--graph-query-db`, `--pack-lifecycle-shadow`) keep memory grounded, auditable, and safer for automation.
- **Episodic event lane:** append/extract/ingest/query/replay/search with redaction-first defaults.
- **Episodic verbatim semantic lane:** `episodes embed` + `episodes search --mode lexical|hybrid|vector` for bounded raw-evidence recall over redacted episodic `search_text`.
- **Optional Mem Engine upgrades:** hybrid recall controls, TODO guardrails, docs cold-lane ingest/search, and an optional `autoRecall.routeAuto` prompt hook for live routing hints.

## Graph semantic memory v0 (1.3.x)

This release line adds a bounded **idea → project matching** surface without turning the graph layer into a hard dependency.

What ships in the v0 slice:
- `graph match "<idea/query>"` returns candidate projects with explanation paths + provenance refs
- `graph health` reports freshness, node/edge counts, last-refresh timestamp, and staleness
- `graph readiness` bridges freshness, topology-source drift, and match-support availability into a single autonomous-ready verdict
- `route auto "<query>"` provides a deterministic default router that prefers graph-semantic only when it is ready and returns candidates (otherwise fails open to transcript recall)
- the feature remains **fail-open**: baseline recall / pack still work when graph-semantic data is missing or stale

Use it when you need to answer questions like:
- “which project is this idea most likely related to?”
- “what existing work already points at this concept?”
- “what should I inspect next, and why?”

## Who it's for

`openclaw-mem` is a strong fit when you want OpenClaw to keep working memory sharp across days or weeks of real work.

Typical fits:
- **OpenClaw operators** who want better recall freshness, auditability, and rollback posture
- **Agent builders** who need a practical memory surface before adding more complexity
- **Teams with docs / repos / decisions to remember** who want memory that stays explainable

## Three adoption paths

### 1) Local proof in one repo
Use this when you want to prove value first.

- clone the repo
- ingest a synthetic trust-aware fixture
- run `pack` before/after a trust policy
- inspect the receipts before touching OpenClaw config

### 2) Sidecar on an existing OpenClaw install
Use this when you already run OpenClaw and want better capture, freshness, and observability.

- keep your current memory slot (`memory-core` or `memory-lancedb`)
- enable the capture plugin
- schedule `harvest`
- use `openclaw-mem` for local recall, triage, and pack receipts

### 3) Promote the optional Mem Engine
Use this when you want `openclaw-mem` to own the memory slot.

- switch to `openclaw-mem-engine` only after a sidecar smoke test
- get hybrid recall, bounded automation, and operator-tunable policies
- optionally enable the `autoRecall.routeAuto` hook to consult `openclaw-mem route auto` before agent start and inject a compact synthesis-aware routing hint block into live turns
- keep rollback to native backends as a one-line slot change

## 5-minute local proof (no OpenClaw required)

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

## Portable governed pack capsule (memvid-inspired thin slice)

If you want a **portable memory capsule** without surrendering trust/provenance governance, use the first-class command family:

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

`openclaw-mem` is **one product family with two operator roles**:

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
