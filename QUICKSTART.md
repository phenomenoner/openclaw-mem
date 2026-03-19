# Quickstart Guide

Get `openclaw-mem` up and running in ~5 minutes.

This guide is the **fastest local proof** for the sharper product wedge:

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

**Run from source:** when using a source checkout, invoke the CLI as:

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

What this proves:
- the local ledger is alive
- the CLI surface is working
- you can inspect memory posture before wiring anything deeper

---

## Step 2.1: Canonical trust-aware pack proof (synthetic)

This is the cleanest showcase path when you want the wedge directly instead of a generic smoke test.

It is **synthetic** (no private/user data). It demonstrates that the **same query** can produce a safer pack once trust policy is enabled.

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

uv run --python 3.13 --frozen -- python -m openclaw_mem pack \
  --db "$DB" \
  --query "trust-aware context packing prompt pack receipts hostile durable memory provenance" \
  --limit 5 \
  --budget-tokens 500 \
  --trace \
  --pack-trust-policy exclude_quarantined_fail_open
```

See:
- `docs/showcase/trust-aware-context-pack-proof.md`
- `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`
- `docs/showcase/inside-out-demo.md` for the companion narrative demo

---

## Step 3: Ingest sample data

```bash
# Generate a tiny synthetic JSONL file (no private/user data)
python3 ./scripts/make_sample_jsonl.py --out ./sample.jsonl

uv run --python 3.13 --frozen -- python -m openclaw_mem ingest --file ./sample.jsonl --json
```

What to expect:
- inserted row counts
- stable IDs / receipts you can inspect later

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

If your real question is “what changed?” or “why are we still doing this?”, this is the loop you want to prove first.

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
          "annotateMemoryTools": true,
          "excludeAgents": ["cron-watchdog", "healthcheck"]
        }
      }
    }
  }
}
```

Note:
- If your OpenClaw uses a non-default state dir (e.g. `OPENCLAW_STATE_DIR=/some/dir`), set `outputPath` and `tail -f` paths under that directory.
- `excludeAgents` is the bounded per-agent carve-out for sidecar capture; matching is exact on OpenClaw agent id.
- Rollback is one-line: remove the id from `excludeAgents` (or remove the key entirely).

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
- `summary` starts with `TODO` / `TASK` / `REMINDER` (case-insensitive; NFKC width-normalized so full-width forms are accepted), in plain form (`TODO ...`) or bracketed form (`[TODO] ...`, `(TASK) ...`, `【TODO】 ...`, `〔TODO〕 ...`, `{TODO} ...`, `｛TODO｝ ...`, `［TODO］ ...`, `「TODO」 ...`, `『TODO』 ...`, `《TODO》 ...`, `«TODO» ...`, `〈TODO〉 ...`, `〖TODO〗 ...`, `〘TODO〙 ...`, `‹TODO› ...`, `<TODO> ...`, `＜TODO＞ ...`), with optional leading markdown wrappers: blockquotes (`>`; spaced `> > ...` and compact `>> ...`/`>>...` forms), list/checklist wrappers (`-` / `*` / `+` / `•` / `▪` / `‣` / `∙` / `·` / `◦` / `・` / `–` / `—` / `−`, then optional `[ ]` / `[x]` / `[✓]` / `[✔]` / `[☐]` / `[☑]` / `[☒]` / `[✅]`), and ordered-list prefixes (`1.` / `1)` / `(1)` / `a.` / `a)` / `(a)` / `iv.` / `iv)` / `(iv)`; Roman forms are canonical). Compact no-space wrapper chaining is also accepted (for example `-TODO ...`, `[x]TODO ...`, `1)TODO ...`, `[TODO]buy milk`, `【TODO】buy milk`, `〔TODO〕buy milk`, `{TODO}buy milk`, `｛TODO｝buy milk`, `［TODO］buy milk`, `「TODO」buy milk`, `『TODO』buy milk`, `《TODO》buy milk`, `«TODO»buy milk`, `〈TODO〉buy milk`, `〖TODO〗buy milk`, `〘TODO〙buy milk`, `‹TODO›buy milk`, `<TODO>buy milk`, `＜TODO＞buy milk`), followed by `:`, `：`, `;`, `；`, whitespace, `-`, `.`, `。`, `－`, `–`, `—`, `−`, or end-of-string.
- Example formats: `TODO: rotate runbook`, `{TODO}: rotate runbook`, `｛TODO｝: rotate runbook`, `［TODO］ rotate runbook`, `【TODO】 rotate runbook`, `「TODO」 rotate runbook`, `『TODO』 rotate runbook`, `《TODO》 rotate runbook`, `«TODO» rotate runbook`, `〈TODO〉 rotate runbook`, `〖TODO〗 rotate runbook`, `〘TODO〙 rotate runbook`, `‹TODO› rotate runbook`, `<TODO> rotate runbook`, `＜TODO＞rotate runbook`, `task- check alerts`, `(TASK): review PR`, `- [ ] TODO file patch`, `> TODO follow up with vendor`, `>>[x]TODO: compact wrappers`, `TODO; rotate runbook`, `TASK；follow up on release checklist`.
- More accepted compact examples: `> - (1) [ ] TASK: clean desk`, `>> (iv) [ ] TODO: clean desk`.
- Additional bullet-wrapper examples: `● TODO rotate runbook`, `○[x] TODO clean desk`.
- See `docs/upgrade-checklist.md` for the full matcher contract and exhaustive accepted forms.
- Example run:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem triage --mode tasks --tasks-since-minutes 1440 --importance-min 0.7 --json
```

---

## Step 6.5: Recommendation-only memory health review (optional)

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem optimize review --json --limit 500
```

