# Context Budget Sidecar — tool output offload + soft compaction continuity (2026-03-04)

This thought-link ties the OpenClaw community pain point (“burning through tokens”) to a concrete, product-fit direction for `openclaw-mem`:

> Treat context as a **budgeted, observable artifact pipeline**.
> Store large, lossy-irrelevant payloads *off-prompt* and retrieve them on demand via handles.

## Trigger (field signal)
- OpenClaw Discussion #1949 “Burning through tokens”:
  - <https://github.com/openclaw/openclaw/discussions/1949>

Core complaint pattern:
- Base prompt is heavy.
- Tool outputs (snapshots/logs/html/pdf) + long session history are repeatedly injected.
- People delete session JSONL files as a workaround (it gets cheaper because it forgets), but that’s not a real solution.

## Upstream alignment (what the core project is converging toward)
OpenClaw repo signals that *hooks are wanted*, even if not fully shipped yet:
- Tool output compression middleware: #30998
- Soft compaction / manual compact: #28233
- Heartbeat workspace-file injection controls: #20649
- Make MEMORY.md injection policy controllable: #26949
- Context plugin system extension (potential hook surface): PR #22201

## openclaw-mem positioning (why this fits)
`openclaw-mem` is not trying to become the orchestrator.
It can be the **governance + storage side-car** for:
- artifact offload (raw tool outputs)
- handle-based retrieval (budgeted expansion)
- compaction continuity (checkpoint packs)

This is production-fit because it improves:
- **token predictability** (budgets)
- **auditability** (handles + hashes + receipts)
- **governance** (retention/redaction)

## Concrete spec pointer
- Spec: `docs/specs/context-budget-sidecar-v0.md` (handle format: `ocm_artifact:v1:sha256:<hex>`)

## Trace pack receipt (where we’ll keep runnable artifacts)
- Repo: `openclaw-async-coding-playbook`
- Path (planned):
  - `projects/openclaw-mem/artifacts/thought-links/2026-03-04_context-budget-sidecar/`

## What we will NOT claim (scope discipline)
- Not claiming a magical 90% cost reduction for every workload.
- Not claiming upstream OpenClaw core changes are done.
- We only claim what we can measure with receipts:
  - input token reduction on “heavy tool output” workflows
  - continuity preserved across compaction via checkpoint handles
