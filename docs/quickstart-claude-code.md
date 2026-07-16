# Claude Code quickstart

1. Install the project MCP entry: `openclaw-mem install --harness claude-code --root . --verify --json`.
2. Optionally add the memory skill: repeat with `--skills-dir .claude/skills`.
3. Restart Claude Code so it reloads `.mcp.json`.
4. Diagnose later with `openclaw-mem doctor --harness claude-code --root . --json`.

The installer preserves unrelated `.mcp.json` keys and never writes secrets.