This command is zero-write by design in the current release: it only reports candidates (staleness, duplication, bloat, weakly-connected memories, repeated no-result `memory_recall` misses) and suggestions.

If you are using importance grading, this is one of the easiest operator checks for “is bad memory starting to crowd out the good stuff?”

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
uv run --python 3.13 --frozen -- python -m openclaw_mem --json graph auto-status
```

Examples:

```bash
# Preflight recall pack (bounded context bundle)
OPENCLAW_MEM_GRAPH_AUTO_RECALL=1 uv run --python 3.13 --frozen -- python -m openclaw_mem graph preflight "slow-cook benchmark drift" --scope openclaw-mem --take 12 --budget-tokens 1200

# Capture recent repo commits as observations
OPENCLAW_MEM_GRAPH_AUTO_CAPTURE=1 uv run --python 3.13 --frozen -- python -m openclaw_mem --json graph capture-git --repo /root/.openclaw/workspace/openclaw-mem-dev --since 24 --max-commits 50

# Capture markdown heading sections (index-only)
OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD=1 uv run --python 3.13 --frozen -- python -m openclaw_mem --json graph capture-md --path /root/.openclaw/workspace/lyria-working-ledger --include .md --since-hours 24
```

Spec: `docs/specs/graphic-memory-auto-capture-auto-recall.md`

## Step 8.5: Topology query smoke test (optional, dev)

Load the curated topology fixture and run one deterministic query:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem --json graph query upstream artifact.daily-mission --topology ./docs/topology.json
uv run --python 3.13 --frozen -- python -m openclaw_mem --json graph query filter --tag background --not-tag human_facing --node-type cron_job --topology ./docs/topology.json
uv run --python 3.13 --frozen -- python -m openclaw_mem --json graph topology-refresh --file ./docs/topology.json
uv run --python 3.13 --frozen -- python -m openclaw_mem --json graph query subgraph project.openclaw-mem --hops 1 --max-nodes 20 --max-edges 40
```

Use the `--topology` queries for the Stage-1 read-only helper slice when you want one-hop answers directly from structured topology truth, before building the derived SQLite cache for deeper graph/drift debugging.


## Step 8.6: Topology extract + diff smoke test (optional, dev)

Generate a deterministic seed from your workspace, then compare it with curated topology (suggest-only):

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem graph topology-extract --workspace /root/.openclaw/workspace --cron-jobs /root/.openclaw/cron/jobs.json --out /tmp/topology-seed.json --json
uv run --python 3.13 --frozen -- python -m openclaw_mem graph topology-diff --seed /tmp/topology-seed.json --curated ./docs/topology.json --limit 20 --json
```

Tip: If your OpenClaw state dir is default (/root/.openclaw), you can omit --cron-jobs; topology-extract auto-reads /root/.openclaw/cron/jobs.json.

Use this to spot missing/stale topology entities before promoting updates into curated docs.

## Step 8.7: Provenance concentration quick slice (optional, dev)

Use provenance concentration views when you need to inspect where edges come from without drilling into one anchor at a time.

    uv run --python 3.13 --frozen -- python -m openclaw_mem graph query provenance --group-by-source --limit 10 --json
    uv run --python 3.13 --frozen -- python -m openclaw_mem graph query provenance --group-by-source --source-path docs/topology.json --limit 10 --json
    uv run --python 3.13 --frozen -- python -m openclaw_mem graph query provenance --source-path-prefix docs/topology/ --limit 10 --json

The first command gives path-level concentration. The second narrows to one exact source path while still returning edge-type breakdowns. The third scopes to a path family prefix before `#anchor` suffixes are considered.

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
