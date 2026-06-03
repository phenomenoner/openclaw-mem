# openclaw-mem optimization run-to-empty blade map - 2026-05-30

Status: implementation spec
Owner: CK / Lyria bounded repo-side worker
Source review: `docs/receipts/openclaw-mem-compat-mempalace-gbrain-review-2026-05-30.md`

## Total goal

Implement the approved repo-side optimization slices from the 2026-05-30 compatibility review without mutating live OpenClaw topology. The result must make symbolic-canvas auto-build resilient to a missing global `openclaw-mem` binary and provide one read-only `mem-system verify` posture report for operators.

## Non-goals

- No live OpenClaw config edits outside this repository.
- No Gateway restart.
- No Qdrant/LanceDB backend switch.
- No live docs, episodes, graph, lifecycle, or mirror writeback.
- No push, tag, release, data migration, or snapshot restore.
- No promotion of GBrain, MemPalace, routeAuto, or working-set behavior.

## Authority boundaries

- Repo files under `/root/.openclaw/workspace/openclaw-mem` may be changed.
- WAL files under `/root/.openclaw/workspace/WAL/openclaw-mem-optimization-run-to-empty-20260530/` may be written.
- Daily memory under `/root/.openclaw/workspace/memory/2026-05-30.md` may be appended.
- Live OpenClaw state may be read for verification, but not mutated.
- The durable truth owner for this slice is the local SQLite store at `state_root/memory/openclaw-mem.sqlite`; LanceDB and Qdrant are treated as indexes/caches, and GBrain is treated as an experimental mirror only.
- Topology means live plugin slot ownership, enabled backend choice, writer surfaces, cron jobs, Gateway process state, and data/index backend selection.

## Slices

### Slice A - symbolic-canvas command fallback

Harden `extensions/openclaw-mem-engine/symbolicCanvasAuto.js` so the default or explicitly configured `openclaw-mem` command can retry through the repo-local module invocation when the binary is absent from `PATH`:

```text
uv run --project <repo-root> --python 3.13 --frozen python -m openclaw_mem ...
```

Custom commands remain authoritative and do not fall back. Receipts should expose the configured command, executed command, fallback status, and attempts where practical.

Clarifications:

- Fallback is identity-by-command-name: after config resolution, `command === "openclaw-mem"` is fallback eligible whether it came from defaults or explicit config.
- Missing primary command is detected from the attempted process result (`ENOENT`), not a preflight `which`.
- There is at most one fallback attempt. The fallback inherits the same timeout and max-buffer budget as the primary attempt.
- Fallback uses the repository root resolved from the extension module location. If `uv` is absent or the module invocation fails, receipts retain both primary and fallback attempts.
- The fallback command shape intentionally follows the approved review requirement. `uv` may use its normal cache/interpreter resolution when actually invoked by auto-build; `mem-system verify` only reports fallback availability and must not execute it.
- Focused node tests mock the runner and do not require real `openclaw-mem`, `uv`, or Python 3.13.

### Slice B - read-only `mem-system verify`

Extend the existing `mem-system status` surface with a `verify` alias/report that consolidates:

- durable truth owner
- Store, Pack, Observe, Review, and Curate surfaces
- CLI availability for `openclaw-mem`, `uv`, and `gbrain`
- symbolic-canvas command readiness and fallback availability
- safely readable state/index coverage counts
- explicit `writes_performed=false` and `topology_changed=false`

Prefer structured JSON plus a concise text rendering. The command must remain read-only.

Clarifications:

- SQLite is opened with `mode=ro` for counts, and missing or unreadable state returns coverage errors instead of attempting repair or schema creation.
- Counts are bounded to cheap table counts and path existence/size metadata; no Qdrant/LanceDB/GBrain live connection or backend probe is allowed.
- CLI availability is `PATH` inspection only and does not execute commands.
- `writes_performed=false` and `topology_changed=false` are assertions backed by implementation shape and local tests; the CLI does not write output unless the operator explicitly passes `--out`.

### Optional Slice C - routeAuto latency receipt plan

If time remains, document a low-risk verifier plan only. Do not change live routeAuto behavior in this slice.

## Verifiers

```bash
node --test extensions/openclaw-mem-engine/symbolicCanvasAuto.test.mjs extensions/openclaw-mem-engine/docsColdLane.test.mjs extensions/openclaw-mem-engine/routeAuto.test.mjs extensions/openclaw-mem-engine/qdrantEdgeRuntimeAdapter.test.mjs extensions/openclaw-mem-engine/gbrainMirror.test.mjs
uv run --python 3.13 --frozen pytest tests/test_mem_system_status.py tests/test_symbolic_canvas.py
uv run --python 3.13 --frozen python -m openclaw_mem mem-system verify --workspace-root . --state-root /root/.openclaw --json
git diff --check
```

## Rollback

Revert the repo changes and remove the WAL/spec artifacts. No live topology rollback is expected because the work does not mutate live config, restart Gateway, change indexes, or switch backends.

## Topology impact

Expected topology impact: unchanged. This work is code/docs/test only plus read-only CLI inspection.

## WAL closure requirements

- Store this spec path in the WAL.
- Store Claude pre-implementation and post-implementation review receipts, or record truthful unavailability.
- Store implementation notes and verifier commands/results.
- Store an explicit topology statement.
- Append the daily memory outcome and next owner.
