# Self-improvement consolidation goal pilot — blade map v0

Date: 2026-05-12
Status: implementation blade map

## Goal

Ship the first OpenClaw Mem consolidation slice from the self-improvement plan:

1. Shared governance substrate for self-improvement surfaces.
2. Read-only `goal status` pilot as the first low-blast-radius product slice.
3. Public-facing docs and ops skill guidance.
4. Local install/readback proof.

## Non-goals

- No live auto-continuation runtime.
- No automatic skill mutation.
- No public push before review.
- No retirement of legacy memory surfaces.
- No cron or OpenClaw gateway topology changes.

## Inputs

- Ledger report: `lyria-working-ledger/REPORTS/openclaw/2026-05-12_openclaw-self-improvement-consolidation-plan.md`
- Existing openclaw-mem surfaces:
  - `active-line pack`
  - `self-curator`
  - `steward review`
  - `ingest-review source`

## Outputs / artifacts

- Python substrate module for surface inventory / receipt validation.
- CLI commands:
  - `openclaw-mem surface validate ...`
  - `openclaw-mem goal status ...`
- Unit tests for inventory/receipt validation and goal status.
- Public-facing docs.
- Ops skill card/update.
- Review receipt from Claude second brain before public push.
- WAL / ledger handoff.

## Invariants

- Commands are read-only unless writing an explicit `--out` receipt/report.
- `writes_performed=false` for Phase -1 and `goal status` commands.
- Protected surfaces cannot appear in `applied[]` without sufficient authority.
- `registerContextEngine` remains the recommended compaction-safe seam; this slice does not implement runtime context-engine integration.
- Existing CLI commands keep behavior.

## Topology / config impact

Unchanged. No cron, plugin config, gateway, or model-routing changes.

## Verifier plan

Dry-run / direct tests:

- `python -m pytest tests/test_self_improvement_surface.py tests/test_goal_primitive.py tests/test_active_line_context.py`
- `python -m openclaw_mem surface validate --inventory <fixture> --receipt <fixture> --json`
- `python -m openclaw_mem goal status --file <fixture> --json --out <receipt>`

Counterfactuals:

- invalid inventory state fails validation
- protected surface with unauthorized `applied[]` fails validation
- malformed goal receipt fails with bounded error

Live local install smoke:

- `python -m pip install -e .`
- `openclaw-mem goal status --file <fixture> --json`
- `openclaw-mem surface validate --inventory <fixture> --receipt <fixture> --json`

Human-readable report:

- `docs/2026-05-12_self-improvement-goal-pilot-receipt.md`

Rollback posture:

- Revert this branch commit or remove the new module/tests/docs and CLI registrations.
