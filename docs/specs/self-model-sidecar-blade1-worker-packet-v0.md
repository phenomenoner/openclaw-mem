# self-model sidecar Blade 1 worker packet v0

Status: draft
Date: 2026-04-18
Scope: first coding slice only
Depends on:
- `docs/specs/self-model-sidecar-contract-v0.md`
- `docs/specs/self-model-sidecar-schema-v0.md`
- `docs/specs/self-model-sidecar-rebuildability-v0.md`
- `docs/specs/self-model-sidecar-msp-execution-blade-map-v0.md`

## Objective
Implement the first read-only continuity surfaces for the self-model side-car:
- `continuity current`
- `continuity attachment-map`

This slice should prove the frozen semantics and schemas in code without touching autonomous scheduling, public release operations, or truth-owner boundaries.

## Scope boundary
In scope:
- domain logic for snapshot derivation on bounded fixture input
- attachment-map derivation on bounded fixture input
- CLI/readout surfaces for `continuity current` and `continuity attachment-map`
- fixture set for at least two clearly different agents
- smoke/integration tests

Out of scope:
- persistence beyond what tests need
- `continuity diff`
- `continuity tension-feed`
- autonomous scheduling/controller wiring
- public release/rebind commands
- broad refactors of existing `openclaw-mem` memory store logic

## Contract rules to obey
- operator noun is `continuity`
- outputs must be labeled derived and non-authoritative
- Nuwa/persona priors are optional weighted inputs only
- attachment strength must use a versioned scoring function
- side-car must not write into memory-of-record
- if semantics are unclear, stop and report against the frozen docs instead of inventing

## Suggested deliverables
1. minimal continuity service/domain module
2. fixture loader or fixture helper
3. `continuity current --json`
4. `continuity attachment-map --json`
5. focused tests and/or smokes
6. example outputs checked in as receipts or fixtures if appropriate

## Verifier plan
Required verifiers:
1. fixture A and fixture B produce clearly distinct `identity_summary`, `core_stances`, and attachment distributions
2. no-op restart fixture does not create fake dramatic drift in the current snapshot shape
3. attachment outputs include provenance, score inputs, and stable join ids
4. CLI output includes derived/non-authoritative posture

Suggested concrete tests:
- `test_continuity_current_fixture_a`
- `test_continuity_current_fixture_b`
- `test_continuity_attachment_map_fixture_a`
- `test_continuity_noop_restart_stability`

## First artifact expected back
Before a broad patch, return one of:
- anomaly list against the frozen contract/schema
- minimal patch plan mapped to files
- or a small first patch with fixture path and one green smoke

## Stop-loss conditions
Stop and report if any occur:
- contract semantics need invention
- schema requires adding undocumented critical fields
- attachment scoring cannot be implemented truthfully from the current docs
- implementation pressure pushes toward writing into base memory-of-record
- repo structure makes CLI surface placement ambiguous enough to risk broad churn

## Files / surfaces to avoid touching
- live cron/controller topology
- optimize-assist surfaces unrelated to continuity
- unrelated memory store schemas
- release/rebind public operator surfaces

## Honest completion condition for Blade 1
Blade 1 is done only when:
- both commands work on fixtures
- verifiers are green
- outputs match frozen contract/schema posture
- no truth-owner boundary was crossed

## What to return if blocked
Return:
- where blocked
- exact file/surface causing ambiguity
- smallest doc/schema change needed
- whether the blocker is semantic, structural, or tooling-related
