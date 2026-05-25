# Memory Strata WS6 Bootstrap Slimming Audit — 2026-05-25

Status: **completed / read-only pre-audit**  
Companion: `docs/specs/memory-strata-todo-v0.md#ws6--docs-cold-lane-and-bootstrap-slimming`  
Topology/data impact: **unchanged** — no file moves, deletions, config changes, or retrieval changes.

## Goal

Identify which `MEMORY.md` and `AGENTS.md` sections are bootstrap-hot vs candidate-cold, without moving any content yet.

## File sizes

- `MEMORY.md`: 13,753 bytes / 107 lines
- `AGENTS.md`: 11,972 bytes / 100 lines

## Hot-required vs candidate-cold

### MEMORY.md
- hot-required: Core stance, Execution defaults, Acceleration / non-stop, Blockers / stop-loss, Push / closure / authority, Memory / openclaw-mem canon
- candidate-cold: Standing lane defaults, Named triggers, Journals / writing / media, Project notes that should not drift

### AGENTS.md
- hot-required: 1) Core stance, 2) Context hygiene, 3) Execution defaults, 4) Acceleration / non-stop, 5) Stop-loss, 6) Ops + closure hygiene
- candidate-cold: 7) Standing defaults / lanes, 8) Named triggers, 9) Read-when-relevant appendix map

## Candidate destinations (proposal only)

```json
{
  "MEMORY.md": {
    "Standing lane defaults": "openclaw-mem/docs/specs/bootstrap-lane-defaults-cold-v0.md",
    "Named triggers": "openclaw-mem/docs/specs/bootstrap-named-triggers-cold-v0.md",
    "Journals / writing / media": "openclaw-mem/docs/specs/bootstrap-journals-media-cold-v0.md",
    "Project notes that should not drift": "openclaw-mem/docs/specs/bootstrap-project-notes-cold-v0.md"
  },
  "AGENTS.md": {
    "7) Standing defaults / lanes": "openclaw-mem/docs/specs/bootstrap-standing-defaults-cold-v0.md",
    "8) Named triggers": "openclaw-mem/docs/specs/bootstrap-agents-named-triggers-cold-v0.md",
    "9) Read-when-relevant appendix map": "openclaw-mem/docs/specs/bootstrap-appendix-map-cold-v0.md"
  }
}
```

## Blocking rule

No moves/deletes happen in WS6 pre-audit. Any actual slimming move must preserve retrieval quality and satisfy:

- pre/post file-size receipt
- retrieval test for every moved high-value rule
- diff review proving no authority boundary loss
- second-brain review before applying

## Closure

WS6 pre-audit is complete. This is inventory/planning only, not bootstrap mutation.
