# Self Curator Sidecar v0 — blade map and contract

Status: **IMPLEMENTATION SLICE** (review-only scout, zero-write)

This v0 contract is intentionally a scout/proposal slice, not the final Self Curator posture. The apply-capable direction is captured in [`self-curator-apply-capable-v1.md`](self-curator-apply-capable-v1.md): direct mutation is allowed once it goes through plan → checkpoint → apply → verify → rollback-capable receipt.

## Goal

Absorb the useful design pattern from Hermes Curator into `openclaw-mem` by first establishing a safe review packet. This v0 does not yet give the curator write authority; v1 is expected to add checkpointed direct mutation for whitelisted surfaces.

The first slice installs a deterministic **review-only self-curator sidecar** that scans skill files and emits lifecycle review artifacts:

- machine packet: `review.json`
- human report: `REPORT.md`

## Non-goals

- No automatic edits to `SOUL.md`, `AGENTS.md`, `MEMORY.md`, skills, runtime config, or OpenClaw memory rows in v0.
- No cron/heartbeat enablement in this slice.
- No LLM judgment in the first implementation slice.
- No hard delete and no archive action; all candidates are advisory.
- No external Hermes content is treated as authority. External material is design input only.

## Inputs

- One or more skill roots containing `*/SKILL.md` files.
- Optional limit for report bounding.
- Optional output root for durable artifacts.
- Optional run id, constrained to a single safe slug component (`[A-Za-z0-9._-]`) because it becomes an artifact directory name.

## Outputs

A timestamped run directory under `.state/self-curator/runs/` by default:

```text
<out-root>/<run-id>/
├── review.json
└── REPORT.md
```

The packet schema is intentionally shallow:

```json
{
  "kind": "openclaw.curator.lifecycle-review.v0",
  "run_id": "...",
  "ts": "...",
  "mode": "review_only",
  "scope": "skill",
  "source_refs": [],
  "summary": {
    "skills_scanned": 0,
    "candidate_count": 0,
    "writes_performed": 0
  },
  "candidates": [
    {
      "candidate_id": "...",
      "target_ref": "skills/foo/SKILL.md",
      "lifecycle_action": "keep|refresh|merge|retire|archive|promote_to_review",
      "reason": "...",
      "evidence_refs": [],
      "risk_class": "skill_surface",
      "apply_lane": "molt_gic_packet",
      "checkpoint_required": true
    }
  ],
  "writes_performed": 0,
  "blocked_until": "human_review"
}
```

## Invariants

- `writes_performed` must always be `0` in v0.
- The scanner may write only its own run artifacts.
- Run ids with path separators or traversal are rejected before artifact writes.
- Skill targets are never mutated by this command.
- Missing or malformed skill files degrade to bounded candidates, not crashes, when possible.
- Authority surfaces are not scanned by this first slice.

## Heuristics in v0

The v0 scanner is deterministic and conservative:

- `refresh`: missing frontmatter name/description, very short body, or explicit TODO/stub markers.
- `promote_to_review`: skill appears substantial and should be considered for pinning/review before any future lifecycle automation.
- `keep`: reserved for later versions when usage and pinning signals can justify no-op lifecycle accounting.

The first v0 scanner intentionally emits one candidate per scanned skill (`refresh` or `promote_to_review`) so operators can review/pin the whole skill surface before future automation. Duplicate/merge and stale/usage-based decisions are intentionally deferred until usage receipts exist.

## Verifier plan

- Unit tests for packet shape, zero-write posture, and heuristic candidate emission.
- CLI smoke with a synthetic skill root.
- Counterfactual smoke proving a malformed/stub skill becomes a bounded `refresh` candidate while no skill file changes.
- Human report must cite the generated `review.json` and truthfully reflect its counts.

## Rollback posture

- Revert the commit or restore files from the pre-change snapshot.
- Generated run artifacts are disposable and not sources of truth.
- No topology/config changes are made by this slice.

## Topology / config impact

**Unchanged.** This slice adds a manual CLI/reporting surface only. No cron, gateway, runtime config, or memory backend topology changes.
