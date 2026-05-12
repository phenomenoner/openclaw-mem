# Self-improvement consolidation slices 2–5 — blade map v0

Date: 2026-05-12
Status: implementation blade map

## Goal

Complete the next read-only/staged-only product skeleton for OpenClaw Mem self-improvement consolidation:

2. Goal survival pack seam.
3. `skill_capture` staged proposal path.
4. Skill Curator report-only review surface.
5. OpenClaw Mem System status surface.

## Non-goals

- No auto-continuation runtime.
- No automatic skill mutation.
- No governed apply enablement.
- No cron, gateway, plugin config, or model-routing changes.
- No L3/L4 live mutation.

## Outputs / artifacts

- New/updated CLI surfaces for goal pack, skill capture, skill-curator review alias, and mem-system status.
- Unit tests for each slice.
- Public docs and ops skill updates.
- Claude second-brain public review before push.
- Local install smoke.
- WAL update and public PR/tag if the slice is merged.

## Invariants

- Goal pack and mem-system status are read-only.
- Skill capture writes only explicit L1 staged proposal artifacts under `--out` / `--out-dir`; it never patches live skills.
- Skill curator review remains non-mutating and proposal/report-only; it may write explicit review artifacts under `--out-root` but never applies patches.
- Topology remains unchanged.

## Verifier plan

- targeted pytest for new modules, CLI integration, and affected existing goal/active-line tests
- CLI smoke for each new command
- mkdocs strict build
- Claude public-facing review
- local editable install smoke
- PR CI readback before merge

## Rollback

Revert the implementation commit or delete the feature branch before merge. No runtime topology rollback is needed because no cron/gateway/config changes are allowed in this batch.
