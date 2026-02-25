# openclaw-mem

**Local-first memory sidecar for OpenClaw.**

Turn your agent’s work into a durable, searchable memory trail—without forcing a change to the canonical memory slot.

> Roadmap note: we are also designing an *optional* slot backend plugin (**OpenClaw Mem Engine**) to replace `memory-lancedb` when you want hybrid recall + tighter governance. See: [Mem Engine →](mem-engine.md).

## Reality check

- Reality check & status (DONE / PARTIAL / ROADMAP): [Go →](reality-check.md)

## Why operators use it

- **Always-fresh recall:** keep “what just happened?” searchable in minutes (or less).
- **Cheap progressive recall:** `search → timeline → get` keeps most lookups local.
- **Docs memory (decisions/specs):** treat your repos as a recall surface (hybrid: FTS + optional embeddings), so “we already decided this” is retrievable without hints.
- **Auditability:** one SQLite ledger you can grep, backup, diff, and export.
- **Safe boundaries:** default posture stays sidecar; slot ownership remains optional and rollbackable.

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
- Context packing (ContextPack): [Go →](context-pack.md)
- Thought-links (why these design/benchmark choices): [Go →](thought-links.md)
- Benchmark/eval plan pointers: [Go →](thought-links.md) · [Go →](rerank-poc-plan.md)
- Importance grading (MVP v1): [Go →](importance-grading.md)
- Context engineering lessons (local-first): [Go →](context-engineering-lessons.md)
- Roadmap (engineering): [Go →](roadmap.md)
- Mem Engine (optional slot backend): [Go →](mem-engine.md)
- Docs memory (spec): [Go →](specs/docs-memory-hybrid-search-v0.md)
- Graphic memory (spec/PRD, dev): [Go →](specs/graphic-memory-graphrag-lite-prd.md)
- Graphic memory auto-capture + auto-recall v0 knobs: [Go →](specs/graphic-memory-auto-capture-auto-recall.md)
- Upgrade checklist (system upgrades): [Go →](upgrade-checklist.md)
- Release checklist (repo rule): [Go →](release-checklist.md)

## Minimal CLI taste

```bash
# Create/open DB and show counts
uv run python -m openclaw_mem --json status

# Cheap recall
uv run python -m openclaw_mem --json search "gateway timeout" --limit 10

# Build a compact recall bundle
uv run python -m openclaw_mem pack --query "gateway timeout" --limit 8 --trace --json
```

## Links

- Repo: <https://github.com/phenomenoner/openclaw-mem>
- Issues: <https://github.com/phenomenoner/openclaw-mem/issues>
