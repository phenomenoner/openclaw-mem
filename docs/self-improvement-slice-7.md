# Self-improvement Slice 7: governed apply and release hardening

Slice 7 adds review-only governance checks around the Slice 6 mutation framework and release process.

It does not enable automatic mutation of production surfaces. It makes approval boundaries and release-readiness gates visible as receipts.

## Commands

Review a mutation plan against approval boundaries:

```bash
openclaw-mem governed apply-review \
  --plan-file plan.json \
  --allowed-root .state/mutation-framework/sandbox \
  --json
```

Run a release gate check:

```bash
openclaw-mem governed release-check \
  --repo-root . \
  --expected-version 1.9.15 \
  --json
```

## Apply-review policy

- L0/L1: may receive an advisory allow decision for local fixture apply when the Slice 6 plan validates.
- L2: requires explicit `--l2-enabled` config gate for an advisory allow decision.
- L3: requires human approval and is still not auto-applyable in this slice.
- L4: requires CK approval and is still not auto-applyable in this slice.

Slice 7 records approval flags; it does not turn L3/L4 into automatic apply.

## Release-check policy

The release check verifies:

- `pyproject.toml` version matches `openclaw_mem/__init__.py`
- `uv.lock` mentions the expected version
- `CHANGELOG.md` has the expected version entry
- a self-improvement receipt document exists
- public self-improvement docs do not contain known local/private marker strings, including date-prefixed self-improvement receipts

## What this does not enable

- no OpenClaw core changes
- no Gateway or plugin config changes
- no cron changes
- no live skill mutation
- no L3/L4 automatic mutation
- no package publishing
- no tag push by itself

The command emits receipts only. PR merge, tag push, package publishing, and L3/L4 changes remain separate explicit operator actions.
