# Self-improvement consolidation: slices 2–5

This page documents the second product batch in the OpenClaw Mem self-improvement consolidation line. The batch expands the read-only/staged-only skeleton after the initial surface validator and `goal status` pilot.

## What this batch adds

### Slice 2 — Goal survival pack seam

`openclaw-mem goal pack` builds a ContextPack-compatible fragment from a goal/controller receipt.

```bash
openclaw-mem goal pack --file goal.json --json
```

This is the goal-primitive alias for the existing active-line context pack shape. It is read-only and returns `writes_performed=false`.

Use it when an unfinished goal needs to survive compaction or handoff as a bounded pack fragment containing:

- goal id
- status
- objective
- current/next gate
- stop-loss state, when present
- verifier presence

### Slice 3 — `skill_capture` staged proposal

`openclaw-mem skill-capture propose` lets an agent mark a learning candidate during a turn without editing live skills.

```bash
openclaw-mem skill-capture propose \
  --text "When version changes, refresh uv.lock before CI." \
  --target-skill ck-software-engineering-ops \
  --rationale "Prevents lockfile freshness failures" \
  --out .state/skill-capture/proposals/version-lock.json \
  --json
```

Rules:

- writes only an explicit L1 staged proposal artifact
- never patches live skills mid-turn
- caps text size
- rejects path-like target skill names
- leaves curator judgment for a later review surface

### Slice 4 — Skill Curator report-only review

`openclaw-mem skill-curator review` is a product-facing report-only alias for the existing self-curator skill review lane.

```bash
openclaw-mem skill-curator review --skill-root skills --json
```

It emits review-only lifecycle candidates and remains blocked until human review. By default it writes review JSON/Markdown artifacts under `--out-root` (default `.state/skill-curator/runs/<timestamp>/`); use `--no-write` for payload-only review. It does not apply patches.

### Slice 5 — OpenClaw Mem System status

`openclaw-mem mem-system status` reports the current Store / Pack / Observe / Review / Curate surfaces in one read-only inventory.

```bash
openclaw-mem mem-system status --json
```

The status output includes:

- planes: Store, Pack, Observe, Review, Curate
- surface count
- state counts such as `stable`, `lab`, and `shadow`
- `writes_performed=false`
- `topology_changed=false`

## Non-goals

This batch does not enable:

- auto-continuation
- automatic skill mutation
- governed apply
- cron changes
- gateway/plugin configuration changes
- L3/L4 live mutation

## Recommended next step

After these surfaces are merged and released, the next engineering line can prepare Slice 6: the staged mutation framework. That line should remain separate because it introduces proposal → apply → rollback semantics and touches higher-risk authority boundaries.
