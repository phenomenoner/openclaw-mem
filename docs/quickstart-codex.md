# Codex quickstart

1. Preview: `openclaw-mem install --harness codex --dry-run --json`.
2. Install the managed global card: `openclaw-mem install --harness codex --mode write --verify --json`.
3. Restart Codex so it reloads `AGENTS.md`.
4. Diagnose later with `openclaw-mem doctor --harness codex --json`.

Use `--root` or `--config-path` for an isolated/project install. Human content outside the managed block is preserved.
