# Plan: dual-language memory rollout (2026-02-07)

## Scope
Roll out support for original text + optional English companion fields (`text`, `text_en`) with safe fallback retrieval.

## Phase 0 — Prep
- Confirm schema/field contract for `text`, `text_en`, language metadata.
- Add metrics instrumentation for usage/latency/failure KPIs.
- Define baseline numbers from current single-language behavior.

## Phase 1 — Write-path enablement
- Accept/store `text_en` without making it required.
- Preserve `text` as canonical field.
- Mark translation provenance/status where available.

## Phase 2 — Read-path fallback
- Keep primary single-language retrieval unchanged.
- Add optional `query_en` fallback path when primary confidence is low.
- Merge/deduplicate candidates with stable scoring.

## Phase 3 — Evaluation and tuning
- Run labeled zh/en/mixed query set.
- Tune fallback trigger thresholds and limits.
- Compare against baseline: empty-result rate, top-k hit rate, p95 latency.

## Phase 4 — Default-on policy
- Enable dual-language fallback by default for mixed-language environments.
- Keep feature flag for immediate rollback.
- Publish operator guidance + KPI dashboard checks.

## Rollback checklist
- [ ] Disable dual-language fallback feature flag.
- [ ] Route queries back to single-language path only.
- [ ] Verify latency and failure rates return to baseline band.
- [ ] Keep stored `text_en` data (no destructive migration).
- [ ] Record incident summary and threshold updates before re-enable.
