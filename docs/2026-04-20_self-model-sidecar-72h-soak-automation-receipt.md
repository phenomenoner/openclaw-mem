# self-model sidecar 72h soak automation receipt

Date: 2026-04-20
Status: implemented, live-activated

## What changed
- added `openclaw_mem/continuity_soak.py` as the bounded soak evaluator for continuity autorun receipts
- added `tools/self_model_sidecar_soak_controller.py` as the scripts-first controller that:
  - runs one continuity autorun cycle per wake
  - initializes a fresh soak baseline so stale historical residue does not poison a new 72h window
  - writes durable status under `~/.openclaw/memory/openclaw-mem/self-model-sidecar/soak/`
  - emits a clear warning on stale receipts, oversized cadence gaps, or suspicious drift
  - disables its own Gateway cron job after a healthy 72h window closes
- updated operator docs in `README.md`, `docs/deployment.md`, and `skills/self-model-sidecar.ops.md`

## Why
The phase 4-9 code slice was already shipped, but the real gate was still operational: a truthful 72h continuity endurance proof. The right closure move was not another manual checklist. It was one bounded controller that can run unattended, stay quiet while healthy, warn clearly when the lane is broken, and self-close when the target window is satisfied.

## Verification
- `python3 -m unittest tests.test_self_model_sidecar`
  - result: `Ran 13 tests ... OK`
- live controller smoke:
  - first run surfaced the real residue problem (`receipt_gap`) caused by an old autorun receipt
  - controller was hardened to start from a fresh baseline instead of over-reading stale history
  - second run returned `NO_REPLY` and wrote:
    - `~/.openclaw/memory/openclaw-mem/self-model-sidecar/soak/baseline.json`
    - `~/.openclaw/memory/openclaw-mem/self-model-sidecar/soak/status.json`
- live Gateway cron activation:
  - job id: `66799dd5-6dc5-48a8-861c-596b8e06930a`
  - name: `self-model-sidecar soak controller (q5m, self-closing)`
  - cadence: every 5 minutes
  - delivery: announce to `discord:user:902441554659123201`
  - failure alerts: enabled, cooldown 1h
- manual cron smoke:
  - `openclaw cron run 66799dd5-6dc5-48a8-861c-596b8e06930a`
  - `openclaw cron runs --id 66799dd5-6dc5-48a8-861c-596b8e06930a --limit 5`
  - result: latest run finished `ok`, `delivered: false`, consistent with `NO_REPLY` while the soak window is still healthy-but-incomplete

## Durable runtime state
- soak baseline: `/root/.openclaw/memory/openclaw-mem/self-model-sidecar/soak/baseline.json`
- live soak status: `/root/.openclaw/memory/openclaw-mem/self-model-sidecar/soak/status.json`
- closure/warning receipts: `/root/.openclaw/memory/openclaw-mem/self-model-sidecar/soak/`

## Honest status
- the 72h gate is now automated, but not yet complete
- baseline start: `2026-04-20T04:46:43.634458+00:00`
- until the window reaches 72h, this lane should stay quiet on green and only interrupt on warning or final closure

## Topology
- topology changed, bounded and explicit
- one new Gateway cron job was added and enabled for the continuity soak controller
- no gateway restart was required for this pass
