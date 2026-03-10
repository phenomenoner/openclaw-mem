# Quickstart

This page is the **fastest local proof** for `openclaw-mem`.

It assumes you want to verify the core story first:

- local-first
- searchable
- auditable
- no OpenClaw config changes yet

If you are still deciding how to adopt it, read [Choose an install path](install-modes.md) first.

## Prerequisites

- Python 3.10+ (recommended: Python 3.13)
- [uv](https://github.com/astral-sh/uv)

## 1) Clone and install

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked
```

## 2) Create a tiny sample and ingest it

```bash
DB=/tmp/openclaw-mem-quickstart.sqlite
python3 ./scripts/make_sample_jsonl.py --out /tmp/openclaw-mem-sample.jsonl

uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json status
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json ingest --file /tmp/openclaw-mem-sample.jsonl
```

What to expect:

- `status` returns a JSON object with DB counters
- `ingest` returns inserted row counts and IDs

## 3) Run the local recall loop

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json search "OpenClaw" --limit 5
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json timeline 1 --window 2
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json get 1
```

That is the product in miniature:

- data goes in locally
- recall stays inspectable
- you can verify what happened without involving a remote backend

## 4) Optional: inspect ops posture

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json profile --recent-limit 10
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json optimize review --limit 200
```

## What to do next

### If you are integrating with OpenClaw agents

- Read the [Agent memory skill (SOP)](agent-memory-skill.md) — it defines trust-aware routing for when to recall, store, search docs, consult topology, or do nothing.

### If the local proof was enough

- move to [Deployment guide](deployment.md)
- enable the sidecar on your existing OpenClaw install

### If you want the detailed source-checkout walkthrough

- GitHub quickstart: <https://github.com/phenomenoner/openclaw-mem/blob/main/QUICKSTART.md>

### If you want the engine path

- read [Mem Engine reference](mem-engine.md)
- read [Ecosystem fit](ecosystem-fit.md)
