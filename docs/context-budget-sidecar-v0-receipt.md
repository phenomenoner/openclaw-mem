# Context Budget Sidecar v0 — RECEIPT

Implemented `openclaw-mem artifact` command group (v0): `stash`, `fetch`, `peek`.

## Commands

```bash
# 1) Stash raw output from stdin
cat tool-output.txt | openclaw-mem artifact stash --json

# 2) Stash from file path
openclaw-mem artifact stash --from ./raw-tool-output.txt --json

# 3) Stash gzip blob
openclaw-mem artifact stash --from ./raw-tool-output.txt --gzip --json

# 4) Peek metadata + tiny preview
openclaw-mem artifact peek ocm_artifact:v1:sha256:<64hex> --json

# 5) Fetch bounded text (default mode=headtail)
openclaw-mem artifact fetch ocm_artifact:v1:sha256:<64hex> --max-chars 1200 --json

# 6) Fetch raw text only (no JSON envelope)
openclaw-mem artifact fetch ocm_artifact:v1:sha256:<64hex> --mode headtail --max-chars 1200 --no-json
```

## Validation

```bash
# Requested command (fails in this env if pytest is not preinstalled)
uv run pytest

# Executed equivalent (installs pytest transiently):
uv run --with pytest pytest
```
