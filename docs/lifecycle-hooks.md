# Lifecycle hooks

`openclaw-mem` provides fail-open hook helpers for hosts that expose lifecycle events such as SessionStart, PostToolUse, and SessionEnd.

The hook helpers are plain CLI commands so they can be wired into Claude Code style hook configs or other local agent supervisors.

## Generate config

```bash
openclaw-mem-hooks install-config \
  --db /path/to/openclaw-mem.sqlite \
  --out-jsonl .state/openclaw-mem/hook-observations.jsonl \
  --packs-dir .state/openclaw-mem/packs \
  --agent main \
  --query "current session memory" \
  --out .state/openclaw-mem/hooks.json
```

## Hook commands

Read the latest Channel A pack at session start:

```bash
openclaw-mem-hooks session-start --packs-dir .state/openclaw-mem/packs --agent main
```

Append one tool-use observation from stdin:

```bash
openclaw-mem-hooks post-tool-use --out-jsonl .state/openclaw-mem/hook-observations.jsonl --agent main
```

Produce the next latest pack at session end:

```bash
openclaw-mem-hooks session-end \
  --db /path/to/openclaw-mem.sqlite \
  --input-jsonl .state/openclaw-mem/hook-observations.jsonl \
  --packs-dir .state/openclaw-mem/packs \
  --agent main \
  --query "current session memory"
```

## Safety posture

- hooks are fail-open
- observations are append-only JSONL before ingest
- private markers are skipped by Channel A
- missing packs return `packFound=false` instead of failing the host session

## Verification

```bash
uv run --python 3.13 --frozen pytest tests/test_hooks.py
```
