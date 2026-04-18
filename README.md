# openclaw-mem

**A local-first context supply chain for OpenClaw: store what matters, pack what fits, observe what changed.**

`openclaw-mem` turns agent work into a durable, searchable, auditable memory trail, then assembles bounded context bundles that are small enough to inject and easy to verify.
Start with a local SQLite sidecar. Keep your current OpenClaw memory backend if you want. Promote to the optional mem engine later if you need hybrid recall, policy controls, and safer automation.

## Why people adopt it

- **Local-first by default** — JSONL + SQLite, no external database required.
- **Cheap recall loop** — `search → timeline → get` keeps routine lookups fast and inspectable.
- **Bounded packing** — `pack` emits a stable `ContextPack` contract for injection, citations, graph-aware synthesis preference, protected fresh tails, and trace-backed debugging.
- **Fits real OpenClaw ops** — capture tool outcomes, retain receipts, and keep rollback simple.
- **Upgradeable path** — sidecar first, engine later; no forced migration on day one.

## Who it’s for

- **OpenClaw operators** who want memory freshness, auditability, and safer rollbacks.
- **Agent builders** who need a practical local recall surface before adding more complexity.
- **Teams with docs / repos / decisions to remember** who want memory to stay explainable.

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

uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json status
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json ingest --file /tmp/openclaw-mem-sample.jsonl
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json search "OpenClaw" --limit 5

uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json timeline 2 --window 2
```

If that works, the product story is real: you already have a local memory ledger plus a recall path you can inspect.

## Store + Pack + Observe

The product loop is simple and stable:

1. **Store**: capture, ingest, and query observations with `store`/`ingest`/`search`.
2. **Pack**: run `pack` to get a bounded `bundle_text` and `context_pack` (`schema: openclaw-mem.context-pack.v1`), with optional protected-tail continuity and graph-aware synthesis preference.
3. **Observe**: use `timeline`, `get`, and `artifact` outputs for explainability and rollback.

Example:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem pack "What changed this week?" --limit 6 --json
uv run --python 3.13 --frozen -- python -m openclaw_mem artifact stash --from ./tool-output.txt --json
uv run --python 3.13 --frozen -- python -m openclaw_mem artifact peek ocm_artifact:v1:sha256:<64hex> --json
```

## Start here

- **About the product:** [`docs/about.md`](docs/about.md)
- **v2 blueprint:** [`docs/context-supply-chain-blueprint.md`](docs/context-supply-chain-blueprint.md)
- **Choose an install path:** [`docs/install-modes.md`](docs/install-modes.md)
- **Detailed quickstart:** [`QUICKSTART.md`](QUICKSTART.md)
- **Triage task-marker acceptance (TASK/TODO/REMINDER forms):** [`docs/upgrade-checklist.md`](docs/upgrade-checklist.md)
- **Docs site:** <https://phenomenoner.github.io/openclaw-mem/>
- **Reality check / status:** [`docs/reality-check.md`](docs/reality-check.md)
- **Deployment patterns:** [`docs/deployment.md`](docs/deployment.md)
- **Auto-capture plugin:** [`docs/auto-capture.md`](docs/auto-capture.md)
- **Agent memory skill (SOP):** [`docs/agent-memory-skill.md`](docs/agent-memory-skill.md)
- **Pack policy contract:** [`docs/specs/context-pack-policy-v1.1.md`](docs/specs/context-pack-policy-v1.1.md)
- **Optional Mem Engine:** [`docs/mem-engine.md`](docs/mem-engine.md)
- **Release notes:** <https://github.com/phenomenoner/openclaw-mem/releases>

## Product shape

`openclaw-mem` is easiest to understand as three cooperating surfaces:

- **Store:** sidecar capture, ingest, local recall, optional mem-engine slot ownership.
- **Pack:** bounded `ContextPack` output for injection, citations, and retrieval traces.
- **Observe:** receipts, traces, and artifact offload for debugging and rollback.

Deep implementation detail stays in the reference docs; the README is meant to help you decide whether this project matches your setup.

## License

Dual-licensed: **MIT OR Apache-2.0**. See `LICENSE`, `LICENSE-MIT`, and `LICENSE-APACHE`.
