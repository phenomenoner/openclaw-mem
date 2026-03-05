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

## Docs Memory cold lane (installable)

`openclaw-mem-engine` now includes an optional **docs cold lane** for operator-authored markdown (DECISIONS/roadmaps/specs) without writing those chunks into hot memory rows.

### New tools

- `memory_docs_ingest` — bounded ingest into `openclaw-mem docs` SQLite index
- `memory_docs_search` — bounded docs snippets (`operator` provenance)

`memory_recall` and `autoRecall` can consult docs cold lane **only when hot recall is insufficient** (`minHotItems` threshold).

### Config knobs

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem-engine": {
        "enabled": true,
        "config": {
          "docsColdLane": {
            "enabled": true,
            "sqlitePath": "~/.openclaw/memory/openclaw-mem.sqlite",
            "sourceRoots": [
              "/root/.openclaw/workspace/lyria-working-ledger/DECISIONS",
              "/root/.openclaw/workspace/openclaw-async-coding-playbook/projects"
            ],
            "sourceGlobs": ["**/*.md", "**/ROADMAP*.md", "**/*SPEC*.md"],
            "scopeMappingStrategy": "repo_prefix", // none|repo_prefix|path_prefix|map
            "scopeMap": {
              "openclaw-mem": ["openclaw-mem/docs", "openclaw-mem/specs"]
            },
            "maxChunkChars": 1400,
            "embedOnIngest": true,
            "ingestOnStart": false,
            "maxItems": 2,
            "maxSnippetChars": 280,
            "minHotItems": 2,
            "searchFtsK": 20,
            "searchVecK": 20,
            "searchRrfK": 60
          }
        }
      }
    }
  }
}
```

### Verification commands

```bash
# 1) Ingest allowlisted docs
openclaw tools invoke memory_docs_ingest --json '{}'

# 2) Query docs lane directly
openclaw tools invoke memory_docs_search --json '{"query":"status code decision","scope":"openclaw-mem"}'

# 3) Verify cold-lane marker in recall receipt/logs
# expect: openclaw-mem-engine:docsColdLane.search
# and autoRecall receipt field: coldLane.{consulted,returned,strategy}
```

### Log markers / receipts

- ingest: `openclaw-mem-engine:docsColdLane.ingest`
- search: `openclaw-mem-engine:docsColdLane.search`
- recall receipt (`openclaw-mem-engine.recall.receipt.v1`) now carries optional `coldLane` summary

### Rollback

Fast rollback (no code revert):

```bash
openclaw config set plugins.entries.openclaw-mem-engine.config.docsColdLane.enabled false
openclaw gateway restart
```

Hard rollback (remove lane tools as well): revert to previous commit and restart gateway.
