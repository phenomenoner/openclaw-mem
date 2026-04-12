# Quickstart Guide

Get `openclaw-mem` up and running in ~5 minutes.

This guide is the fastest local proof for the product wedge:

- prompt packs stay smaller than a giant memory dump
- trust tiers stay visible and actionable
- stale / untrusted / hostile content can be kept out of the pack with receipts

## Prerequisites

- Python 3.10+ (recommended: Python 3.13)
- [uv](https://github.com/astral-sh/uv)
- OpenClaw gateway running (only needed for the plugin / Route A)

---

## Step 1: Install

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked
```

**Run from source:**

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem ...
```

If you have a packaged install that provides the console script, you can use:

```bash
openclaw-mem ...
```

---

## Step 2: Quick test

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem --json status
uv run --python 3.13 --frozen -- python -m openclaw_mem --json doctor
uv run --python 3.13 --frozen -- python -m openclaw_mem --json backend
```

What this proves:
- the local ledger is alive
- the CLI surface is working
- you have a one-shot doctor surface for common setup/health questions
- you can inspect memory posture before wiring anything deeper

---

## Step 2.1: Canonical trust-aware pack proof (synthetic)

This is the cleanest showcase path when you want the wedge directly instead of a generic smoke test.

```bash
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
```

See:
- `docs/showcase/trust-aware-context-pack-proof.md`
- `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`
- `docs/showcase/inside-out-demo.md`

---

## Step 3: Ingest sample data

```bash
python3 ./scripts/make_sample_jsonl.py --out ./sample.jsonl
uv run --python 3.13 --frozen -- python -m openclaw_mem ingest --file ./sample.jsonl --json
```

---

## Step 4: Progressive recall (search → timeline → get)

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem search "OpenClaw" --limit 10 --json
uv run --python 3.13 --frozen -- python -m openclaw_mem timeline 2 --window 2 --json
uv run --python 3.13 --frozen -- python -m openclaw_mem get 1 --json
```

This is the product in miniature:
- **search** finds candidate memory
- **timeline** scopes it to the right slice of history
- **get** lets you inspect the concrete memory instead of trusting a vague summary

---

## Step 4.5: Build prompt-ready context + offload artifacts (context-pack v1)

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem pack "What should I prioritize next?" --limit 6 --json

printf 'very long tool output...' > ./tool-output.txt
uv run --python 3.13 --frozen -- python -m openclaw_mem artifact stash --from ./tool-output.txt --meta-json '{"source":"agent-cli-demo"}' --json

uv run --python 3.13 --frozen -- python -m openclaw_mem artifact fetch ocm_artifact:v1:sha256:<64hex> --json
uv run --python 3.13 --frozen -- python -m openclaw_mem artifact peek ocm_artifact:v1:sha256:<64hex> --json
```

The `pack` response carries a stable `context_pack` field for handoff, and `artifact` commands use deterministic JSON contracts for machine parsing.

---

## Step 4.6: Dual-language memory (optional)

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem store "<original non-English text>" \
  --text-en "Preference: run integration tests before release" \
  --lang zh --category preference --importance 0.9 --json

uv run --python 3.13 --frozen -- python -m openclaw_mem hybrid "<original query>" \
  --query-en "pre-release process" \
  --limit 5 --json
```

See: `docs/dual-language-memory-strategy.md`.

---

## Step 4.7: Verbatim semantic lane for episodic evidence (optional)

```bash
DB=/tmp/openclaw-mem-proof.sqlite
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json episodes embed --scope global --limit 200
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json episodes search "routing fallback" --scope global --mode hybrid --trace
```

See: `docs/verbatim-semantic-lane.md`.

---

## Step 5: Enable the OpenClaw plugin (optional)

The plugin provides:
- auto-capture (writes tool results to JSONL)
- backend-aware annotations (when `backendMode=auto`) for memory ops observability

Ownership model:
- `memory-core` / `memory-lancedb` remain canonical memory backends
- `openclaw-mem` is sidecar capture + local recall + triage

### Option A — local checkout

```bash
openclaw plugins install -l ./extensions/openclaw-mem
openclaw gateway restart
```

---

## Next steps

- Full docs: `README.md`
- Agent memory skill: `docs/agent-memory-skill.md`
- Reality check: `docs/reality-check.md`
- Deployment: `docs/deployment.md`
- Ecosystem fit: `docs/ecosystem-fit.md`
- Changes/features: `CHANGELOG.md`
