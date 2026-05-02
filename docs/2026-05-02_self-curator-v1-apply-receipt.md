# Self Curator v1 checkpointed apply receipt

Date: 2026-05-02

## Changed truth

`openclaw-mem` Self Curator is now apply-capable. It can mutate relative workspace files through an explicit checkpointed lifecycle:

```text
plan -> checkpoint -> apply -> diff/receipt -> verify -> rollback
```

This absorbs the Hermes Curator design target more fully than the v0 scout: the curator can directly change files, including patch/write/move/archive/frontmatter operations, but every apply is preconditioned, checkpointed, receipted, verifiable, and rollbackable.

## CLI surface

```bash
openclaw-mem self-curator skill-review ...
openclaw-mem self-curator plan --mutations-file mutations.json --out plan.json --workspace-root . --json
openclaw-mem self-curator apply --plan plan.json --workspace-root . --checkpoint-root .state/self-curator/checkpoints --receipt-root .state/self-curator/apply-runs --json
openclaw-mem self-curator verify --receipt .state/self-curator/apply-runs/<run>/apply-receipt.json --json
openclaw-mem self-curator rollback --receipt .state/self-curator/apply-runs/<run>/apply-receipt.json --json
```

## Mutation classes shipped

- `replace_text`
- `write_file`
- `move_file`
- `archive_file`
- `set_frontmatter_field`

## Safety posture

- Targets must be relative paths under `--workspace-root`; traversal/absolute paths are rejected.
- Existing directory targets are rejected.
- Checkpoints are created before writes.
- Preconditions can require exact SHA-256, existence, or required text.
- Any mutation failure or exception restores from checkpoint and returns `failed_closed`.
- Move/archive destination hashes are stored and verified.
- Rollback restores pre-apply bytes and removes paths that did not exist before.
- Topology/config impact: **unchanged**. No cron or runtime integration enabled.

## Verification receipts

Primary test command:

```text
uv run -- python -m py_compile openclaw_mem/self_curator.py openclaw_mem/cli.py
uv run -- python -m unittest tests.test_self_curator -q
```

Result:

```text
Ran 13 tests
OK
```

CLI smoke:

```text
self-curator plan -> apply -> verify -> rollback
```

Result:

- apply emitted `openclaw.curator.apply-receipt.v1`
- verify emitted `openclaw.curator.verify-receipt.v1` with `ok=true`
- rollback emitted `openclaw.curator.rollback-receipt.v1` with `ok=true`
- source file hash after rollback matched pre-apply hash

## Independent QA

Three QA passes were run during implementation:

1. Stage 1 QA found exception atomicity, weak verify, weak rollback absent-path handling, directory target, and CLI wording gaps.
2. Stage 2 QA found two remaining must-fixes: first-mutation partial-write exception restore and move/archive destination hash verification.
3. Final QA passed: no remaining must-fix; OK to commit/tag.

## Rollback posture

Repo rollback:

```bash
git revert <self-curator-v1-commit>
```

Apply rollback for curator-run mutations:

```bash
openclaw-mem self-curator rollback --receipt <apply-receipt.json> --json
```

Pre-change snapshot root for this implementation line:

```text
/root/.openclaw/workspace/.state/self-curator/snapshots/20260502-1932-self-curator-v1-apply/
```

## Stale-rule sweep

No active rule surface contradicts the new v1 posture after README/spec update: Self Curator is no longer described as permanently review-only. v0 remains a scout; v1 is checkpointed apply.

## Remaining follow-up

- Cron/autonomous scheduling remains intentionally disabled until a separate controller enablement slice.
- Broader authority/canon mutation needs a stricter gate if ever enabled.
- LLM-generated mutation plans should remain separate from this deterministic apply engine until plan validation and QA mature further.
