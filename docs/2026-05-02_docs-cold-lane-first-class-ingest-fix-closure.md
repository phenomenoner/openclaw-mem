# Docs cold lane first-class ingest hardening closure — 2026-05-02

## Changed truth
`memory_docs_ingest` tool input is now sanitized before docs cold lane path resolution. Undefined, blank, or non-string `sourceRoots` / `sourceGlobs` entries are dropped; absolute roots resolve directly with `path.resolve`; an override containing no valid roots returns a structured `source_roots_invalid` receipt instead of surfacing a raw Node `paths[0]` error.

## Patch
- `extensions/openclaw-mem-engine/docsColdLane.js`
  - Added `coerceStringArray`.
  - Added `normalizeDocsColdLaneToolInput` for first-class ingest root/glob sanitation.
- `extensions/openclaw-mem-engine/index.ts`
  - Uses `normalizeDocsColdLaneToolInput` before resolving `memory_docs_ingest` override roots/globs.
  - Resolves absolute override roots directly with `path.resolve` instead of runtime `api.resolvePath`.
  - Adds structured `source_roots_invalid` response with `droppedSourceRoots` diagnostic count.
- `extensions/openclaw-mem-engine/docsColdLane.test.mjs`
  - Added regression coverage for invalid-only and mixed-valid first-class ingest input shapes.

## Verification
- `node --test docsColdLane.test.mjs` => 8/8 pass.
- `node --test *.test.mjs` => 47/47 pass.
- `uv run --python 3.13 --frozen python -m openclaw_mem --db /root/.openclaw/memory/openclaw-mem.sqlite --json docs ingest --path /root/.openclaw/workspace/docs/lyria-self-journal/README.md --max-chars 1400 --embed` => `ok=true`, `files_seen=1`, `chunks_unchanged=5`.
- `git diff --check` => clean.
- Independent review: approve with caveat; no must-fix. Caveat addressed by adding `normalizeDocsColdLaneToolInput` regression that covers invalid-only roots, mixed valid roots, and undefined globs.

## Runtime note
The current running OpenClaw gateway still has the old plugin code loaded. A live first-class `memory_docs_ingest` call still returns the old `paths[0]` error until the gateway/plugin process is reloaded. No restart was performed in this closure.

## Topology / config delta
Unchanged. Code-only hardening; no source root, SQLite, embedding, cron, or authority-surface config changed.

## Rollback
Revert this patch in `/root/.openclaw/workspace/openclaw-mem` and reload the gateway/plugin process if it has already been loaded.
