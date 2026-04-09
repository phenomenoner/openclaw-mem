# Route-auto synthesis ops skill (card)

Purpose: operate and verify the **synthesis-aware route-auto lane** so `openclaw-mem` can prefer a fresh synthesis card over replaying multiple covered raw refs while staying fail-open and provenance-first.

## When to use
Use this lane when the question is closer to:
- "is `route auto` actually surfacing synthesis coverage receipts?"
- "is the mem-engine hook carrying the same synthesis-aware hint into live turns?"
- "did this rollout keep the raw refs reachable instead of hiding them behind a magic summary?"

Do **not** use it to turn synthesis cards into durable memory truth.

## Default operator flow
1. Check graph readiness first:
   - `openclaw-mem graph readiness --scope <scope> --json`
2. Inspect the router directly:
   - `openclaw-mem route auto "<query>" --scope <scope> --json`
3. Verify the synthesis receipt:
   - `selection.graph_consumption.preferredCardRefs`
   - `selection.graph_consumption.coveredRawRefs`
   - candidate-level `graph_consumption.cards[]`
4. If the mem-engine hook is enabled, verify the injected hint stays compact and recommendation-only.

## Deterministic smoke
```bash
python tools/route_auto_synthesis_smoke.py
```

Expected result:
- selected lane = `graph_match`
- preferred card refs present
- covered raw refs present
- no mutation of durable memory truth

## Lane boundaries (mandatory)
- route-auto remains a **routing/recommendation** surface, not a write path
- synthesis cards are **derived graph artifacts**, not L1 durable-memory facts by default
- raw refs must remain reachable through receipts / citations / covered-ref metadata
- if graph/synthesis enrichment breaks, the lane must **fail open** to the pre-existing route-auto posture

## Practical commands
```bash
openclaw-mem graph readiness --scope openclaw-mem --json
openclaw-mem route auto "route auto synthesis propagation" --scope openclaw-mem --json
node --test extensions/openclaw-mem-engine/routeAuto.test.mjs
python -m unittest tests/test_autonomous_default_routing_cli.py
python tools/route_auto_synthesis_smoke.py
```

## Escalation rule
If `route auto` stops returning synthesis coverage receipts, or the mem-engine hint no longer mirrors them, treat that as a **product-surface regression**: fix CLI + hook + docs together before claiming the slice shipped.
