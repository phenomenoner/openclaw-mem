# Docs cold lane first-class ingest fix plan — 2026-05-02

## Goal
Fix `memory_docs_ingest` first-class tool failures where the OpenClaw tool path can surface a raw Node path error:

```text
The "paths[0]" argument must be of type string. Received undefined
```

## Non-goals
- Do not change docs cold lane CLI behavior.
- Do not change configured docs source roots, SQLite path, embedding provider, or memory topology.
- Do not broaden ingest allowlists.
- Do not restart the gateway as part of the code patch without explicit operator confirmation.

## Expected behavior
- Tool-supplied `sourceRoots` / `sourceGlobs` are normalized before path resolution.
- Undefined / non-string array entries cannot reach `path.resolve` / `api.resolvePath` / `execFile` args.
- Invalid override roots return a structured `source_roots_invalid` receipt instead of throwing a raw tool error.
- Valid allowlisted roots continue to ingest via the existing CLI fallback path.

## Verifier plan
1. Unit/regression test: mixed undefined/non-string source roots are handled without throwing and valid strings survive.
2. Unit smoke: existing `docsColdLane.test.mjs` passes.
3. CLI smoke: `openclaw-mem docs ingest` succeeds on `/root/.openclaw/workspace/docs/lyria-self-journal/README.md`.
4. Human closure: receipt in daily memory and this plan.

## Rollback
Revert the patch commit/files in `/root/.openclaw/workspace/openclaw-mem`. Runtime behavior remains unchanged until gateway reload/restart loads patched plugin code.

## Topology/config impact
Unchanged. Code-only wrapper hardening.
