# Generic harness quickstart

1. Preview: `openclaw-mem install --harness generic --root . --dry-run --json`.
2. Install the portable skill: `openclaw-mem install --harness generic --root . --verify --json`.
3. Configure the harness's stdio MCP command as `openclaw-mem-mcp`.
4. Diagnose later with `openclaw-mem doctor --harness generic --root . --json`.

Override the portable skill root with `--skills-dir`.
