# Blade map v0 — TencentDB-Agent-Memory absorption into openclaw-mem

Status: active implementation slice
Date: 2026-05-15

## Battle picture
TencentDB-Agent-Memory has two ideas worth absorbing into `openclaw-mem`:

1. **Symbolic short-term memory**: compress verbose task/tool state into a compact Mermaid canvas while preserving refs to raw evidence.
2. **Layered memory semantics**: L0 raw conversation → L1 atom → L2 scenario → L3 persona, with drill-down from abstract profile/scene back to evidence.

`openclaw-mem` already owns the stronger product spine: **Store / Pack / Observe**, citations, trust policy, bounded `ContextPack`, receipts, rollback, and opt-in advanced labs. So this line absorbs **interfaces and patterns**, not the Tencent plugin/runtime.

## Decision
Absorb as a governed `symbolic-canvas` / layered-drilldown helper inside `openclaw-mem`, starting with deterministic local artifacts. Do not install the Tencent plugin or import its postinstall patch workflow.

## Scope for this slice

### Build
- Add a deterministic symbolic canvas generator that accepts a small JSON task trace and emits:
  - Mermaid graph text
  - node index with `node_id`, labels, state, refs
  - warnings for missing evidence refs
- Add CLI access under `openclaw-mem` if the existing CLI shape supports a small subcommand cleanly.
- Add docs describing how this maps to Store / Pack / Observe.

### Do not build yet
- No automatic after-tool-call capture.
- No live context offload slot.
- No persona auto-writer.
- No Gateway/plugin patch.
- No Qdrant/LanceDB backend changes.

## Invariants
- Store remains canonical durable record owner.
- Pack remains bounded injection owner.
- Observe remains receipt/debug owner.
- Any L3/persona layer is advisory/read-only unless a separate governed apply path exists.
- Raw evidence is referenced, not swallowed into irreversible summaries.

## Verifiers
- Unit tests for deterministic node IDs / Mermaid output / missing-ref warnings.
- CLI smoke creates reviewable JSON + Mermaid artifacts under `.state/...`.
- `git diff --check` for touched files.

## Rollback
Remove the added symbolic-canvas module, tests, docs, and receipt files. No runtime topology rollback expected.
