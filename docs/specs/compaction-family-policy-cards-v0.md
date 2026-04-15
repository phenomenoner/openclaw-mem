# Compaction family policy cards v0

Status: advisory-only, shipped as `compaction_policy_hints`.

This doc defines the first operator-facing policy cards for command-aware compaction families.
The purpose is narrow:
- help humans and pack traces explain how to use compacted command output,
- preserve deterministic raw recovery,
- avoid turning family labels into retrieval truth or ranking logic.

## Contract boundary

Current shipped output surface:
- `compaction_policy_hints.mode`
- `compaction_policy_hints.family_counts`
- `compaction_policy_hints.preferred_families`
- `compaction_policy_hints.guidance`

Boundary rules:
- advisory only
- no retrieval ranking changes
- no durable-memory branching
- no command-family-specific storage schema
- raw evidence remains recoverable through artifact handle / receipt

## Policy cards

### `git_diff`

Use when compacted output came from diff-style commands.

Examples:
- `git diff --stat`
- compacted diff summaries

Guidance:
- prefer compact summaries first for review and navigation
- rehydrate raw diff before exact line-level claims
- do not treat summary counts alone as proof of semantic correctness

### `test_failures`

Use when compacted output came from test runners.

Examples:
- `pytest -q`
- failing assertion summaries

Guidance:
- prefer compact summaries first for failure triage
- rehydrate raw output for stack traces, exact assertions, and flaky-pattern inspection
- do not collapse multiple failing cases into one truth claim without raw confirmation

### `long_logs`

Use when compacted output came from log-heavy commands.

Examples:
- `docker logs api`
- long service logs

Guidance:
- prefer compact summaries first for scanning and anomaly spotting
- rehydrate bounded raw windows around suspect events
- avoid broad causal claims from compressed log prose alone

### `generic`

Fallback when the command family is unknown or not yet specialized.

Guidance:
- prefer compact summaries first when they reduce noise
- rehydrate raw evidence before exact operational claims
- treat as a temporary neutral family, not a correctness badge

## Why this shape

This keeps Observe stronger without inventing a new subsystem.

- Store still owns durable records
- Pack may prefer compact text for bounded injection
- Observe keeps the provenance and raw-recovery path visible

That is enough to improve operator ergonomics now while leaving future ranking/policy work optional.
