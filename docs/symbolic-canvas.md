# Symbolic Canvas

`symbolic-canvas` is an additive `openclaw-mem` helper inspired by the useful parts of TencentDB-Agent-Memory's symbolic short-term memory design.

It converts a small task trace into:

- compact Mermaid graph text
- a node index with stable `node_id`s
- refs back to raw evidence/artifacts
- warnings for missing refs or unresolved edges

It performs **no model calls**, **no live capture**, **no Gateway patching**, and **no runtime memory mutation**.

## Why this fits Store / Pack / Observe

| Layer | Role |
|---|---|
| Store | Raw evidence remains in observations, refs, logs, files, or artifacts. The canvas is not the canonical record. |
| Pack | Mermaid + node index can become a compact bounded injection candidate. |
| Observe | `node_id` + refs provide drill-down receipts for debugging, falsification, and rollback. |

## Input shape

```json
{
  "task_id": "example-task",
  "nodes": [
    {"id": "fetch", "label": "Fetch upstream README", "state": "done", "refs": ["refs/readme.md"]},
    {"id": "analyze", "label": "Analyze value items", "state": "running", "result_ref": "refs/analysis.md"}
  ],
  "edges": [["fetch", "analyze", "evidence"]]
}
```

`steps` or `events` may be used instead of `nodes`. If a node has no `id`, a deterministic `node_id` is generated from its position and label.

Supported states: `pending`, `running`, `done`, `blocked`, `failed`, `skipped`, `unknown`.

## Operator skill card

For agent-facing usage guidance, see the repo skill card: [`skills/symbolic-canvas.ops.md`](https://github.com/phenomenoner/openclaw-mem/blob/main/skills/symbolic-canvas.ops.md).

## CLI

```bash
openclaw-mem symbolic-canvas build \
  --from-file trace.json \
  --base-dir . \
  --out .state/canvas.json \
  --mermaid-out .state/canvas.mmd \
  --json
```

The command is file-only. It does not open the memory DB and does not require OpenClaw Gateway changes.


## Opt-in auto-build hook

`openclaw-mem-engine` can optionally build symbolic-canvas receipts on `agent_end` via:

```json
{
  "plugins": {
    "entries": {
      "openclaw-mem-engine": {
        "config": {
          "symbolicCanvas": {
            "autoBuild": {
              "enabled": true,
              "outputDir": "memory/symbolic-canvas-auto",
              "minMessages": 4
            }
          }
        }
      }
    }
  }
}
```

The hook is deliberately observe-only:

- runs only when explicitly enabled
- listens at `agent_end` and derives a bounded user/assistant message trace
- writes JSON + Mermaid receipts under the configured state-relative `outputDir`
- performs no model calls, no prompt injection, and no canonical memory mutation
- skips failed agent runs and runs with fewer than `minMessages` eligible messages

For local development without a globally installed `openclaw-mem`, set `command` and `commandArgs`, for example:

```json
{
  "command": "uv",
  "commandArgs": [
    "run", "--project", "/path/to/openclaw-mem",
    "--python", "3.13", "--frozen",
    "python", "-m", "openclaw_mem"
  ]
}
```

Rollback is config-only: set `symbolicCanvas.autoBuild.enabled=false`. Generated receipts are non-canonical artifacts and may be deleted independently.

## Non-goals

- Not a replacement for `ContextPack`.
- Not an automatic after-tool-call offload engine.
- Not a persona writer.
- Not a TencentDB-Agent-Memory plugin installer.

## Absorption boundary

Absorbed from TencentDB-Agent-Memory:

- compact symbolic canvas
- `node_id` drill-down posture
- layered top-summary → index → raw-evidence thinking

Rejected for this product surface:

- install-time OpenClaw runtime patching
- automatic L3/persona writes
- ungoverned memory mutation
- backend replacement
