# Contributing / Branch policy (openclaw-mem)

This repo is run like a small, ops-sensitive product: **main stays stable**, experiments land on **dev**, then we merge back when artifact-backed.

## Branch policy

- `main`
  - **Stable line** for releases/tags.
  - Only accept changes that are clearly safe (docs, tests, small fixes) or explicitly approved for release.

- `dev`
  - **Default development line** for new features/experiments (bench hooks, retrieval router prototypes, refactors).
  - May be temporarily messy; should still keep tests passing when practical.

## Local workflow

- Preferred: use worktrees to avoid checkout conflicts with cron/automation:
  - `.../openclaw-mem` (main)
  - `.../openclaw-mem-dev` (dev)

- If you need to change code for a slow-cook job, target **dev** unless the task explicitly says otherwise.

## Merging dev → main

Merge to `main` only when:
- The change is **artifact-backed** (receipts, benchmark report, or reproducible test).
- It is **rollbackable** and does not break local-first defaults.
- Docs are updated (roadmap/thought-links/upgrade notes if applicable).

Process:
1) Open a PR from `dev` → `main` (can be lightweight; no ceremony).
2) Rebase/resolve conflicts.
3) Merge and cut a tag if it is a release.

## Release tags

- Use semantic tags already established (`vX.Y.Z`).
- Update `CHANGELOG.md` if user-facing.
- Keep main green.
