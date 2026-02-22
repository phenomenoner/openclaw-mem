# Graphic Memory v0 automation knobs: auto-recall + auto-capture

## Status
- Version: v0
- Scope: `openclaw-mem` CLI + operator automation
- Defaults: **OFF** (opt-in)

## Environment switches

### `OPENCLAW_MEM_GRAPH_AUTO_RECALL`
- Default: `0` / unset (disabled)
- When enabled (`1`, `true`, `on`), agents/operators can run a preflight recall step before deeper reasoning:
  - `openclaw-mem graph preflight "<query>" ...`
- Purpose: produce a bounded, deterministic context bundle with no manual id curation.

### `OPENCLAW_MEM_GRAPH_AUTO_CAPTURE`
- Default: `0` / unset (disabled)
- When enabled, operators can schedule recurring capture of recent git commits into the observation store:
  - `openclaw-mem graph capture-git --repo <path> ...`
- Purpose: let Graphic Memory grow naturally from day-to-day code activity.

> v0 note: switches are operational toggles used by wrappers/cron/agent policy. They do **not** force automatic background jobs by themselves.

## Commands

### 1) Auto-recall preflight: `graph preflight`
```bash
openclaw-mem graph preflight "slow-cook benchmark drift" \
  --scope openclaw-mem \
  --limit 12 \
  --window 2 \
  --suggest-limit 6 \
  --take 12 \
  --budget-tokens 1200
```

Behavior:
- Runs the same retrieval logic as `graph index`.
- Deterministically selects refs in this order:
  1. `top_candidates`
  2. `suggested_next_expansions`
- Dedupe + `--take` cap.
- Internally runs `graph pack` with the selected refs.

Output:
- default text mode: only `bundle_text` (prompt-ready)
- `--json`: `openclaw-mem.graph.preflight.v0` payload with query, selection, index summary, and embedded pack output.

### 2) Auto-capture from git: `graph capture-git`
```bash
openclaw-mem graph capture-git \
  --repo /path/to/openclaw-mem \
  --repo /path/to/openclaw-async-coding-playbook \
  --since 24 \
  --max-commits 50 \
  --state ~/.openclaw/memory/openclaw-mem/graph-capture-state.json \
  --json
```

Behavior:
- For each repo, scans commits since last state cursor (`last_author_ts`) or `--since` fallback.
- Inserts one observation per commit:
  - `kind=note`
  - `tool_name=graph.capture-git`
  - `summary=[GIT] <repo> <sha7> <subject>`
  - `detail_json={repo, sha, author_ts, files[]}`
- Idempotent by `(repo, sha)` via seen-table + existing-observation check.
- Returns aggregate-only counters per repo:
  - `inserted`
  - `skipped_existing`
  - `errors`

## Safety posture (v0)
- **No diff hunks** are stored.
- **No file contents** are stored.
- Only high-level commit metadata + changed file paths are captured.
- Output/trace remains redaction-safe and aligned with progressive disclosure.

## Cron examples

### Auto-capture (hourly)
```bash
OPENCLAW_MEM_GRAPH_AUTO_CAPTURE=1 \
openclaw-mem graph capture-git \
  --repo /root/.openclaw/workspace/openclaw-mem-dev \
  --repo /root/.openclaw/workspace/openclaw-async-coding-playbook \
  --since 24 \
  --max-commits 50 \
  --json
```

### Auto-recall preflight in a job/pipeline
```bash
OPENCLAW_MEM_GRAPH_AUTO_RECALL=1 \
openclaw-mem graph preflight "${QUERY}" \
  --scope "${PROJECT}" \
  --take 12 \
  --budget-tokens 1200
```

## Agent prompt snippet

Use this snippet in agent scaffolds when `OPENCLAW_MEM_GRAPH_AUTO_RECALL=1`:

```text
Before answering, run a Graphic Memory preflight pack for the user query.
- Command: openclaw-mem graph preflight "<user_query>" --scope <project_or_repo> --take 12 --budget-tokens 1200
- Inject the returned bundle_text as bounded context.
- If preflight returns empty, continue normally (fail-open).
```

This keeps recall deterministic, bounded, and optional.
