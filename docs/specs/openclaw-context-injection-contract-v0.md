# OpenClaw context injection contract v0

Status: **spec-only, bounded adoption note**

## Why this exists

`claude-mem`'s OpenClaw integration clarified a useful product boundary:
- **hot cross-session context** should be injected at runtime via OpenClaw hooks,
- **durable memory** should remain operator/agent curated,
- and the two should not collapse into the same write path.

For `openclaw-mem`, the correct cherry-pick is the **contract**, not a blind worker-centric transplant.

## Current repo reality

Today `openclaw-mem` ships:
- sidecar observation capture (`extensions/openclaw-mem`)
- optional memory-slot backend (`extensions/openclaw-mem-engine`)
- agent-memory skill cards + prompt-layer deployment snippets

Today it does **not** ship a first-class OpenClaw `before_prompt_build` runtime bridge that appends hot context into the system prompt.

That means this document defines the intended future runtime contract and the guardrails we should preserve while approaching it.

## Contract

If/when `openclaw-mem` gains a hot-context OpenClaw bridge, it should follow these rules.

### 1) Runtime lane, not markdown writeback
- Use OpenClaw hook/runtime surfaces such as `before_prompt_build`.
- Return hot context through `appendSystemContext` (or the equivalent runtime append surface).
- Do **not** use `MEMORY.md` as the transport for per-turn context injection.

### 2) Durable memory stays curated
- `memory/YYYY-MM-DD.md` and `MEMORY.md` remain durable/operator-facing truth surfaces.
- Observation capture or hot-context injection must not silently rewrite those files on every turn.

### 3) Empty means no injection
- If the bounded context query returns empty/whitespace-only content, inject nothing.
- Do not add cosmetic wrappers around an empty result.

### 4) Per-agent carve-out is first-class
- Support **per-agent exclusion** for hot-context injection.
- Read-only / watchdog / narrow cron lanes should be able to opt out cleanly.
- Exclusion should be explicit and reviewable in config, not buried in prompt prose.

### 5) Bounded cache semantics
- Cache hot-context results with a short TTL.
- Document the cache key, TTL, and reset behavior.
- Gateway restart or equivalent runtime reset must clear stale injection state.

### 6) No recursive memory loops
- Memory-management tools and bridge-maintenance internals must not recursively produce new hot-context fetch loops.
- Tests should explicitly cover recursion guards.

### 7) Fail-open and visible
- If the hot-context provider is unavailable, the agent loop should continue.
- Failure should degrade to “no injected context”, not to a broken turn.
- Operator receipts/logs should make the skip/degrade reason legible.

## Adaptation boundary for `openclaw-mem`

`openclaw-mem` should adopt this in layers:

### Layer A — prompt-layer deployables (already available)
- canonical skill cards under `skills/`
- generated prompt snippets under `docs/snippets/`
- runtime-enforced read-only mode when `openclaw-mem-engine` is the active memory slot

### Layer B — sidecar capture guardrails (shippable now)
- keep capture out of `MEMORY.md`
- allow per-agent exclusion from sidecar observation capture for noisy lanes
- keep tests around non-writeback and bounded capture behavior

### Layer C — future runtime bridge (later)
- `before_prompt_build` injection
- `appendSystemContext` hot-context path
- bounded TTL cache and explicit reset semantics
- per-agent injection exclusion

## Minimum test contract

A future runtime bridge should ship with tests for:
1. context injected on non-empty result
2. no injection on empty result
3. no `MEMORY.md` writeback on init/tool/result paths
4. per-agent exclusion
5. recursion guard for memory/self-management tools
6. TTL cache hit + reset on runtime restart
7. fail-open behavior when the provider is unavailable

## Operator stance

Until Layer C exists, operators should read this correctly:
- `openclaw-mem` already has strong **durable memory** and **capture** posture
- it does **not** yet claim claude-mem-style hot-context runtime injection
- prompt-layer snippets and read-only runtime enforcement remain the correct bounded deployment surface today
