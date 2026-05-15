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
