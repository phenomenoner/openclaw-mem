# Windsurf quickstart

1. Preview: `openclaw-mem install --harness windsurf --root ~ --dry-run --json`.
2. Install `mcpServers.openclaw-mem` and the skill card: `openclaw-mem install --harness windsurf --root ~ --verify --json`.
3. Restart Windsurf and inspect Cascade > MCP Servers.
4. Diagnose later with `openclaw-mem doctor --harness windsurf --root ~ --json`.

The default user path is `~/.codeium/windsurf/mcp_config.json`, matching the [Windsurf MCP documentation](https://docs.windsurf.com/windsurf/cascade/mcp). Override it with `--config-path` if your installation differs.
