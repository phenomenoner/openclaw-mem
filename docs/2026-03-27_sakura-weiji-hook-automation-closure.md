# 2026-03-27 — Sakura Wei Ji Hook Automation Closure

Repo: `openclaw-mem`  
Companion repo: `delirium-to-weiji`

## Verdict
Wei Ji is now wired into the highest-ROI OpenClaw lane: **`memory_store` can auto-run Wei Ji preflight before memory is written**.

This slice lands the real automation wedge CK asked for:
- the operator does **not** need to remember a wrapper command for the explicit memory-write moment,
- the flow can ask Wei Ji automatically,
- the posture stays advisory-first + rollbackable.

## What changed

### Code
- added helper module:
  - `extensions/openclaw-mem-engine/weiJiMemoryPreflight.js`
- added helper tests:
  - `extensions/openclaw-mem-engine/weiJiMemoryPreflight.test.mjs`
- wired helper into `extensions/openclaw-mem-engine/index.ts`
  - new config gate: `weijiMemoryPreflight`
  - `memory_store` now builds an OpenClaw-style memory intent and calls Wei Ji before `db.add`
  - receipts surface under:
    - `memory_store.details.receipt.weiJiMemoryPreflight`
  - blocked policy result returns:
    - `error = "weiji_memory_preflight_blocked"`
    - no memory is stored
  - runtime failures honor `failMode`
    - `open` => allow write, keep receipt
    - `closed` => block write

### Config / manifest
- updated `extensions/openclaw-mem-engine/openclaw.plugin.json`
  - config schema for `weijiMemoryPreflight`
  - UI hints for command / dbPath / fail mode / fail-on flags
- host config enabled on this machine in:
  - `/root/.openclaw/openclaw.json`

Current host posture:
```jsonc
"weijiMemoryPreflight": {
  "enabled": true,
  "command": "uv",
  "commandArgs": [
    "run",
    "--project",
    "/root/.openclaw/workspace/delirium-to-weiji",
    "weiji-memory-preflight"
  ],
  "dbPath": "/root/.openclaw/workspace/delirium-to-weiji/.state/d2w/verdicts.sqlite3",
  "timeoutMs": 12000,
  "failMode": "open",
  "failOnQueued": false,
  "failOnRejected": false
}
```

### Docs
- updated:
  - `extensions/openclaw-mem-engine/README.md`
  - `docs/mem-engine.md`
- added:
  - `docs/2026-03-27_sakura-weiji-hook-automation-blade-map.md`
  - `docs/2026-03-27_sakura-weiji-hook-automation-closure.md`

## Verifier receipts

### Focused helper tests
```bash
node --test extensions/openclaw-mem-engine/weiJiMemoryPreflight.test.mjs
```
Result:
- **5 passed**

### Helper live subprocess smoke
```bash
node --input-type=module - <<'JS'
import { runWeiJiMemoryPreflight } from './extensions/openclaw-mem-engine/weiJiMemoryPreflight.js';
const out = await runWeiJiMemoryPreflight({
  intent: {
    id: 'live-helper-smoke-2026-03-27',
    tool: 'memory_store',
    source: 'manual-smoke',
    scope: 'global',
    category: 'other',
    text: 'TEMP HELPER SMOKE — verify plugin-to-Wei-Ji subprocess contract',
    importance: 0.2,
  },
  config: {
    enabled: true,
    command: 'uv',
    commandArgs: ['run', '--project', '/root/.openclaw/workspace/delirium-to-weiji', 'weiji-memory-preflight'],
    dbPath: '/root/.openclaw/workspace/delirium-to-weiji/.state/d2w/verdicts.sqlite3',
    timeoutMs: 12000,
    failMode: 'open',
    failOnQueued: false,
    failOnRejected: false,
  },
});
console.log(JSON.stringify(out, null, 2));
JS
```
Observed key result:
- `allowed = true`
- `blocked = false`
- `decision = allow`
- `mode = advisory`
- `wrapperExitCode = 0`
- `governorStatus = queued`
- `runtimeFailed = false`

### Host runtime receipt
Observed plugin registration on this host includes:
- `weijiMemoryPreflight=advisory|open|cmd=uv`

### Live memory tool smoke
A temporary `memory_store` + immediate `memory_forget` smoke was run from the main OpenClaw session to confirm the lane remains operational while the gate is enabled.

## Checkpoint / closeout lane
Status: **deferred**

Reason:
- not a clear low-risk hook surface in this plugin slice,
- would require broader OpenClaw command/runtime interception work,
- violates the bounded-ROI posture of this automation line if forced here.

## Topology statement
- **Changed:** plugin behavior (`memory_store` pre-write gate), plugin config schema/hints, host config for the new gate, operator docs
- **Unchanged:** persistence topology, human-gated review model, checkpoint/closeout runtime topology

## Rollback
Fast rollback options:
1. set `plugins.entries.openclaw-mem-engine.config.weijiMemoryPreflight.enabled = false`
2. restart the gateway / foreground runtime

Stronger rollback:
1. disable the gate as above
2. or switch `plugins.slots.memory` back to `memory-lancedb` / `memory-core`
3. restart runtime

## Skill decision
Do **not** create a new OpenClaw skill for this automation line.

Reason:
- this value now lives below the skill layer as a product/runtime behavior,
- the right move is to **update the existing Wei Ji skill docs** so they mention the live memory-store automation lane,
- not to add a second skill that duplicates the same authority surface.
