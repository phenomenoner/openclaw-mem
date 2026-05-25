# Memory Strata WS1 Product Architecture Audit — 2026-05-25

Status: **completed / read-only baseline**  
Companion specs: `docs/specs/memory-strata-boundary-map-v0.md`, `docs/specs/memory-strata-todo-v0.md`  
Topology impact: **unchanged** — no runtime config, cron, slot, schema, or install changes were made.

## Goal

Verify the current-known product surfaces for the memory strata before any WS2–WS9 implementation or local install/enable work.

## Evidence captured

- CLI/help capture: `.tmp/memory-strata-ws1/cli-surfaces.txt`
- Surface file inventory: `.tmp/memory-strata-ws1/surface-files.txt`
- Command used: `python3 -m openclaw_mem ... --help/status` only.

## Runtime/status snapshot

- `openclaw_mem` version: `1.9.18`
- DB path: `/root/.openclaw/memory/openclaw-mem.sqlite`
- DB preexisting: `True`
- Observation count: `63608`
- Memory slot: `openclaw-mem-engine`
- `memory-core` enabled: `False`
- `memory-lancedb` enabled: `False`
- `openclaw-mem` sidecar enabled: `True`
- Episodic spool exists: `True`
- Episodic ingest state exists: `True`
- Graph capture state exists: `True`
- Graph markdown capture state exists: `True`
- Graph auto recall env enabled: `False`
- Graph auto capture env enabled: `False`

## Strata surface inventory

```text
## durable_engine_docs
- docs/mem-engine.md: file
- extensions/openclaw-mem-engine: dir
## episodic_docs
- docs/specs/episodic-events-ledger-v0.md: file
- docs/specs/episodic-auto-capture-v0.md: file
## episodic_semantic_docs
- docs/verbatim-semantic-lane.md: file
## working_set_docs
- docs/specs/auto-recall-activation-vs-retention-v1.md: file
## docs_cold_lane_docs
- docs/specs/docs-cold-lane-scope-pushdown-v1.md: file
- openclaw_mem/docs_memory.py: file
## graph_docs_code
- openclaw_mem/graph: dir
- docs/specs/graphic-memory-query-plane-v0.md: file
## pack_docs_code
- openclaw_mem/context_pack_v1.py: file
- openclaw_mem/pack_trace_v1.py: file
- docs/context-pack.md: file
```

## Product surface findings

| Stratum | Current-known surface | WS1 verdict |
|---|---|---|
| Durable / long-term | `openclaw-mem-engine` is reported as memory slot; engine docs and extension directory exist. | Present; exact selection/autoRecall policy still needs WS2. |
| Episodic | `episodes` command group exists with append/extract/ingest/query/embed/search/replay/redact/gc; spool and ingest state files exist. | Present; retention/redaction behavior needs WS3 fixture verification. |
| Episodic semantic | `episodes embed` and `episodes search --mode ...` are exposed in CLI help. | Present as episodic retrieval lane; hit-quality baseline deferred to WS4/WS10. |
| Working Set / Backbone | Design doc exists; pack/engine surfaces imply activation layer. | Present as design/current-known lane; source records and lifecycle need WS5. |
| Docs cold lane | `docs ingest/search` command group exists; docs memory code/spec exist. | Present; truth-owner boundary remains derived-index unless governed promotion. |
| Graph / topology | `graph` command group exists with index/pack/preflight/topology/query/capture/export surfaces; graph code/spec exist. | Present; topology-source contract and drift/orphan checks need WS7. |
| Pack / Proactive Pack | `pack` command exists with `--trace`, `--use-graph`, trust policy, lifecycle flags. | Present; pack is treated as consumer with writes disabled unless explicitly opted in. |

## Noted gaps / follow-up mapping

- WS2: Verify current `autoRecall` selection mode, quota behavior, repeat suppression, and Working Set dedupe.
- WS3: Fixture-test episodic summary-only query, include-payload gate, redact, retention/GC.
- WS4: Compare lexical vs episodic semantic retrieval on fixed queries.
- WS5: Define Working Set source/citation/TTL and whether any use-signal writeback is allowed.
- WS7: Write topology-source contract and local ops-only ontology separately.
- WS8: Run pack traces with lane failure/counterfactual checks.
- WS9: Promotion/writeback governor is planned, not assumed shipped.
- WS10: Retrieval regression baseline must precede default flips or bootstrap slimming.

## Counterfactual / safety check

- This audit used help/status/file inventory only.
- No `ingest`, `store`, `episodes ingest`, `docs ingest`, `graph capture`, `pack-lifecycle-write`, config write, cron change, install, push, or tag was run.
- Therefore a broken write path would not be hidden by this audit; write/enable validation remains future workstream-specific.

## Closure

WS1 read-only baseline is sufficient to proceed to WS10 retrieval regression baseline. It is **not** sufficient to claim any runtime/default behavior is ready for enablement.
