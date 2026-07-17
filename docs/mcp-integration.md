# MCP integration

`openclaw-mem` ships a small stdio MCP server for host agents that can consume Model Context Protocol tools.

The server is intentionally narrow:

- stable tool descriptions suitable for hash pinning
- local SQLite only
- fail-open behavior at the host boundary
- ContextPack v1 output for bounded prompt injection

## Install

```bash
pip install openclaw-context-pack
```

The distribution installs `openclaw-mem-mcp`.

## Claude Code style add command

```bash
claude mcp add openclaw-mem -- openclaw-mem-mcp --db /path/to/openclaw-mem.sqlite
```

From a checkout:

```bash
claude mcp add openclaw-mem -- uv run --python 3.13 --frozen openclaw-mem-mcp --db /path/to/openclaw-mem.sqlite
```

## Tools

- `mem_search`: compact cited search over observations
- `mem_recall`: unified fail-open lexical/vector/hybrid/graph recall receipt
- `mem_timeline`: recent observations in timestamp order
- `mem_get`: one observation by `obs:<id>` or numeric id
- `mem_pack`: bounded `openclaw-mem.context-pack.v1` using the complete CLI
  trust, quota, lifecycle, scoring, and trace policy path
- `mem_store`: local observation write without requiring embeddings
- `mem_status`: store counts and latency receipt
- `mem_trust_inspect`: trust metadata and pack-eligibility hint
- `graph_neighbors`: bounded neighbors for one graph node
- `graph_path`: bounded path between two graph nodes
- `graph_impact`: bounded downstream impact traversal

Generate the stable tool-description hash manifest:

```bash
openclaw-mem-mcp --tool-descriptions --json
```

The committed release fixture is `docs/fixtures/mcp-tool-descriptions.v1.json`.

The manifest includes:

- `contractVersion`
- `descriptionSha256`
- `inputSchemaSha256`
- `approvalRequired`
- `readOnly`
- `timeoutMs`
- a stable error shape for host fail-open handling

`mem_store` is the only write-capable tool in the default set and is marked
`approvalRequired=true`. Recall/search, graph queries, timeline, get, pack,
status, and trust inspect are read-only. Invalid parameters and backend
degradation return actionable hints rather than host-level tracebacks.

## Contract posture

Use MCP for online recall/pack calls where the host has a warm stdio process. Use Channel A for offline, file-based, fail-open pack injection. If MCP fails or exceeds a host latency budget, the host should fall back to the latest Channel A pack.

## Verification

```bash
uv run --python 3.13 --frozen pytest tests/test_mcp_server.py
```
