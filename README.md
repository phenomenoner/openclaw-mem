# openclaw-mem

**Stop long-running OpenClaw projects from rotting.**

`openclaw-mem` is a **local-first memory layer for OpenClaw**.
It gives your agent a durable, searchable memory ledger so you can answer three questions fast:

- **what changed**
- **why it changed**
- **what the agent should still trust**

Start with a local sidecar. Keep your current OpenClaw memory backend if you want. Promote to the optional mem engine later if you need hybrid recall, policy controls, and safer automation.

## Why people adopt it

- **Context drift shows up first in long-running work** — old notes, stale assumptions, and weak signals quietly shape new answers.
- **Search alone is not enough** — you need a recall path you can inspect, test, and audit.
- **Receipts beat vibes** — JSON outputs, timeline views, and topology checks make memory behavior easier to verify.
- **Sidecar-first keeps the risk low** — prove the product locally before changing your main OpenClaw memory slot.

## Best first fit

`openclaw-mem` is a strong fit when you want OpenClaw to keep working memory sharp across days or weeks of real work.

Typical fits:
- **OpenClaw operators** who want better recall freshness, auditability, and rollback posture
- **Agent builders** who need a practical memory surface before adding more complexity
- **Teams with docs / repos / decisions to remember** who want memory to stay explainable instead of opaque

## Core capabilities in v1.1.0

- **Local recall loop:** `search → timeline → get` keeps routine lookups fast and inspectable.
- **Graph/query plane:** `graph topology-refresh`, `graph query ...`, `graph query drift`, `graph query provenance`.
- **Recommendation-only memory hygiene:** `optimize review` plus `optimize policy-loop` for read-only rollout readiness.
- **Policy-driven safety:** trust policies, graph provenance, and lifecycle logging (`--pack-trust-policy`, `--graph-provenance-policy`, `--graph-query-db`, `--pack-lifecycle-shadow`) keep memory grounded, auditable, and safer for automation.
- **Episodic event lane:** append/extract/ingest/query/replay with redaction-first defaults.
- **Optional Mem Engine upgrades:** hybrid recall controls, TODO guardrails, docs cold-lane ingest/search.

## Three adoption paths

### 1) Local proof in one repo
Use this when you want to prove the core story first.

- clone the repo
- ingest a sample JSONL file
- run local recall against SQLite
- verify that memory is inspectable before touching OpenClaw config

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

## 5-minute local proof (no OpenClaw required)

Goal: prove three things in one pass:
1. memory stays local
2. recall is inspectable
3. stale / noisy memory can be reviewed before it pollutes future context

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

If that works, you have already shown the core value:
- memory is local and inspectable
- you can recover what happened without a black-box backend
- you can review memory health before trusting it blindly

Want a tighter demo talk track? See [`docs/showcase/inside-out-demo.md`](docs/showcase/inside-out-demo.md).

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

**Demo / positioning path**
- **5-minute showcase:** [`docs/showcase/inside-out-demo.md`](docs/showcase/inside-out-demo.md)
- **About the wedge:** [`docs/about.md`](docs/about.md)

**Operate and extend**
- **Release checklist:** [`docs/release-checklist.md`](docs/release-checklist.md)
- **Triage task-marker acceptance (TASK/TODO/REMINDER forms):** [`docs/upgrade-checklist.md`](docs/upgrade-checklist.md)
- **Agent memory skill (SOP):** [`docs/agent-memory-skill.md`](docs/agent-memory-skill.md)
- **Release notes:** <https://github.com/phenomenoner/openclaw-mem/releases>

## Product shape

`openclaw-mem` has two parts:

- **Sidecar (default):** capture, ingest, local recall, triage, receipts.
- **Mem Engine (optional):** an OpenClaw memory-slot backend for hybrid recall and controlled automation.

The README stays focused on the product story: local proof first, sidecar next, engine only when it earns the right to exist.

## License

Dual-licensed: **MIT OR Apache-2.0**. See `LICENSE`, `LICENSE-MIT`, and `LICENSE-APACHE`.
