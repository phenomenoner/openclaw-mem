# openclaw-mem

**Local-first memory sidecar for OpenClaw, with an optional hybrid memory engine when you want it to become the active memory backend.**

`openclaw-mem` turns your agent’s work into a durable, searchable, auditable memory trail.
Start with a local SQLite sidecar. Keep your current OpenClaw memory backend if you want. Promote to the optional mem engine later if you need hybrid recall, policy controls, and safer automation.

## Why people adopt it

- **Local-first by default** — JSONL + SQLite, no external database required.
- **Inspectable recall loop** — `search → timeline → get` keeps routine lookups fast and auditable.
- **Deterministic operator tools** — topology query/drift checks, recommendation-only optimization, and explicit JSON receipts.
- **Upgradeable path** — sidecar first, engine later; no forced migration on day one.

## Who it’s for

- **OpenClaw operators** who want memory freshness, auditability, and safer rollbacks.
- **Agent builders** who need a practical local recall surface before adding more complexity.
- **Teams with docs / repos / decisions to remember** who want memory to stay explainable.

## Core capabilities in v1.1.0

- **Graph/query plane (deterministic):** `graph topology-refresh`, `graph query ...`, `graph query drift`, `graph query provenance`.
- **Optimization observer (zero-write):** `optimize review` proposes cleanups (staleness, duplication, repeated misses) without mutating data.
- **Episodic event lane:** append/extract/ingest/query/replay with redaction-first defaults.
- **Optional Mem Engine upgrades:** hybrid recall controls, TODO guardrails, docs cold-lane ingest/search.

## Three adoption paths

### 1) Local proof in one repo
Use this when you just want to see the product work.

- clone the repo
- ingest a sample JSONL file
- run local recall against SQLite
- no OpenClaw config changes

### 2) Sidecar on an existing OpenClaw install
Use this when you already run OpenClaw and want better capture, freshness, and observability.

- keep your current memory slot (`memory-core` or `memory-lancedb`)
- enable the capture plugin
- schedule `harvest`
- use `openclaw-mem` for local recall, triage, and receipts

### 3) Promote the optional Mem Engine
Use this when you want `openclaw-mem` to own the memory slot.

- switch to `openclaw-mem-engine` only after a sidecar smoke test
- get hybrid recall, bounded automation, and operator-tunable policies
- keep rollback to native backends as a one-line slot change

## Quick proof (local, no OpenClaw required)

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked

DB=/tmp/openclaw-mem.sqlite
python3 ./scripts/make_sample_jsonl.py --out /tmp/openclaw-mem-sample.jsonl

uv run --python 3.13 --frozen -- python -m openclaw_mem --help
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json status
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json ingest --file /tmp/openclaw-mem-sample.jsonl
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json search "OpenClaw" --limit 5
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json timeline 2 --window 2
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json optimize review --limit 200
```

If that works, your local memory ledger is active and verifiable: you already have an inspectable recall path and a safe recommendation-only optimization pass.

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

**Operate and extend**
- **Release checklist:** [`docs/release-checklist.md`](docs/release-checklist.md)
- **Triage task-marker acceptance (TASK/TODO/REMINDER forms):** [`docs/upgrade-checklist.md`](docs/upgrade-checklist.md)
- **Agent memory skill (SOP):** [`docs/agent-memory-skill.md`](docs/agent-memory-skill.md)
- **Release notes:** <https://github.com/phenomenoner/openclaw-mem/releases>

## Product shape

`openclaw-mem` has two parts:

- **Sidecar (default):** capture, ingest, local recall, triage, receipts.
- **Mem Engine (optional):** an OpenClaw memory-slot backend for hybrid recall and controlled automation.

Deep implementation detail stays in the reference docs; the README is meant to help you decide whether this project matches your setup.

## License

Dual-licensed: **MIT OR Apache-2.0**. See `LICENSE`, `LICENSE-MIT`, and `LICENSE-APACHE`.
