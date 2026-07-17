---
name: openclaw-mem-graph
description: >-
  Operate graph readiness, topology lookup, synthesis-aware routing, and
  symbolic evidence canvases. Use for project ownership, impact, dependency,
  or idea-to-project questions.
metadata:
  ring: 1
  surface: [cli, plugin]
  version: 2.0.0
  requires: [openclaw-mem-memory]
---

# Graph Governance

## Workflow

1. Check readiness before using graph output as a router.
2. Query or match the narrowest scope.
3. Preserve synthesis coverage and raw-reference receipts.
4. Fail open to docs, recall, or repository inspection when graph evidence is stale or unavailable.

```bash
openclaw-mem graph readiness --json
openclaw-mem graph query subgraph <node-id> --json
openclaw-mem graph match <query> --json
openclaw-mem route auto <query> --json
openclaw-mem routing resolve <query> --workspace-root <workspace> --json
```

Synthesis cards are derived artifacts, not durable memory. Require `preferredCardRefs` and `coveredRawRefs` when one card replaces multiple raw hits. Use `graph synth recommend` before explicit refresh.

Build a symbolic canvas only as a compact evidence map. Duplicate IDs fail closed; missing refs remain warnings; the canvas does not write durable memory.

## Verify

```bash
openclaw-mem graph readiness --json
openclaw-mem route auto <query> --json
python -m pytest tests/test_graph_match_cli.py tests/test_autonomous_default_routing_cli.py -q
```
