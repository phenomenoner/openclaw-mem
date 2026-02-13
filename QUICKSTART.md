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
uv run python -m openclaw_mem ...
```

If you have a packaged install that provides the console script, you can use:

```bash
openclaw-mem ...
```

---

## Step 2: Quick test

```bash
# Creates/opens a DB and prints stats
uv run python -m openclaw_mem --json status

# Inspect active OpenClaw memory backend + fallback posture
uv run python -m openclaw_mem --json backend
```

---

## Step 3: Ingest sample data

```bash
cat > /tmp/sample.jsonl <<'EOF'
{"ts":"2026-02-05T10:00:00Z","kind":"tool","tool_name":"web_search","summary":"searched for OpenClaw","detail":{"results":5}}
{"ts":"2026-02-05T10:01:00Z","kind":"tool","tool_name":"web_fetch","summary":"fetched openclaw.ai","detail":{"ok":true}}
{"ts":"2026-02-05T10:02:00Z","kind":"tool","tool_name":"exec","summary":"ran git status","detail":{"exit_code":0}}
EOF

uv run python -m openclaw_mem ingest --file /tmp/sample.jsonl --json
```

---

## Step 4: Progressive recall (search → timeline → get)

```bash
uv run python -m openclaw_mem search "OpenClaw" --limit 10 --json
uv run python -m openclaw_mem timeline 2 --window 2 --json
uv run python -m openclaw_mem get 1 --json
```

---

## Step 4.5: Dual-language memory (optional)

```bash
uv run python -m openclaw_mem store "<original non-English text>" \
  --text-en "Preference: run integration tests before release" \
  --lang zh --category preference --importance 0.9 --json

uv run python -m openclaw_mem hybrid "<original query>" \
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
ln -s "$(pwd)/extensions/openclaw-mem" ~/.openclaw/plugins/openclaw-mem

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
uv run python -m openclaw_mem ingest \
  --file ~/.openclaw/memory/openclaw-mem-observations.jsonl --json
```

---

## Step 6: Deterministic triage (optional)

```bash
uv run python -m openclaw_mem triage --mode heartbeat --json
```

---

## Next steps

- Full docs: `README.md`
- Reality check & status: `docs/reality-check.md`
- Plugin details: `docs/auto-capture.md`
- Deployment: `docs/deployment.md`
- Ecosystem fit: `docs/ecosystem-fit.md`
- Changes/features: `CHANGELOG.md`

## Tests

```bash
uv run --python 3.13 -- python -m unittest discover -s tests -p 'test_*.py'
```
