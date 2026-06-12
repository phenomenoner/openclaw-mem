# Project management control files

Status: active internal planning surface.

This folder turns the 2026-06-12 integration optimization phase plan into file-driven project management for `openclaw-mem`.

Use these files as the working surface before changing product code:

- `phase-backlog.md` is the source backlog. It preserves every recommendation from `02-整合優化-Phase規劃與Backlog.md`, mapped into actionable work items.
- `work-practices.md` defines how agents and humans update progress, create new files, and decide the next task from files.
- `next-step.md` is the active control file. Start every development session there.
- `progress-checklist.html` is the browser-readable progress mirror. Update it whenever status changes.

Rules:

- Do not start implementation until the open confirmation gates in `next-step.md` are resolved or explicitly deferred.
- Every implementation slice must create or update one receipt file under `docs/project-management/receipts/`.
- Keep product-facing docs clean. This folder is excluded from MkDocs public output by `mkdocs.yml`.

Current recommendation:

1. Finalize the one-sentence product story.
2. Add the SQLite internal schema version marker.
3. Implement the channel A file contract producer.
