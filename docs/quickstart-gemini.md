# Gemini CLI quickstart

1. Preview: `openclaw-mem install --harness gemini --root ~ --dry-run --json`.
2. Install `mcpServers.openclaw-mem` and the skill card: `openclaw-mem install --harness gemini --root ~ --verify --json`.
3. Restart Gemini CLI and run `/mcp` to inspect the connection.
4. Diagnose later with `openclaw-mem doctor --harness gemini --root ~ --json`.

The default user path is `~/.gemini/settings.json`, matching the [Gemini CLI configuration documentation](https://google-gemini.github.io/gemini-cli/docs/get-started/configuration.html). Override it with `--config-path` if your installation differs.
