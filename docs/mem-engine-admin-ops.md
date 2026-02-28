# openclaw-mem-engine admin ops (P0-1)

This page documents the operator-facing admin surfaces added for `openclaw-mem-engine`.

## What is supported

Comparable admin capabilities are now available for the engine backend:

- `list` memories (filterable by `scope` / `category`, bounded by `limit`)
- `stats` (counts by `scope` / `category` + size/age summaries)
- `export` (sanitized, deterministic JSONL/JSON)
- `import` (append mode, with dedupe and dry-run validation)

All admin operations return a receipt/debug block with:

- `operation`
- `filtersApplied`
- `returnedCount` (or `importedCount` / `skippedCount` / `failedCount` for import)
- backend context (`dbPath`, `tableName`, latency)

## CLI commands

> OpenClaw core may not ship built-in `openclaw memory list|stats|export|import` yet.
> This plugin registers equivalent admin commands under **both** surfaces when loaded:
>
> - `openclaw memory <subcommand>` (extends existing memory command)
> - `openclaw ltm <subcommand>` (fallback compatibility namespace)

### List

```bash
openclaw memory list --scope openclaw-mem --limit 20 --json
# fallback:
openclaw ltm list --scope openclaw-mem --limit 20 --json
```

### Stats

```bash
openclaw memory stats --scope openclaw-mem --json
# fallback:
openclaw ltm stats --scope openclaw-mem --json
```

### Export (sanitized by default)

```bash
openclaw memory export \
  --scope openclaw-mem \
  --out /root/.openclaw/workspace/.tmp/openclaw/mem_export_test.jsonl \
  --format jsonl \
  --json

# fallback:
openclaw ltm export --scope openclaw-mem --out /tmp/mem.json --format json --json
```

- Deterministic ordering: `createdAt ASC`, then `id ASC`
- Default redaction: obvious API/token/private-key patterns in `text` are masked
- Use `--no-redact` only in trusted/local scenarios

### Import (append + dedupe + dry-run)

```bash
openclaw memory import \
  --in /root/.openclaw/workspace/.tmp/openclaw/mem_export_test.jsonl \
  --dedupe id_text \
  --dry-run \
  --json

# fallback:
openclaw ltm import --in /tmp/mem.jsonl --dedupe id_text --dry-run --json
```

Dedupe modes:

- `none` – no dedupe
- `id` – skip rows with existing IDs
- `id_text` (default) – skip existing IDs and normalized duplicate text

Import behavior:

- append-only; no destructive overwrite
- if `vector` is missing, engine attempts embedding generation
- if embeddings are unavailable and no `vector` provided, row is counted as failed

## Tool API surface

The same admin operations are also exposed as tools:

- `memory_list`
- `memory_stats`
- `memory_export`
- `memory_import`

This keeps admin functionality available in agent/tool workflows even if CLI wiring differs across OpenClaw versions.
