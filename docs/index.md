# openclaw-mem

**Local-first memory sidecar for OpenClaw.**

Turn your agent’s work into a durable, searchable memory trail—without taking over the canonical memory slot.

## Reality check

- Reality check & status (DONE / PARTIAL / ROADMAP): [Go →](reality-check.md)

## Why operators use it

- **Always-fresh recall:** keep “what just happened?” searchable in minutes (or less).
- **Cheap progressive recall:** `search → timeline → get` keeps most lookups local.
- **Auditability:** one SQLite ledger you can grep, backup, diff, and export.
- **Safe boundaries:** OpenClaw backends stay canonical; this project stays sidecar.

## How it works (one screen)

```text
OpenClaw tool results → JSONL capture → harvest → SQLite (FTS) → progressive recall
                           └────────────── optional: embeddings / compression
```

## Start here

| | | |
|---|---|---|
| **Quickstart** | **Ecosystem fit** | **Deployment** |
| Install + run the 5‑minute tour. | Who owns which memory tools/slots. | Always‑fresh ingest profile + ops tips. |
| [Go →](quickstart.md) | [Go →](ecosystem-fit.md) | [Go →](deployment.md) |

## Memory quality features

- Architecture (design): [Go →](architecture.md)
- Thought-links (why these design/benchmark choices): [Go →](thought-links.md)
- Benchmark/eval plan pointers: [Go →](thought-links.md) · [Go →](rerank-poc-plan.md)
- Importance grading (MVP v1): [Go →](importance-grading.md)
- Context engineering lessons (local-first): [Go →](context-engineering-lessons.md)
- Roadmap (engineering): [Go →](roadmap.md)
- Upgrade checklist (system upgrades): [Go →](upgrade-checklist.md)

## Minimal CLI taste

```bash
# Create/open DB and show counts
uv run python -m openclaw_mem --json status

# Cheap recall
uv run python -m openclaw_mem --json search "gateway timeout" --limit 10
```

## Links

- Repo: <https://github.com/phenomenoner/openclaw-mem>
- Issues: <https://github.com/phenomenoner/openclaw-mem/issues>
