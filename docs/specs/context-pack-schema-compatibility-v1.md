# ContextPack Schema Compatibility v1

## Status

- Schema id: `openclaw-mem.context-pack.v1`
- Producer: `openclaw-mem pack`
- Consumer posture: fail open on invalid, oversized, or unsupported payloads
- Compatibility helper: `openclaw_mem.context_pack_contract`

## Contract

`openclaw-mem` keeps its package-native schema id for v1:

```text
openclaw-mem.context-pack.v1
```

Required top-level fields:

- `schema`
- `meta`
- `bundle_text`
- `items`
- `notes`

Required `meta` fields:

- `ts`
- `query`
- `scope`
- `budgetTokens`
- `maxItems`

Required `items[]` fields:

- `recordRef`
- `layer`
- `type`
- `importance`
- `trust`
- `text`
- `citations`

Required citation field:

- `items[].citations.recordRef`

`items[].text` is the stable chunk text. `items[].citations.recordRef` is the stable citation id. `items[].citations.url` is optional and may be null.

## Agent Harness Adapter Mapping

Hosts that use `agent-harness.context-pack.v1` should adapt, not rename, the producer schema.

| `openclaw-mem.context-pack.v1` | `agent-harness.context-pack.v1` adapter |
|---|---|
| `schema` | `sourceSchema` |
| `meta.query` | `query` |
| `meta.budgetTokens` | `budgetTokens` |
| `bundle_text` | `bundleText` |
| `items[].citations.recordRef` | `items[].citationId` and `items[].chunk.id` |
| `items[].text` | `items[].chunk.text` |
| `items[].citations.url` | `items[].chunk.sourceUri` |
| `items[].recordRef` | `items[].recordRef` |
| constant producer name | `items[].source = "openclaw-mem"` |

The helper `to_agent_harness_context_pack_v1()` performs this adapter mapping after validating the producer payload.

## Unsupported Versions

Consumers must reject unknown schema ids such as `openclaw-mem.context-pack.v99` with a typed validation error and fail open. They must not silently treat unknown future payloads as v1.

## Fixtures

- `tests/fixtures/context_pack/openclaw_mem_context_pack_v1.json`
- `tests/fixtures/context_pack/unknown_future_context_pack.json`
- `docs/fixtures/context-pack-v1-compat/legal-pack.json`
- `docs/fixtures/context-pack-v1-compat/oversized-pack.json`
- `docs/fixtures/context-pack-v1-compat/missing-field-pack.json`

## Verification

```powershell
uv run --python 3.13 pytest tests/test_context_pack_contract.py tests/test_context_pack_v1_compat_fixtures.py -q
```

Harness-side validation should additionally run against a generated pack:

```powershell
openclaw-mem pack --db .agent-harness\memory\openclaw-mem.sqlite --query "openclaw-mem memory engine recovery" --limit 5 --budget-tokens 800 --json > .tmp\context-pack-smoke\context-pack-openclaw-mem-v1.json
agent-harness context-pack-validate --raw-file .tmp\context-pack-smoke\context-pack-openclaw-mem-v1.json --json
```

If the harness validator is not present in the current checkout, record that as an external dependency receipt. Do not weaken the producer contract.

## Harness Env Bridge

For naked CLI use from an Agent Harness checkout, pass `--harness-home <path>` explicitly. The CLI then:

- reads `<harness-home>/secrets/memory-credentials.env` if present;
- maps harness memory credential names to CLI env names only in process memory;
- defaults `OPENCLAW_MEM_DB` to `<harness-home>/memory/openclaw-mem.sqlite` when no stronger DB path was supplied;
- reports redacted bridge metadata in `status --json`;
- never prints secret values.

Supported credential mappings:

| Target env | Source env candidates |
|---|---|
| `OPENAI_API_KEY` | `OPENAI_API_KEY`, `OPENCLAW_MEM_OPENAI_API_KEY`, `OPENCLAW_MEM_EMBEDDING_API_KEY`, `AGENT_HARNESS_MEMORY_EMBEDDING_API_KEY` |
| `OPENCLAW_MEM_OPENAI_BASE_URL` | `OPENCLAW_MEM_OPENAI_BASE_URL`, `OPENAI_BASE_URL`, `AGENT_HARNESS_MEMORY_EMBEDDING_BASE_URL` |
| `OPENCLAW_MEM_EMBED_MODEL` | `OPENCLAW_MEM_EMBED_MODEL`, `OPENAI_EMBEDDING_MODEL`, `AGENT_HARNESS_MEMORY_EMBEDDING_MODEL` |
| `OPENCLAW_MEM_RERANK_MODEL` | `OPENCLAW_MEM_RERANK_MODEL` |

Verification:

```powershell
openclaw-mem --harness-home .agent-harness status --json
openclaw-mem pack --harness-home .agent-harness --query "openclaw-mem memory engine recovery" --limit 5 --json
```
