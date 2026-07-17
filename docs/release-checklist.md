# Release checklist (repo rule)

This repo runs CI in **locked** mode:
- CI: `uv sync --locked`
- Docs build: `uv sync --locked --extra docs`

**Rule:** if you change *anything* that affects dependency resolution (including bumping the project version), you **must** update and commit `uv.lock`.

## Before tagging

1) Choose the release surface and keep only that surface aligned.
   - Python distribution/repo release:
     - `pyproject.toml` `version = ...`
     - `openclaw_mem/__init__.py` `__version__ = ...`
     - canonical `skills/**/SKILL.md` metadata
     - generated skill docs/snippets
     - the root package entry in `uv.lock`
   - `extensions/openclaw-mem` and `extensions/openclaw-mem-engine` have
     independent package versions. Bump their manifest/package pairs only when
     those packages are actually part of the release.
2) Move shipped notes from `[Unreleased]` to the dated version in
   `CHANGELOG.md` and add/update `docs/releases-vX.Y.Z.md`.
3) Update generated assets and lockfile.
   ```bash
   python scripts/generate_agent_memory_skill_assets.py
   uv lock
   ```
4) Run command-truth, docs hygiene, and locked checks.
   ```bash
   uv lock --check
   python scripts/generate_agent_memory_skill_assets.py --check
   python -m pytest -q tests/test_docs_public_hygiene.py tests/test_skill_lint.py
   uv run --locked --extra docs mkdocs build --strict
   uv run --with build -- python -m build
   ```
5) Run the full repository suite and the governed release check for the exact
   version. Do not substitute a checklist sentence for test output.
6) Confirm the release commit is on `main`, CI is green, the working tree is
   clean, and the tag does not already exist locally or remotely.
7) If the release changes `openclaw-mem-engine` runtime wiring, capture local host receipts:
   ```bash
   openclaw doctor
   openclaw status
   ```
   Capable hosts should log `openclaw-mem-engine: registered core memory runtime capability` and should not report `No active memory plugin is registered for the current config` when mem-engine owns `plugins.slots.memory`.

## Tag + release
- Create an annotated tag from verified `main`, push it, and create the GitHub
  Release from the reviewed release-notes file:
  ```bash
  git tag -a vX.Y.Z -m "openclaw-mem release vX.Y.Z"
  git push origin vX.Y.Z
  gh release create vX.Y.Z --title "openclaw-mem vX.Y.Z" \
    --notes-file docs/releases-vX.Y.Z.md --verify-tag
  ```

GitHub Release, PyPI publication, ClawHub publication, docs deployment, and a
live memory-owner cutover are separate state changes. Perform only the surfaces
explicitly authorized for that release.

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
