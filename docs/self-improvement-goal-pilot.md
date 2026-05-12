# Self-improvement consolidation: surface validation and goal status

OpenClaw Mem's self-improvement work is split into deliberately small, reviewable pieces. This page documents the first read-only slice:

1. a shared surface/receipt validation contract, and
2. a goal status readback command.

The slice is intentionally local-only and non-mutating. It is meant to make future memory, skill-curator, and goal-continuation work safer by establishing a common receipt and authority shape before any background loop is allowed to write durable state.

## Why this exists

Agents feel more useful when they can preserve unfinished work and improve reusable procedures. OpenClaw's product posture is that this self-improvement must be observable, feature-flagged, rollbackable, and gated by write authority.

This pilot therefore starts with validation and status, not automation.

## Surface inventory contract

A surface inventory lists self-improvement-related components and their current authority level.

Example:

```json
{
  "surfaces": [
    {
      "surface_id": "goal.primitive",
      "state": "lab",
      "owner": "openclaw-mem",
      "write_authority": "stage",
      "risk_class": "L1",
      "protected": false,
      "rollback": null
    },
    {
      "surface_id": "skills.operator-rule",
      "state": "stable",
      "owner": "operator",
      "write_authority": "none",
      "risk_class": "L3",
      "protected": true,
      "rollback": "manual review required"
    }
  ]
}
```

Supported states:

- `stable`
- `lab`
- `shadow`
- `retired`

Supported write authorities:

- `none`
- `suggest`
- `stage`
- `apply-local`
- `apply-publish`

Supported risk classes:

- `L0` — read-only/report only
- `L1` — staged local artifact, no live runtime effect
- `L2` — local durable memory/skill addition
- `L3` — edit/delete/retire existing load-bearing rule/skill/memory
- `L4` — external publish, config/routing/cron/topology mutation

Protected surfaces require at least `apply-local` authority, and L4/external surfaces require `apply-publish` authority with explicit approval.

## Validate a surface inventory or receipt

```bash
openclaw-mem surface validate --inventory surfaces.json --json
```

Validate a receipt against an inventory:

```bash
openclaw-mem surface validate \
  --inventory surfaces.json \
  --receipt receipt.json \
  --out validation-receipt.json \
  --json
```

The command returns a validation receipt with `writes_performed=false`.

## Goal status readback

`goal status` normalizes a goal/controller receipt into a small, read-only status object.

Example input:

```json
{
  "goal": {
    "goal_id": "self-improvement-pilot",
    "objective": "Ship read-only goal status",
    "status": "active",
    "phase": "phase-1",
    "next_gate": "run tests",
    "continuation_owner": "operator",
    "completion_verifier": "pytest"
  }
}
```

Run:

```bash
openclaw-mem goal status --file goal.json --json
```

Write a status receipt:

```bash
openclaw-mem goal status \
  --file goal.json \
  --out goal-status.receipt.json \
  --json
```

The command is read-only except for the optional explicit `--out` file.

## Relationship to context packing

This pilot does not implement runtime continuation or compaction behavior. For compaction-safe injection, the intended future seam is an OpenClaw context engine. Prompt hooks can provide fallback context, but the durable goal/todo state should be owned by a context/packing layer rather than pasted into every turn unconditionally.

## Non-goals

- no automatic skill mutation
- no live auto-continuation
- no cron or gateway topology changes
- no retirement of legacy memory surfaces
- no external publishing without review and explicit approval
