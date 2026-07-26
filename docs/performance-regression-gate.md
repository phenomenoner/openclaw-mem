# Performance Regression Gate

The scheduled `nightly-perf` job protects the published 100k performance
thresholds and absolute product SLOs. It deliberately keeps the existing
`pack.e2e_p95_ms < 300` contract instead of widening the limit when a shared
GitHub-hosted runner produces an isolated pause.

## Sampling and diagnostics

- The pack lane measures 50 indexed calls after warmup. This is large enough
  for one isolated host pause to remain visible as `max_ms` without dominating
  the p95 statistic.
- The receipt records the five slowest timed samples.
- The three slowest queries are replayed with `pack --trace`; replay totals and
  stage timings are diagnostic evidence and do not replace the original timed
  samples.

## Confirmation policy

Scheduled and manually dispatched workflows run one confirmation attempt only
when the first 100k gate fails. The job fails when the confirmation attempt
also fails. Both attempt receipts are uploaded when confirmation is needed,
preserving evidence for real regressions while reducing false alarms from a
single hosted-runner stall.

## Changelog

- 2026-07-27: increased pack sampling from 20 to 50, added slow-sample and
  traced-replay diagnostics, added one fail-confirmation attempt, and exposed
  manual workflow dispatch without changing stored thresholds or the 300 ms
  pack SLO.
