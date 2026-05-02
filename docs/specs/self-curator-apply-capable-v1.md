# Self Curator apply-capable v1 — checkpointed mutation contract

Status: **NEXT SLICE SPEC**  
Supersedes the overly-conservative interpretation that Self Curator should remain review-only forever. v0 remains a useful scout/proposal surface; v1 is the first apply-capable lane.

## Goal

Build a Hermes-curator-like Self Curator that may directly change files or settings **inside an explicit checkpointed apply protocol**.

The contract is not "never mutate". The contract is:

> mutate only through a plan → checkpoint → apply → verify → rollback-capable receipt loop.

## Whole-picture promise

Self-improvement should be able to metabolize old skills, memory policy, and eventually safe settings without forcing CK to hand-edit every small hygiene change, while still making every change inspectable and reversible.

## Posture layers

```text
review-only scout
  -> apply plan
  -> rollback checkpoint
  -> apply whitelisted mutation
  -> verify/readback
  -> WAL + receipt
  -> rollback command remains available
```

## v1 command surface

Proposed CLI family:

```bash
openclaw-mem self-curator skill-review ...
openclaw-mem self-curator plan --from-review review.json --out plan.json
openclaw-mem self-curator apply --plan plan.json --checkpoint-root .state/self-curator/checkpoints --json
openclaw-mem self-curator rollback --receipt apply-receipt.json --json
openclaw-mem self-curator verify --receipt apply-receipt.json --json
```

## Allowed mutation classes for first apply-capable slice

Start narrow and real:

1. **Skill metadata refresh**
   - Fill missing `description` only when a deterministic replacement is supplied in the plan.
   - Normalize frontmatter ordering for selected skill files.
   - Add lifecycle sidecar metadata file, not hidden inline mutation, if richer state is needed.

2. **Generated config/settings candidate files**
   - Write proposed settings to a staged file first.
   - Promote only if target is explicitly whitelisted and rollback checkpoint exists.

3. **Archive/retire is not first apply**
   - No auto-archive in first v1 apply slice.
   - Archive requires mature restore tests and operator confidence.

## Out of scope for first v1 apply

- `SOUL.md`, `AGENTS.md`, `MEMORY.md`, runtime config, gateway config, cron topology.
- Hard delete.
- LLM-authored freeform rewrites without deterministic patch payload.
- External repo docs/skill publish without separate external-content review.

## Apply plan schema

```json
{
  "kind": "openclaw.curator.apply-plan.v1",
  "mode": "apply_plan",
  "source_review": ".../review.json",
  "plan_id": "...",
  "ts": "...",
  "mutations": [
    {
      "mutation_id": "...",
      "target_ref": "skills/foo/SKILL.md",
      "action": "replace_text|write_file|move_file|set_yaml_field",
      "risk_class": "skill_surface",
      "preconditions": {
        "sha256": "...",
        "must_contain": "..."
      },
      "patch": {
        "old_text": "...",
        "new_text": "..."
      },
      "rollback_strategy": "restore_checkpoint"
    }
  ],
  "requires_checkpoint": true
}
```

## Checkpoint manifest schema

```json
{
  "kind": "openclaw.curator.checkpoint.v1",
  "checkpoint_id": "...",
  "ts": "...",
  "plan_id": "...",
  "files": [
    {
      "target_ref": "skills/foo/SKILL.md",
      "before_sha256": "...",
      "snapshot_path": "...",
      "exists_before": true
    }
  ]
}
```

## Apply receipt schema

```json
{
  "kind": "openclaw.curator.apply-receipt.v1",
  "mode": "applied",
  "plan_id": "...",
  "checkpoint_id": "...",
  "writes_performed": 1,
  "mutations_applied": [],
  "mutations_skipped": [],
  "diff_path": ".../apply.diff",
  "verify": {
    "preconditions_passed": true,
    "postconditions_passed": true,
    "rollback_rehearsal_available": true
  },
  "rollback_command": "openclaw-mem self-curator rollback --receipt ..."
}
```

## Invariants

- Every apply must create a checkpoint before the first write.
- Every write must be listed in the plan.
- Every target must have a precondition hash or exact text precondition.
- Any precondition mismatch fails closed before writes.
- Apply receipt must include before/after hashes and a diff artifact.
- Rollback must restore file bytes from checkpoint, not attempt inverse fuzzy edits.
- v1 may mutate whitelisted skill/config surfaces, but authority/canon surfaces remain later-gated.

## Verifier plan

1. Unit tests:
   - plan validation rejects path traversal and unwhitelisted targets.
   - apply creates checkpoint before write.
   - precondition mismatch performs zero writes.
   - rollback restores exact original SHA-256.
2. CLI smoke:
   - fixture skill with missing description.
   - plan fills description.
   - apply changes file, emits diff/receipt.
   - verify passes.
   - rollback restores original hash.
3. Counterfactual smoke:
   - mutate target between plan and apply; apply must fail closed with `writes_performed=0`.

## Topology/config impact

Unchanged for v1 implementation until an explicit cron/controller enablement slice. This is a manual apply-capable CLI lane first.

## WAL closure requirement

Any apply-capable release must write:

- implementation receipt
- verifier receipts
- rollback smoke receipt
- docs update
- daily memory/WAL entry
- tag after push once clean
