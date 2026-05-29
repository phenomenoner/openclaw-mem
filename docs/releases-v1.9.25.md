# openclaw-mem v1.9.25

Release date: 2026-05-30

## Highlights

- Symbolic Canvas auto-build now retries the default `command: "openclaw-mem"` through the repo-local module path when the binary is missing from `PATH`: `uv run --project <repo-root> --python 3.13 --frozen python -m openclaw_mem ...`.
- Custom Symbolic Canvas commands remain authoritative. The fallback only applies to the default `openclaw-mem` command after an `ENOENT` spawn failure.
- Symbolic Canvas receipts now expose the configured command, executed command, executed args, fallback status, and per-attempt summaries.
- Docs cold-lane ingestion/search can pass configured embedding credentials to the child process environment without logging or storing the key.
- The memory plugin manifest now declares its exported tool contract for runtime surface auditing.
- `openclaw-mem mem-system verify` is available as a read-only alias for the expanded system posture report.

## Operator Verification

```bash
node --test extensions/openclaw-mem-engine/symbolicCanvasAuto.test.mjs extensions/openclaw-mem-engine/docsColdLane.test.mjs extensions/openclaw-mem-engine/routeAuto.test.mjs extensions/openclaw-mem-engine/qdrantEdgeRuntimeAdapter.test.mjs extensions/openclaw-mem-engine/gbrainMirror.test.mjs
uv run --python 3.13 --frozen pytest tests/test_mem_system_status.py tests/test_symbolic_canvas.py
uv run --python 3.13 --frozen python -m openclaw_mem mem-system verify --workspace-root . --state-root /root/.openclaw --json
git diff --check
```

Expected `mem-system verify` fields include `writes_performed=false` and `topology_changed=false`.

## Safety Posture

- The new `mem-system verify` path is read-only. SQLite coverage is opened with a read-only URI and optional `--out` is the only file write.
- The Symbolic Canvas fallback is narrow: it does not substitute custom commands, and it does not retry ordinary non-zero command failures.
- Embedding credentials are passed only to the spawned child environment when the parent process does not already define the corresponding environment variables.
- The plugin `contracts.tools` declaration is descriptive metadata; it does not add a new write path.

## Changed Files

- `extensions/openclaw-mem-engine/symbolicCanvasAuto.js`
- `extensions/openclaw-mem-engine/docsColdLane.js`
- `extensions/openclaw-mem-engine/index.ts`
- `extensions/openclaw-mem-engine/openclaw.plugin.json`
- `openclaw_mem/mem_system_status.py`
- `openclaw_mem/cli.py`
- `docs/symbolic-canvas.md`
- `extensions/openclaw-mem-engine/README.md`
- focused tests under `extensions/openclaw-mem-engine/` and `tests/test_mem_system_status.py`
