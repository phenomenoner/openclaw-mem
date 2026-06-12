# Quickstart

This is the **fastest local proof** for `openclaw-mem`.

Goal: show that the same query can produce a **smaller, safer, cited** pack once trust policy is enabled.

If you are still deciding how to adopt it, read [Choose an install path](install-modes.md) first.

## Prerequisites

- Python 3.10+ (recommended: Python 3.13)
- `pip` for the packaged CLI path
- [uv](https://github.com/astral-sh/uv) only if you want to run the repository proof fixture directly

## 1) Install the packaged CLI

```bash
python -m venv .venv
. .venv/bin/activate
pip install openclaw-context-pack
openclaw-mem --db /tmp/openclaw-mem-quickstart.sqlite status --json
```

The PyPI distribution is `openclaw-context-pack`; it installs the `openclaw_mem` Python package, the `openclaw-mem` console command, and the integration entrypoints `openclaw-mem-mcp`, `openclaw-mem-channel-a`, and `openclaw-mem-hooks`.

If you want to run the bundled synthetic fixture from this repository instead, clone the repo too:

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked
```

## 2) Ingest the synthetic proof fixture

```bash
DB=/tmp/openclaw-mem-quickstart.sqlite

openclaw-mem ingest \
  --db "$DB" \
  --json \
  --file ./docs/showcase/artifacts/trust-aware-context-pack.synthetic.jsonl
```

What this gives you:
- six synthetic rows with trust tiers, importance labels, and provenance refs
- no private or user data
- a reproducible basis for pack before/after comparison

## 3) Build the pack without trust gating

```bash
openclaw-mem pack \
  --db "$DB" \
  --query "trust-aware context packing prompt pack receipts hostile durable memory provenance" \
  --limit 5 \
  --budget-tokens 500 \
  --trace
```

Expected shape:
- a compact `bundle_text`
- `items[]` + `citations[]`
- `trace.kind = openclaw-mem.pack.trace.v1`

In the synthetic proof, this ungated pack still admits one **quarantined** row because it matches the query text.

## 4) Build the pack with trust gating on

```bash
openclaw-mem pack \
  --db "$DB" \
  --query "trust-aware context packing prompt pack receipts hostile durable memory provenance" \
  --limit 5 \
  --budget-tokens 500 \
  --trace \
  --pack-trust-policy exclude_quarantined_fail_open
```

What changes:
- the quarantined row is excluded
- a trusted row takes its place
- the pack gets smaller
- `trust_policy`, `policy_surface`, and `lifecycle_shadow` explain exactly what happened

## 5) Inspect the proof artifact

- [Canonical walkthrough](showcase/trust-aware-context-pack-proof.md)
- [Metrics JSON](showcase/artifacts/trust-aware-context-pack.metrics.json)
- [Raw receipts](showcase/artifacts/index.md)

## 6) Optional integration routes

The local proof above is the fastest path. If you are wiring an agent host, use one of these routes.

### Route A: MCP online tools

```bash
openclaw-mem-mcp --tool-descriptions
claude mcp add openclaw-mem -- openclaw-mem-mcp --db "$DB"
```

The MCP server exposes `mem_search`, `mem_pack`, `mem_store`, `mem_status`, and related tools. See [MCP integration](mcp-integration.md).

### Route B: fail-open file pack

```bash
openclaw-mem-channel-a \
  --db "$DB" \
  --input-jsonl docs/fixtures/context-pack-v1-compat/ingest-idempotency.jsonl \
  --packs-dir .state/openclaw-mem/packs \
  --agent main \
  --query "context pack compatibility"
```

The host reads `.state/openclaw-mem/packs/main/latest.json` if present and skips it if missing or invalid. See [Channel A file contract](channel-a-file-contract.md).

### Route C: lifecycle hooks

```bash
openclaw-mem-hooks install-config \
  --db "$DB" \
  --out-jsonl .state/openclaw-mem/hook-observations.jsonl \
  --packs-dir .state/openclaw-mem/packs \
  --agent main \
  --query "current session memory" \
  --out .state/openclaw-mem/hooks.json
```

Wire the generated commands into the host lifecycle slots. See [Lifecycle hooks](lifecycle-hooks.md).

## What to do next

### If the local proof was enough

- move to [Deployment guide](deployment.md)
- add the sidecar to your existing OpenClaw install

### If you are integrating with OpenClaw agents

- read the [Agent memory skill (SOP)](agent-memory-skill.md)
- review [Context pack](context-pack.md)
- add online tools with [MCP integration](mcp-integration.md)
- use fail-open pack files with [Channel A file contract](channel-a-file-contract.md)
- wire [Lifecycle hooks](lifecycle-hooks.md)
- review [Mem Engine reference](mem-engine.md)

### If you want the detailed source-checkout walkthrough

- GitHub quickstart: <https://github.com/phenomenoner/openclaw-mem/blob/main/QUICKSTART.md>
