# Self-improvement Slice 6: staged mutation framework

Slice 6 introduces a narrow local mutation framework for OpenClaw Mem self-improvement work.

It is intentionally not a general-purpose self-modification runtime. It provides a reviewable `plan → stage → apply → rollback` loop for local fixture files so future governed-apply work can reuse a tested receipt shape.

## Commands

Build a plan:

```bash
openclaw-mem mutation plan --mutations-file mutations.json --out plan.json --json
```

Validate a plan:

```bash
openclaw-mem mutation validate --plan-file plan.json --allowed-root .state/mutation-framework/sandbox --allow-apply --json
```

Stage review artifacts:

```bash
openclaw-mem mutation stage --plan-file plan.json --allowed-root .state/mutation-framework/sandbox --json
```

Apply synthetic/local fixture mutations:

```bash
openclaw-mem mutation apply --plan-file plan.json --allowed-root .state/mutation-framework/sandbox --json
```

Rollback an apply receipt:

```bash
openclaw-mem mutation rollback --receipt .state/mutation-framework/apply-runs/<run>/apply-receipt.json --json
```

## Supported actions

- `write_file`
- `replace_text`

## Safety boundaries

Slice 6 apply is limited to local fixture paths under `--allowed-root`. The default `--allowed-root` is relative to the current working directory; use an absolute path for repeatable operator runs.

Validation blocks L3/L4/protected/manual-approval mutations unconditionally, even when you are only validating and not applying.

It blocks:

- absolute paths
- `..` path traversal
- protected mutations
- L3/L4 mutations
- mutations requiring manual approval
- apply attempts outside the configured allowed root
- missing or empty `mutations` lists in CLI input

If any mutation in a plan fails during apply, the framework restores already-applied changes and returns `failed_closed`. Staging can still write review artifacts for an invalid plan; the stage receipt will have `ok=false` and must not be treated as apply approval.

## What this does not enable

- no OpenClaw core changes
- no Gateway or plugin config changes
- no cron changes
- no live skill mutation
- no governed real apply to production surfaces
- no L3/L4 automatic mutation

## Relationship to Slice 7

Slice 7 can build on this receipt shape to add governed allowlists, approval boundaries, release gates, and stale-rule retirement checks. Slice 6 deliberately stops before those higher-risk live boundaries.
