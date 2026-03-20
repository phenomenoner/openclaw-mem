# Decision: QMD fit policy for openclaw-mem-dev (2026-02-20)

## Decision
We will **not** make QMD a hard runtime dependency of openclaw-mem-dev.

Instead, we integrate QMD conclusions as:
- design patterns (lexical anchors → semantic fallback → optional rerank)
- versioned contracts (`pack --trace` schema + receipts)
- benchmarkable hypotheses (golden corpus + regression gates)
- opt-in flags + shadow mode (observe first; promote only after proven wins)

## Rationale
- openclaw-mem is designed as a sidecar and does not replace OpenClaw canonical backends.
- dev roadmap already points to a QMD-style retrieval router; highest leverage is contract + benchmark hardening.
- QMD runtime introduces cold-start costs/model downloads/background refresh expectations that must remain explicit opt-in.

## Non-goals (for now)
- Query expansion default-on
- Always-on background indexing/refresh
- Silent behavior changes without receipts

## Receipt
- 4A trace pack (Captain+Harper+Benjamin+Lucas):
  - `openclaw-async-coding-playbook/projects/openclaw-mem/artifacts/4a/20260220/qmd-fit-into-openclaw-mem-dev/`
