# Self-improvement goal pilot receipt — 2026-05-12

## Summary

Implemented the first OpenClaw Mem self-improvement consolidation slice:

- shared read-only surface inventory / receipt validation substrate
- read-only `goal status` command
- public-facing Advanced Labs documentation
- ops skill card
- local install smoke

No cron, gateway, plugin config, model routing, or external delivery topology changed.

## Changed files

- `openclaw_mem/self_improvement_surface.py`
- `openclaw_mem/goal_primitive.py`
- `openclaw_mem/cli.py`
- `tests/test_self_improvement_surface.py`
- `tests/test_goal_primitive.py`
- `docs/self-improvement-goal-pilot.md`
- `docs/specs/self-improvement-goal-pilot-blade-map-v0.md`
- `skills/goal-primitive.ops.md`
- `mkdocs.yml`

## Verification

### Unit tests

Command:

```bash
uv run python -m pytest tests/test_self_improvement_surface.py tests/test_goal_primitive.py tests/test_active_line_context.py
```

Result:

```text
17 passed in 0.08s
```

### CLI smoke

Commands exercised:

```bash
uv run python -m openclaw_mem surface validate \
  --inventory .state/self-improvement-goal-pilot/smoke/surfaces.valid.json \
  --receipt .state/self-improvement-goal-pilot/smoke/receipt.safe.json \
  --out .state/self-improvement-goal-pilot/smoke/surface-valid.receipt.json \
  --json

uv run python -m openclaw_mem surface validate \
  --inventory .state/self-improvement-goal-pilot/smoke/surfaces.valid.json \
  --receipt .state/self-improvement-goal-pilot/smoke/receipt.blocked.json \
  --json

uv run python -m openclaw_mem goal status \
  --file .state/self-improvement-goal-pilot/smoke/goal.active.json \
  --out .state/self-improvement-goal-pilot/smoke/goal-status.receipt.json \
  --json
```

Assertions:

- safe surface validation returns `ok=true` and `writes_performed=false`
- protected-surface blocked receipt returns `ok=false` and `protected_touched=true`
- goal status returns `ok=true`, `writes_performed=false`, and `goal.active=true`
- default `goal status` receipt does not leak the input file path through `source_ref`

### Documentation build

Command:

```bash
uv run --with mkdocs --with mkdocs-material mkdocs build --strict
```

Result: documentation built successfully.

### Public-facing review

Claude second-brain review was run twice before public push.

First review verdict: hold for fixes.

Must-fix items addressed:

- removed default local path leak from `goal status` `source_ref`
- replaced internal continuation owner example with neutral `operator`
- removed undefined comparator jargon from public docs
- tightened authority validation for non-empty `applied[]`, `writes_performed=true`, protected L3, and L4 surfaces
- clarified CLI help text and public doc authority wording

Second review verdict:

```text
clear to push — no must-fix blockers
```

Review artifacts are under `.state/self-improvement-goal-pilot/` in the working tree.

### Local install smoke

Command:

```bash
uv tool install --force --editable .
```

Result:

```text
Installed 3 executables: openclaw-mem, openclaw-mem-gateway, openclaw-mem-pack-capsule
```

Installed CLI smoke:

```bash
openclaw-mem goal status --file .state/self-improvement-goal-pilot/smoke/goal.active.json --json
openclaw-mem surface validate --inventory .state/self-improvement-goal-pilot/smoke/surfaces.valid.json --receipt .state/self-improvement-goal-pilot/smoke/receipt.safe.json --json
```

Result: installed `openclaw-mem` smoke passed.

## Counterfactual coverage

- invalid inventory state fails validation
- protected L3 surface rejects `stage` authority
- protected L3 surface accepts sufficient `apply-local` authority
- L4 surface requires `apply-publish`
- non-empty `applied[]` requires at least `suggest`
- `writes_performed=true` requires at least `apply-local`
- unknown surface id warns rather than failing when policy context is absent
- invalid goal status fails validation

## Topology impact

Unchanged.

No cron, gateway, plugin config, model routing, or channel routing changes were made.

## Rollback

Revert the implementation commit or remove the listed files/CLI registrations. Local editable install can be restored by reinstalling from the previous `openclaw-mem` checkout or tag.
