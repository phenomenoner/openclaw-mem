# Quickstart Guide

Get `openclaw-mem` up and running in ~5 minutes.

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

**Invocation note (truthful):** from a source checkout, run the CLI as:

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
# Creates/opens a DB and prints stats
uv run --python 3.13 --frozen -- python -m openclaw_mem --json status

# Inspect active OpenClaw memory backend + fallback posture
uv run --python 3.13 --frozen -- python -m openclaw_mem --json backend
```

---

## Step 2.1: 5-minute synthetic demo (Inside-Out Memory)

This demo is **synthetic** (no private/user data) and is designed to run even
without `OPENAI_API_KEY` (FTS-only fail-open).

```bash
./scripts/inside_out_demo.sh
```

See: `docs/showcase/inside-out-demo.md`.

---

## Step 3: Ingest sample data

```bash
# Generate a tiny synthetic JSONL file (no private/user data)
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

---

## Step 4.5: Dual-language memory (optional)

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

## Step 5: Enable the OpenClaw plugin (optional)

The plugin provides:
- auto-capture (writes tool results to JSONL)
- backend-aware annotations (when `backendMode=auto`) for memory ops observability

Ownership model (important):
- `memory-core` / `memory-lancedb` remain canonical memory backends
- `openclaw-mem` is sidecar capture + local recall + triage

For explicit memory writes/reads, use CLI commands (`store`, `hybrid`, etc.).

```bash
# Symlink plugin into OpenClaw
ln -s ./extensions/openclaw-mem ~/.openclaw/plugins/openclaw-mem

# Restart gateway
openclaw gateway restart
```

Minimal config fragment for `~/.openclaw/openclaw.json`:

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem": {
        "enabled": true,
        "config": {
          "outputPath": "~/.openclaw/memory/openclaw-mem-observations.jsonl",
          "captureMessage": false,
          "redactSensitive": true,
          "backendMode": "auto",
          "annotateMemoryTools": true
        }
      }
    }
  }
}
```

Note:
- If your OpenClaw uses a non-default state dir (e.g. `OPENCLAW_STATE_DIR=/some/dir`), set `outputPath` and `tail -f` paths under that directory.

Verify capture is working:

```bash
tail -f ~/.openclaw/memory/openclaw-mem-observations.jsonl
```

Ingest captured observations:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem ingest \
  --file ~/.openclaw/memory/openclaw-mem-observations.jsonl --json
```

---

## Step 6: Deterministic triage (optional)

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem triage --mode heartbeat --json
uv run --python 3.13 --frozen -- python -m openclaw_mem triage --mode tasks --tasks-since-minutes 1440 --json
```

Task matching rules in `--mode tasks` are deterministic:
- `kind == "task"`, or
- `summary` starts with `TODO` / `TASK` / `REMINDER` (case-insensitive; NFKC width-normalized so full-width forms are accepted), in plain form (`TODO ...`) or bracketed form (`[TODO] ...`, `(TASK) ...`, `【TODO】 ...`, `〔TODO〕 ...`, `{TODO} ...`, `「TODO」 ...`, `『TODO』 ...`, `《TODO》 ...`, `«TODO» ...`, `〈TODO〉 ...`, `〖TODO〗 ...`, `〘TODO〙 ...`, `‹TODO› ...`, `<TODO> ...`, `＜TODO＞ ...`), with optional leading markdown wrappers: blockquotes (`>`; spaced `> > ...` and compact `>> ...`/`>>...` forms), list/checklist wrappers (`-` / `*` / `+` / `•` / `▪` / `‣` / `∙` / `·` / `◦` / `・` / `–` / `—` / `−`, then optional `[ ]` / `[x]` / `[✓]` / `[✔]` / `[☐]` / `[☑]` / `[☒]` / `[✅]`), and ordered-list prefixes (`1.` / `1)` / `(1)` / `a.` / `a)` / `(a)` / `iv.` / `iv)` / `(iv)`; Roman forms are canonical). Compact no-space wrapper chaining is also accepted (for example `-TODO ...`, `[x]TODO ...`, `1)TODO ...`, `[TODO]buy milk`, `【TODO】buy milk`, `〔TODO〕buy milk`, `{TODO}buy milk`, `「TODO」buy milk`, `『TODO』buy milk`, `《TODO》buy milk`, `«TODO»buy milk`, `〈TODO〉buy milk`, `〖TODO〗buy milk`, `〘TODO〙buy milk`, `‹TODO›buy milk`, `<TODO>buy milk`, `＜TODO＞buy milk`), followed by `:`, `：`, `;`, `；`, whitespace, `-`, `.`, `。`, `－`, `–`, `—`, `−`, or end-of-string.
- Example formats: `TODO: rotate runbook`, `{TODO}: rotate runbook`, `【TODO】 rotate runbook`, `「TODO」 rotate runbook`, `『TODO』 rotate runbook`, `《TODO》 rotate runbook`, `«TODO» rotate runbook`, `〈TODO〉 rotate runbook`, `〖TODO〗 rotate runbook`, `〘TODO〙 rotate runbook`, `‹TODO› rotate runbook`, `<TODO> rotate runbook`, `＜TODO＞rotate runbook`, `task- check alerts`, `(TASK): review PR`, `- [ ] TODO file patch`, `> TODO follow up with vendor`, `>>[x]TODO: compact wrappers`, `TODO; rotate runbook`, `TASK；follow up on release checklist`.
- More accepted compact examples: `> - (1) [ ] TASK: clean desk`, `>> (iv) [ ] TODO: clean desk`.
- Example run:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem triage --mode tasks --tasks-since-minutes 1440 --importance-min 0.7 --json
```

