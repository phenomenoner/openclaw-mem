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

## Optional ClawHub marketplace publish

Default marketplace posture is **sidecar-first**:

- Update the existing bundle slug: `openclaw-mem-lyria`.
- Bundle only the lightweight `extensions/openclaw-mem` capture plugin plus docs.
- Do **not** publish `openclaw-mem-engine` as the default marketplace path; point advanced users to GitHub after they deliberately choose the memory-slot migration boundary.

Prepare a small bundle staging folder with:

- `openclaw.bundle.json`
- `package.json` with `name: "openclaw-mem-lyria"`
- `README.md` explaining sidecar-first install, config, rollback, and GitHub engine path
- `extensions/openclaw-mem/`
- selected docs such as `QUICKSTART.md`, `CHANGELOG.md`, `docs/auto-capture.md`, `docs/install-modes.md`, `docs/deployment.md`, and `docs/mem-engine.md`

Publish the bundle:

```bash
clawhub package publish <bundle-staging-folder> \
  --family bundle-plugin \
  --name openclaw-mem-lyria \
  --display-name "OpenClaw Mem" \
  --version X.Y.Z \
  --changelog "<short release note>" \
  --bundle-format directory \
  --host-targets openclaw \
  --source-repo phenomenoner/openclaw-mem \
  --source-commit <git-sha> \
  --source-ref vX.Y.Z
```

Install command shown by ClawHub should remain:

```bash
openclaw bundles install clawhub:openclaw-mem-lyria
```

Engine publication can be reopened later as a separate product surface, but it is not the default release checklist item.

## Why this exists
We prefer reproducible builds. Locked-mode CI will fail fast if `uv.lock` is stale.
