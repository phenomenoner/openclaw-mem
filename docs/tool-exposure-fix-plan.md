# openclaw-mem tiny fix plan — tool exposure (`memory_store` / `memory_recall`)

Date: 2026-02-08
Owner: openclaw-mem

## Problem
`openclaw-mem` capture hook was loading, but `memory_store` / `memory_recall` could return `Tool not available` in runtime.

## Root-cause hypothesis
The plugin declared tools via a static `tools: { ... }` block, while official OpenClaw extensions/docs use runtime registration via `api.registerTool(...)` inside `register()`.

## Minimal fix scope
1. Keep current capture behavior unchanged (`tool_result_persist` JSONL capture).
2. Move tool wiring to official API path (`api.registerTool(...)`).
3. Keep command behavior unchanged (`openclaw-mem store` / `openclaw-mem hybrid`).
4. Update docs/changelog/version.

## Acceptance checks
- [ ] Gateway starts with plugin enabled.
- [ ] `memory_store` can be invoked via Gateway tools/invoke.
- [ ] `memory_recall` can be invoked via Gateway tools/invoke.
- [ ] Capture still appends observations JSONL.
- [ ] If strict tool policy is enabled, plugin tools are explicitly opted in (recommended: `tools.alsoAllow` includes `memory_store`, `memory_recall`).

## Rollback
- Revert commit and restart gateway.
- Plugin remains usable in capture-only mode while investigating.

## Status
Implemented on 2026-02-08:
- registration path migrated to `api.registerTool(...)`
- docs/changelog/version updated

Runtime note:
- actual tool invocation still depends on the active OpenClaw tool policy (allow/deny/profile).