---

## Step 6.5: Recommendation-only memory health review (optional)

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem optimize review --json --limit 500
```

This command is zero-write by design in v0.1: it only reports candidates (staleness, duplication, bloat, weakly-connected memories, repeated no-result `memory_recall` misses) and suggestions.

## Step 7: Autograde toggle (optional)

`openclaw-mem` can auto-score importance during ingest/harvest with `heuristic-v1`.

Enable per-command:

```bash
# aliases accepted: heuristic_v1, heuristic_v2
OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1 uv run --python 3.13 --frozen -- python -m openclaw_mem harvest --file /tmp/incoming.jsonl --json --no-embed
```

Disable for a one-off run (kill-switch):

```bash
OPENCLAW_MEM_IMPORTANCE_SCORER=off uv run --python 3.13 --frozen -- python -m openclaw_mem harvest --file /tmp/incoming.jsonl --json --no-embed
```

Or override only this command:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem harvest --file /tmp/incoming.jsonl --json --no-embed --importance-scorer off
```

## Step 8: Graphic Memory automation knobs (optional, dev)

Graphic Memory automation toggles are opt-in (default OFF):

- `OPENCLAW_MEM_GRAPH_AUTO_RECALL=1` for deterministic preflight recall packs
- `OPENCLAW_MEM_GRAPH_AUTO_CAPTURE=1` for recurring git commit capture
- `OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD=1` for markdown heading indexing

Inspect effective toggle state:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem graph auto-status --json
```

Examples:

```bash
# Preflight recall pack (bounded context bundle)
OPENCLAW_MEM_GRAPH_AUTO_RECALL=1 uv run --python 3.13 --frozen -- python -m openclaw_mem graph preflight "slow-cook benchmark drift" --scope openclaw-mem --take 12 --budget-tokens 1200

# Capture recent repo commits as observations
OPENCLAW_MEM_GRAPH_AUTO_CAPTURE=1 uv run --python 3.13 --frozen -- python -m openclaw_mem graph capture-git --repo /root/.openclaw/workspace/openclaw-mem-dev --since 24 --max-commits 50 --json

# Capture markdown heading sections (index-only)
OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD=1 uv run --python 3.13 --frozen -- python -m openclaw_mem graph capture-md --path /root/.openclaw/workspace/lyria-working-ledger --include .md --since-hours 24 --json
```

Spec: `docs/specs/graphic-memory-auto-capture-auto-recall.md`

## Step 8.5: Topology query smoke test (optional, dev)

Load the curated topology fixture and run one deterministic query:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem graph topology-refresh --file ./docs/topology.json --json
uv run --python 3.13 --frozen -- python -m openclaw_mem graph query subgraph project.openclaw-mem --depth 1 --limit 20 --json
```

Use this when you want a quick read-only check that topology refresh + query plumbing is alive before deeper graph/drift debugging.


## Step 8.6: Topology extract + diff smoke test (optional, dev)

Generate a deterministic seed from your workspace, then compare it with curated topology (suggest-only):

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem graph topology-extract --workspace /root/.openclaw/workspace --cron-jobs /root/.openclaw/cron/jobs.json --out /tmp/topology-seed.json --json
uv run --python 3.13 --frozen -- python -m openclaw_mem graph topology-diff --seed /tmp/topology-seed.json --curated ./docs/topology.json --limit 20 --json
```

Use this to spot missing/stale topology entities before promoting updates into curated docs.

## Next steps

- Full docs: `README.md`
- Agent memory skill (SOP/manual): `docs/agent-memory-skill.md`
- Agent memory skill cards (global + read-only carve-out):
  - `skills/agent-memory-skill.global.md`
  - `skills/agent-memory-skill.readonly.md`
- Prompt wiring templates (real OpenClaw prompt surfaces):
  - `docs/snippets/openclaw-agentturn-message.global-default.md`
  - `docs/snippets/openclaw-agentturn-message.watchdog-readonly.md`
  - helper: `scripts/json_escape.py`
- Reality check & status: `docs/reality-check.md`
- Plugin details: `docs/auto-capture.md`
- Deployment: `docs/deployment.md`
- Ecosystem fit: `docs/ecosystem-fit.md`
- Changes/features: `CHANGELOG.md`
- Graphic Memory knobs/spec: `docs/specs/graphic-memory-auto-capture-auto-recall.md`

## Tests

```bash
uv run --python 3.13 --frozen -- python -m unittest discover -s tests -p 'test_*.py'
```
