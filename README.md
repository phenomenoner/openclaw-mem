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
- Make value easy to verify with a reproducible synthetic proof.
- Keep adoption practical: start sidecar-first, then promote to mem-engine only when needed.

## See the proof first

- **Canonical proof artifact:** [`docs/showcase/trust-aware-context-pack-proof.md`](docs/showcase/trust-aware-context-pack-proof.md)
- **Before/after metrics artifact:** [`docs/showcase/artifacts/trust-aware-context-pack.metrics.json`](docs/showcase/artifacts/trust-aware-context-pack.metrics.json)
- **Synthetic fixture + receipts:** [`docs/showcase/artifacts/index.md`](docs/showcase/artifacts/index.md)
- **Companion 5-minute demo:** [`docs/showcase/inside-out-demo.md`](docs/showcase/inside-out-demo.md)

## Recommended way to get started

1. **Prove it locally (5 minutes):** run the synthetic trust-aware pack proof first.
2. **Run sidecar on existing OpenClaw (default):** keep your current memory backend and add capture/recall hygiene.
3. **Promote to optional mem engine later:** switch slot ownership only when hybrid recall/policy controls are worth it.

This keeps adoption practical: prove value locally first, then expand with explicit rollback options.

## Why people adopt it

- **Long-running agent failures are often admission failures, not storage failures.** Old notes, stale assumptions, scraped suggestions, and hostile instructions can quietly shape future answers.
- **Search alone is not enough.** You need a pack you can inspect, test, and audit before trusting it.
- **Smaller, cited packs beat giant context dumps.** They are cheaper to inject, easier to reason about, and safer to debug.
- **Receipts beat vibes.** JSON outputs, pack traces, policy surfaces, and lifecycle shadow logs make memory behavior visible.
- **Sidecar-first keeps the risk low.** Prove the product locally before touching your OpenClaw memory slot.

## What ships today in v1.1.0

- **Local recall loop:** `search → timeline → get` keeps routine lookups fast and inspectable.
- **Trust-aware pack surfaces:** `pack`, `--trace`, `--pack-trust-policy`, `policy_surface`, and `pack_lifecycle_shadow` provide inclusion/exclusion receipts.
- **Graph/provenance surfaces:** `graph topology-refresh`, `graph query ...`, drift checks, and graph provenance gating for graph-derived pack candidates.
- **Review-gated action plane (recommendation-only):** `optimize review` plus `optimize policy-loop` emit review queues for rollout readiness (no silent writeback).
- **Policy-driven safety:** trust policies, graph provenance, and lifecycle logging (`--pack-trust-policy`, `--graph-provenance-policy`, `--graph-query-db`, `--pack-lifecycle-shadow`) keep memory grounded, auditable, and safer for automation.
- **Episodic event lane:** append/extract/ingest/query/replay with redaction-first defaults.
- **Optional Mem Engine upgrades:** hybrid recall controls, TODO guardrails, docs cold-lane ingest/search.

## Best first fit

`openclaw-mem` is a strong fit when you want OpenClaw to keep working memory sharp across days or weeks of real work.

Typical fits:
- **OpenClaw operators** who want better recall freshness, auditability, and rollback posture
- **Agent builders** who need a practical memory surface before adding more complexity
- **Teams with docs / repos / decisions to remember** who want memory to stay explainable instead of opaque

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

## Maintainer launch docs (internal guidance)

These files define copy/governance rules for maintainers and release editors, not end-user product docs:

- [`docs/launch/relaunch-information-architecture-v0.md`](docs/launch/relaunch-information-architecture-v0.md)
- [`docs/launch/trust-aware-context-pack-copy-pack.md`](docs/launch/trust-aware-context-pack-copy-pack.md)
- [`docs/launch/github-repo-surface-consistency.md`](docs/launch/github-repo-surface-consistency.md)
- [`docs/launch/proof-first-relaunch-checklist.md`](docs/launch/proof-first-relaunch-checklist.md)
- [`docs/launch/release-surface-proof-pack-v0.md`](docs/launch/release-surface-proof-pack-v0.md)
- [`docs/launch/release-note-body-v0-final.md`](docs/launch/release-note-body-v0-final.md)

## Product shape

`openclaw-mem` is **one product family with two operator roles**:

- **Sidecar (default):** capture, ingest, local recall, triage, pack receipts.
- **Mem Engine (optional):** an OpenClaw memory-slot backend for hybrid recall and controlled automation.

Marketplace/package mapping keeps install boundaries explicit:
- `@phenomenoner/openclaw-mem` = sidecar package
- `@phenomenoner/openclaw-mem-engine` = engine package

The split is about install/rollback boundary, not about pretending they are unrelated products.

## License

Dual-licensed: **MIT OR Apache-2.0**, at your option.

- MIT terms: `LICENSE` (root canonical text for GitHub/license-scanner detection)
- Apache 2.0 terms: `LICENSE-APACHE`
