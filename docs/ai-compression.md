# AI compression ("summarize") — governance + operator contract

This doc defines how we use LLM-assisted compression in `openclaw-mem` without turning it into a silent-footgun.

## What AI compression is
Compression turns high-volume, low-signal logs into a smaller set of **derived notes**.

It is not a replacement for retrieval. It is a way to keep the *operator surface* readable.

## Decision (default posture)
- Compression output is a **derived artifact by default**.
- We do **not** auto-promote compressed text into durable memory.
- We do **not** overwrite operator-authored files.

Rationale: a bad summary is worse than no summary, because it creates false confidence.

## Required guardrails

### 1) Deterministic input selection
- Select a bounded input window (e.g., one day, or N records).
- Prefer importance/trust-aware selection (must > nice > unknown, cap the rest).

### 2) Hard caps (cost + length)
- Always set a hard output limit (e.g., `max_tokens <= 700`).
- Limit frequency (daily or less) unless explicitly justified.

### 3) Receipts (must be debuggable)
Every compression run must record:
- time window / input selection rules
- model + max_tokens
- output length
- a pointer to the derived artifact path

### 4) Fail-open
If compression fails:
- ingest/harvest/triage must still work
- the system should remain operable (no broken pipeline)

### 5) Rollback
Rollback is simple:
- ignore/delete the derived artifact
- re-run compression from raw sources

## Implementation status
- `openclaw-mem summarize` exists (CLI).
- The governance contract above is the acceptance bar for making it part of daily ops.

## Future: promotion (explicit, reviewed)
If we later decide to promote compressed notes into durable memory, it must be:
- explicit (operator-reviewed)
- reversible (archive-first)
- tracked (receipts + provenance)
