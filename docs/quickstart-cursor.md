# Cursor quickstart

1. Preview the project install: `openclaw-mem install --harness cursor --root . --dry-run --json`.
2. Install `mcpServers.openclaw-mem` and the skill card: `openclaw-mem install --harness cursor --root . --verify --json`.
3. Restart Cursor and inspect MCP tools in settings.
4. Diagnose later with `openclaw-mem doctor --harness cursor --root . --json`.

The default project path is `.cursor/mcp.json`, matching the [Cursor MCP documentation](https://docs.cursor.com/context/model-context-protocol). Use `--config-path ~/.cursor/mcp.json` for a global install.
