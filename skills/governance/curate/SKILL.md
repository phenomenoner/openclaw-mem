---
name: openclaw-mem-curate
description: >-
  Govern low-risk observation and skill lifecycle maintenance. Use for
  review, planning, policy checks, checkpointed apply, verification, reports,
  and receipt-driven rollback.
metadata:
  ring: 1
  surface: [cli]
  version: 1.9.32
  requires: [openclaw-mem-memory]
---

# Curate Governance

Use the lifecycle: review → plan → policy → checkpoint → apply → verify → report → rollback if requested or verification fails.

## Authority

- Scout with zero-write review before judgment.
- Keep low-risk unattended mutation within the explicit whitelist and mutation cap.
- Report post-hoc apply with exact changed paths and rollback receipt.
- Do not merge scout, governor, and writer authority into one hidden step.
- Run scheduled curation separately from heartbeat health checks.

## Operate

```bash
openclaw-mem optimize evolution-review --json
openclaw-mem optimize governor-review --json
openclaw-mem self-curator skill-review --skill-root <workspace>/skills --json
openclaw-mem self-curator controller --skill-root <workspace>/skills --workspace-root <workspace> --out-root <workspace>/.state/self-curator --mode dry_run --json
openclaw-mem self-curator rollback --receipt <apply-receipt> --json
```

Current scheduled apply may append one bounded `Curator lifecycle` section or archive malformed/very-short skills under `skills/.archive/`. Broader lower-level operations are not automatically authorized.

## Verify

```bash
openclaw-mem self-curator skill-review --skill-root <workspace>/skills --no-write --json
python -m pytest tests/test_self_curator.py -q
git diff --check
```
