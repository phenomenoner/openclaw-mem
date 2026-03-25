# Automation status (main-only) — what is automatic vs cron vs not yet wired

This page is the operator-facing truth for `openclaw-mem` on our host.

The system is intentionally split into layers:
- **Plugin (sidecar)** captures observations.
- **Cron (operator automation)** runs ingest/triage and related loops.
- Some features exist as CLI tools but are **not yet auto-wired** into the default agent loop.

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

### Harvest + triage (main)
- MAIN baseline: `a9f3066a-43ac-40b3-aacc-dcfa44e9106e` (`:05`)
  - code root: `/root/.openclaw/workspace/openclaw-mem` (main)
  - DB: `/root/.openclaw/memory/openclaw-mem.sqlite`
  - receipts: `/root/.openclaw/memory/openclaw-mem/{harvest_last.json,triage_last.json}`

### Feature lanes (A-fast / A-deep, main-governed)
- A-fast: `57d3e88c-4278-414a-8e33-c091baae7887`
- A-deep: `30adb125-88b9-4f2f-a644-5271baab7c0b`
- governance: lane packets converge to `main`; no long-lived `dev` integration branch contract
- lock: `openclaw-mem-dev-feature` + global heavy-python guard (legacy lock name retained)

### AI compression (derived artifact)
- Job: `58a7c87c-d1b2-4c9c-96fd-6ecccf623b85` (daily 00:35 Asia/Taipei)
- Output (derived): `/root/.openclaw/workspace/memory/compressed/YYYY-MM-DD.md`
- Receipt: `/root/.openclaw/workspace/memory/compressed/receipts/YYYY-MM-DD.json`
- Governance: derived-by-default, no durable promotion (see `docs/ai-compression.md`)

### Graphic Memory — auto-capture (git commits)
- Job: `01761d59-adfc-4413-bd12-2ecd616e3029` (2/day: 01:13, 13:13 Asia/Taipei)
- Spec: `/root/.openclaw/workspace/openclaw-async-coding-playbook/cron/jobs/01761d59-adfc-4413-bd12-2ecd616e3029.md`
- DB: `/root/.openclaw/memory/openclaw-mem.sqlite`
- State cursor (default): `OPENCLAW_STATE_DIR/memory/openclaw-mem/graph-capture-state.json`

### Graphic Memory — auto-capture (markdown index-only)
- Job: `04e3d483-40bc-4d51-822e-4a1eb2252a7b` (q12h)
- Spec: `/root/.openclaw/workspace/openclaw-async-coding-playbook/cron/jobs/04e3d483-40bc-4d51-822e-4a1eb2252a7b.md`
- DB: `/root/.openclaw/memory/openclaw-mem.sqlite`
- State cursor (default): `OPENCLAW_STATE_DIR/memory/openclaw-mem/graph-capture-md-state.json`

## 3) Exists (CLI) but NOT yet auto-wired (waiting for further decisions)

### Context Packer (`pack`)
- `pack` exists and supports `--trace` receipts.
- Not yet wired as the default per-request context feeder for OpenClaw.

Why not wired yet:
- We want a clear promotion gate and a burn-in window.
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
