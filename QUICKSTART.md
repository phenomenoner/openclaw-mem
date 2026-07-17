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
uv run --python 3.13 --frozen -- python -m openclaw_mem init --json
uv run --python 3.13 --frozen -- python -m openclaw_mem --json doctor
uv run --python 3.13 --frozen -- python -m openclaw_mem db info --json
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

Optional operator handoff template:

```bash
./scripts/operator_template_demo.sh
```

---

## Step 3: Ingest sample data

```bash
python3 ./scripts/make_sample_jsonl.py --out ./sample.jsonl
uv run --python 3.13 --frozen -- python -m openclaw_mem ingest --file ./sample.jsonl --json
```

---

## Step 4: Primary recall, with legacy drill-down available

Use the v2 primary entrypoint first:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem recall "OpenClaw" --mode auto --json
```

The compatibility drill-down commands remain available through `--help-all`:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem search "OpenClaw" --limit 10 --json
uv run --python 3.13 --frozen -- python -m openclaw_mem timeline 2 --window 2 --json
uv run --python 3.13 --frozen -- python -m openclaw_mem get 1 --json
```

The compatibility drill-down is useful when debugging a result:
- **recall** routes the normal agent query and reports its selected/fallback lane
- **search** finds lexical candidate memory
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

### Step 4.5b: Command-aware compaction, bounded raw recovery

```bash
# Raw + compact outputs from your own toolchain
printf 'diff --git a/a.py b/a.py\n-foo\n+bar\n' > ./raw-git-diff.txt
printf 'M a.py (+1 -1)\n' > ./compact-git-diff.txt

uv run --python 3.13 --frozen -- python -m openclaw_mem artifact compact-receipt \
  --command "git diff --stat" \
  --tool rtk \
  --compact-file ./compact-git-diff.txt \
  --raw-file ./raw-git-diff.txt \
  --json > ./compaction-receipt.json

uv run --python 3.13 --frozen -- python -m openclaw_mem artifact rehydrate \
  --receipt-file ./compaction-receipt.json \
  --max-chars 120 \
  --json
```

What this proves:
- compacted command output can be stored as an Observe-side sideband receipt
- the receipt keeps a deterministic pointer back to bounded raw evidence
- family metadata is attached advisory-only (`git_diff`, `test_failures`, `long_logs`, `generic`)
- later `pack` runs can prefer compact evidence without losing raw recovery
- `pack` can emit advisory `compaction_policy_hints` for operator guidance without mutating retrieval ranking

See also:
- `docs/showcase/command-aware-compaction-proof.md`
- `docs/specs/compaction-family-policy-cards-v0.md`

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

## Step 4.6b: Harness-safe command probes (optional)

When running inside an agent harness checkout, pass the harness home explicitly.
This lets the CLI resolve the harness memory DB and embedding credential env file
without printing secret values:

```bash
openclaw-mem --harness-home /path/to/.agent-harness status --json
openclaw-mem pack --harness-home /path/to/.agent-harness --query "current memory posture" --limit 5 --json
openclaw-mem --harness-home /path/to/.agent-harness service-store init --json
openclaw-mem --harness-home /path/to/.agent-harness writeback-store init --json
openclaw-mem --json graph topology-extract --harness-home /path/to/.agent-harness --workspace /path/to/.agent-harness/workspace
```

For isolated test databases, use DB-only store mode so smoke tests do not append
Markdown notes to the operator workspace:

```bash
openclaw-mem store --db /tmp/openclaw-mem-smoke.sqlite \
  --text "temp store isolation smoke" \
  --no-file-write \
  --json
```

Contract-first cutover probes are read-only and shadow-only:

```bash
openclaw-mem service status --json
openclaw-mem service lease --owner agent-harness --ttl-ms 60000 --json
openclaw-mem qdrant status --json
openclaw-mem qdrant recall --db /path/to/.agent-harness/memory/openclaw-mem.sqlite --vector "[0.1]" --json
```

`service-store init` and `writeback-store init` create empty readiness JSONL files only. Qdrant vector recall is optional and fail-closed; it reports a fallback when the local shard or `qdrant_edge` dependency is unavailable.

See:
- `docs/specs/context-pack-schema-compatibility-v1.md`
- `docs/specs/remote-mem-engine-service-contract-v0.md`
- `docs/specs/native-qdrant-recall-contract-v0.md`

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

If you are promoting the optional mem-engine from a source checkout, install its local Node deps first:

```bash
cd extensions/openclaw-mem-engine
npm install
cd ../..
openclaw plugins install -l ./extensions/openclaw-mem-engine
openclaw gateway restart
```

On OpenClaw hosts that expose the core memory runtime capability, `openclaw-mem-engine`
also registers as the active core memory runtime. That makes doctor/status and core
memory-search probes recognize the engine while the existing `memory_store`,
`memory_recall`, docs cold-lane, auto-capture, and prompt-hook behavior remain intact.

Compatibility note: older OpenClaw hosts that do not expose
`registerMemoryCapability`/`registerMemoryRuntime` continue to run the plugin through
its tools and hooks. In that case the engine logs that core runtime registration was
skipped; this is a host capability limit, not data loss.

Useful verification after restart:

```bash
openclaw doctor
openclaw status
```

Expect plugin logs to include `openclaw-mem-engine: registered core memory runtime capability`
on capable hosts. If the core `memory` CLI surface is disabled by `plugins.allow`, use
doctor/status plus the plugin's direct tools as the verification path.

---

## Step 7: Autograde toggle (optional)

`openclaw-mem` can auto-score importance during ingest/harvest with `heuristic-v1`.

Enable per-command:

```bash
OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1 uv run python -m openclaw_mem harvest --file /tmp/incoming.jsonl --json --no-embed
```

Disable for a one-off run (kill-switch):

```bash
OPENCLAW_MEM_IMPORTANCE_SCORER=off uv run python -m openclaw_mem harvest --file /tmp/incoming.jsonl --json --no-embed
```

Or override only this command:

```bash
uv run python -m openclaw_mem harvest --file /tmp/incoming.jsonl --json --no-embed --importance-scorer off
```

## Next steps

- Full docs: `README.md`
- Agent memory skill: `docs/agent-memory-skill.md`
- Reality check: `docs/reality-check.md`
- Deployment: `docs/deployment.md`
- Ecosystem fit: `docs/ecosystem-fit.md`
- Changes/features: `CHANGELOG.md`
