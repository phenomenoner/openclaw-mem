# 櫻花刀舞 — Wei Ji Hook Automation Blade Map

Date: 2026-03-27  
Primary repo: `openclaw-mem`  
Companion repo: `delirium-to-weiji`

## Verdict
Push Wei Ji from hook-ready to **actually auto-triggered** at the highest-ROI OpenClaw write path first: `memory_store`.

Checkpoint / closeout automation stays in scope, but only after the memory-write gate is landed or its lane is proven clearly available.

## Whole-picture promise
Make OpenClaw ask Wei Ji **at the dangerous moment before memory becomes system truth**, without requiring the operator to remember any wrapper commands.

This line is about **real automation**, not better snippets.

## Bounded slice
### Slice A (must land)
Automate Wei Ji preflight inside `openclaw-mem-engine`'s `memory_store` write path in an advisory-first, fail-open, rollbackable posture.

### Slice B (only if lane is clearly available after A)
Evaluate and, if cheap/truthful, wire a checkpoint / delegated-closeout trigger path using existing OpenClaw hook surfaces.

## Contract / boundary rules
In scope:
- local subprocess call from `openclaw-mem-engine` to Wei Ji wrapper
- config-gated automation (off by default unless explicitly enabled in this host config)
- machine-readable receipt in `memory_store` result details
- fail-open policy knob so memory path does not become fragile by accident
- tests/docs/config/WAL closure

Out of scope:
- daemon/service layer
- auto-approval / auto-reject without explicit policy
- new persistence lane
- web UI
- broad OpenClaw core refactor

## Design posture
- advisory-first
- config-gated
- fail-open by default unless host config explicitly requests blocking behavior
- explicit receipt beats invisible magic
- thin edge in plugin, testable helper for subprocess contract

## Serial queue board
- [x] Blade 0 — write hook-automation blade map
- [x] Blade 1 — inventory actual hookable lanes on this host and confirm ROI order
- [x] Blade 2 — add a testable Wei Ji preflight helper module for memory intents
- [x] Blade 3 — wire helper into `memory_store` write path with config gate + receipt surface
- [x] Blade 4 — add focused tests for helper + fail-open/fail-closed behavior
- [x] Blade 5 — update operator docs/config contract; state what is and is not auto-triggered
- [x] Blade 6 — evaluate checkpoint/closeout auto-trigger lane; **defer** unless smallest truthful wedge is clear
- [x] Blade 7 — verifier pass + manual smoke + WAL/push/docs-ingest closure

## Blade 1 receipt — host hookable lanes / ROI order

Confirmed lane order (highest ROI first on this host):
1. `memory_store` tool execute path in `openclaw-mem-engine` (direct pre-commit interception before `db.add`) ✅
2. `memory_import` batch write path (high volume but lower frequency)
3. `agent_end` autoCapture write path (implicit extraction, not explicit operator intent)
4. checkpoint/closeout automation lane (currently not a clear low-risk hook surface in this plugin slice)

Why this order:
- `memory_store` is the explicit "make this durable" moment and already has a deterministic plugin-owned execution surface.
- checkpoint/closeout requires runtime-command lifecycle interception not currently documented in this lane with the same confidence.

## Blade 6 receipt — checkpoint/closeout lane decision

Decision: **deferred in this slice**.

Reason:
- No documented, low-risk checkpoint/closeout hook equivalent to the `memory_store` tool intercept in this plugin boundary.
- Forcing this now would drift into broader OpenClaw core exploration/surgery, violating this blade's bounded constraints.

## Verifier plan
- helper-level tests for input shaping / subprocess result parsing / fail-open-vs-block policy
- repo-root smoke for extension package tests
- live host check only after config/runtime truth is explicit
- topology statement must distinguish:
  - plugin behavior changed
  - runtime config changed or unchanged
  - checkpoint lane landed or deferred

## Stop-loss
Stop and report early if:
1. checkpoint/closeout automation requires undocumented OpenClaw core surgery,
2. the Wei Ji subprocess path cannot be made fail-open and bounded,
3. helper/subprocess wiring drifts into framework archaeology,
4. runtime config uncertainty blocks truthful closure.
