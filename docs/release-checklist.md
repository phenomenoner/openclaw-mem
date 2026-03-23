# Release checklist (repo rule)

This repo runs CI in **locked** mode:
- CI: `uv sync --locked`
- Docs build: `uv sync --locked --extra docs`

**Rule:** if you change *anything* that affects dependency resolution (including bumping the project version), you **must** update and commit `uv.lock`.

## Before tagging
1) Bump versions (keep them aligned)
   - `pyproject.toml` `version = ...`
   - `openclaw_mem/__init__.py` `__version__ = ...`
   - `extensions/openclaw-mem/openclaw.plugin.json` `version`
   - `extensions/openclaw-mem/package.json` `version`
   - `extensions/openclaw-mem-engine/openclaw.plugin.json` `version` (when releasing the engine package)
   - `extensions/openclaw-mem-engine/package.json` `version` (when releasing the engine package)
2) Update `CHANGELOG.md`
3) Update lockfile
   ```bash
   uv lock
   git add uv.lock
   ```
4) Sanity check (locked)
   ```bash
   uv sync --locked
   uv sync --locked --extra docs
   ```

## Tag + release
- Create annotated tag and push:
  ```bash
  git tag -a vX.Y.Z -m "openclaw-mem release vX.Y.Z"
  git push origin vX.Y.Z
  ```
- Create GitHub Release page (notes from CHANGELOG).

## Optional ClawHub package publish (`extensions/openclaw-mem` / `extensions/openclaw-mem-engine`)
If the plugin packages are part of the release, publish from the plugin folders rather than the repo root:

```bash
clawhub package publish ./extensions/openclaw-mem \
  --family code-plugin \
  --name @phenomenoner/openclaw-mem \
  --display-name "OpenClaw Mem" \
  --version X.Y.Z \
  --changelog "<short release note>" \
  --tags latest \
  --source-repo phenomenoner/openclaw-mem \
  --source-commit <git-sha> \
  --source-ref main \
  --source-path extensions/openclaw-mem
```

```bash
clawhub package publish ./extensions/openclaw-mem-engine \
  --family code-plugin \
  --name @phenomenoner/openclaw-mem-engine \
  --display-name "OpenClaw Mem Engine" \
  --version 0.0.1 \
  --changelog "<short release note>" \
  --tags latest \
  --source-repo phenomenoner/openclaw-mem \
  --source-commit <git-sha> \
  --source-ref main \
  --source-path extensions/openclaw-mem-engine
```

## Why this exists
We prefer reproducible builds. Locked-mode CI will fail fast if `uv.lock` is stale.
