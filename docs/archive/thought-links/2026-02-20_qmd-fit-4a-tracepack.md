# QMD fit into openclaw-mem-dev — 4A trace pack (2026-02-20)

This note links to a **4A Debate Mode** trace pack that answers:
- How to integrate (or explicitly not integrate) QMD-derived conclusions into the current openclaw-mem-dev design.

## Outcome (one-liner)
Integrate QMD conclusions as **patterns + contracts + benchmarkable hypotheses**, not as a hard runtime dependency. Use flags + shadow mode + regression-gated benchmarks before any default-on behavior changes.

## Trace pack receipt
- Repo: openclaw-async-coding-playbook
- Commit: (see git history; created same day)
- Path:
  - `projects/openclaw-mem/artifacts/4a/20260220/qmd-fit-into-openclaw-mem-dev/`

## Why this exists
- Avoid cargo-culting QMD.
- Keep the default path boring/deterministic.
- Make improvements provable and rollbackable.
