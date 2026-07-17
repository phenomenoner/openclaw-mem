# File-driven development practice

Purpose: keep `openclaw-mem` development driven by explicit files instead of chat memory.

## Session loop

1. Read `docs/archive/project-management-2026-06-12/next-step.md`.
2. Read only the backlog items referenced by `currentFocus`.
3. If the next task has an unresolved `confirmationGate`, stop and ask CK.
4. If the next task is clear, implement the smallest rollbackable slice.
5. Add or update a receipt under this archived folder's `receipts/` directory.
6. Update `next-step.md` and `progress-checklist.html` with:
   - completed item ids
   - exact receipt paths
   - next recommended item
   - blocker, if any

## Status vocabulary

- `todo`: accepted backlog, not started.
- `ready`: dependencies and confirmation gates are clear.
- `active`: current implementation slice.
- `blocked`: cannot move without CK or external state.
- `done`: implemented and verified.
- `deferred`: intentionally postponed, with reason.
- `icebox`: explicitly not scheduled.

## File creation rules

- Planning/control files lived under the now-archived project-management folder.
- The browser checklist is `docs/archive/project-management-2026-06-12/progress-checklist.html`.
- Public product specs still live under `docs/specs/` when they become real user-facing contracts.
- Receipts live under `docs/archive/project-management-2026-06-12/receipts/`.
- Benchmark outputs live under `benchmarks/` or `docs/showcase/artifacts/` when public-safe.
- Do not mix internal phase management into `README.md`, `QUICKSTART.md`, or public docs until the corresponding slice is implemented.

## Definition of done for a backlog item

Each item needs:

- code or docs change committed in the repo working tree
- test, smoke, or explicit "not run" note
- receipt path
- rollback note if behavior changed
- `phase-backlog.md` status update
- `next-step.md` pointer to the next task

## Cut-line discipline

P0 and P1 are contract and positioning gates. Do not spend implementation time on P2/P3 retrieval or governance depth until the active P0/P1 gates are either done or explicitly deferred.

Default order:

1. P0-4 one-sentence story.
2. P0-8 SQLite internal schema version marker.
3. P1-8 channel A file contract producer.
4. P1-1 MCP server v1.

## Confirmation gates

Ask CK before changing:

- public schema id or field casing
- PyPI package rename / alias behavior
- removal or deprecation of legacy gateway surfaces
- benchmark publication claims
- external posts, PRs to other repos, launch materials
