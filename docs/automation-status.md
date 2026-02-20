# Automation status (dev) — what is automatic vs cron vs not yet wired

This page is the operator-facing truth for `openclaw-mem` on our host.

The system is intentionally split into layers:
- **Plugin (sidecar)** captures observations.
- **Cron (operator automation)** runs ingest/triage and other loops.
- Some features exist as CLI tools but are **not yet auto-wired** into the agent loop.

## 1) Automatic (plugin / sidecar) — already running
These happen automatically once the OpenClaw plugin is enabled.

- Capture: writes JSONL observations
  - output: `/root/.openclaw/memory/openclaw-mem-observations.jsonl`
- Backend annotations (observability): tags memory backend + memory tool actions
- Redaction/denoise:
  - `captureMessage=false`
  - exclude noisy/sensitive tools (exec/read/browser/message/gateway/nodes/canvas)

What this layer does *not* do:
- it does not run harvest/ingest into SQLite
- it does not run context packing
- it does not run AI compression

## 2) Automatic (cron) — scheduled operator loops
These are automated via OpenClaw cron jobs (so the system works without manual CLI calls).

### Harvest + triage (dual-run)
- MAIN baseline: `a9f3066a-43ac-40b3-aacc-dcfa44e9106e` (`:05`)
  - code root: `/root/.openclaw/workspace/openclaw-mem` (main)
  - DB: `/root/.openclaw/memory/openclaw-mem.sqlite`
  - receipts: `/root/.openclaw/memory/openclaw-mem/{harvest_last.json,triage_last.json}`
- DEV candidate: `8c69db59-abee-4b8f-8778-5bb5951454ab` (`:25`)
  - code root: `/root/.openclaw/workspace/openclaw-mem-dev` (dev)
  - DB: `/root/.openclaw/memory/openclaw-mem-dev.sqlite`
  - receipts: `/root/.openclaw/memory/openclaw-mem-dev/{harvest_last.json,triage_last.json}`

### AI compression (derived artifact, dev)
- Job: `58a7c87c-d1b2-4c9c-96fd-6ecccf623b85` (daily 00:35 Asia/Taipei)
- Output (derived): `/root/.openclaw/workspace/memory/compressed/YYYY-MM-DD.md`
- Receipt: `/root/.openclaw/workspace/memory/compressed/receipts/YYYY-MM-DD.json`
- Governance: derived-by-default, no durable promotion (see `docs/ai-compression.md`)

## 3) Exists (CLI) but NOT yet auto-wired (waiting for further decisions)

### Context Packer (`pack`)
- `pack` exists and supports `--trace` receipts.
- Not yet wired as the default per-request context feeder for OpenClaw.

Why not wired yet:
- We want a clear promotion gate (dev → main) and a burn-in window.
- We need confidence on determinism, privacy/redaction, and operator debuggability.

Current pilot sequencing (2026-02):
- **Pillar A (build now):** contract hardening + citation/rationale coverage + benchmark receipts.
- **Pillar B (spec now):** learning-record lifecycle/bench specs only, no runtime rollout yet.
- Any scheduler adjustments remain spec-only in this phase (no live cron mutations here).

### Promotion of compression output into durable memory
- Not enabled.
- Promotion (if any) must be explicit + reviewed + reversible.

### Graph semantic memory
- Not implemented.
- Needs schema/storage/benchmark decisions first.
