# Spec — Context pack policy v1.1 (graph-aware preference + protected tail)

## Status
- Version: v1.1
- Scope: `openclaw-mem pack`
- Posture: deterministic, fail-open, provenance-first

## Goal
Turn context packing from implicit heuristics into an explicit, testable contract for:
- warm durable candidate ordering
- protected recent-tail reservation
- graph-aware synthesis preference
- trace receipts that explain why a candidate made it in or got cut

## Non-goals
- learned ranking or dynamic weighting
- automatic tail summarization/compression
- cross-project graph expansion by default
- changing the stable `context_pack` top-level schema

## Inputs
- query
- retrieved warm candidates (`_hybrid_retrieve` result)
- optional synthesis preference map (`_hybrid_prefer_synthesis_cards`)
- optional recent-tail inputs (`--tail-text`, `--tail-file`)
- budgets:
  - `--limit`
  - `--budget-tokens`
  - `--tail-budget-tokens`
  - `--tail-max-items`
- optional graph auto/on lane (`--use-graph=off|auto|on`)

## Outputs
- `bundle_text`
- `items[]`
- `context_pack`
- optional `trace` with policy and graph receipts
- optional `tail` summary block when tail input was provided

## Core policy rules

### 1) Graph-aware synthesis preference is additive
Before final warm selection, `pack` may prefer a covering synthesis card over raw covered refs when a deterministic coverage relation already exists.

Rules:
- prefer fresh synthesis cards only when the coverage relation is already known
- do not require `--use-graph=on` for this smaller preference step
- fail-open: if synthesis preference cannot be computed, ordinary warm selection continues

### 2) Warm candidate ranking order
Warm candidates are ranked by this precedence:
1. graph synthesis preferred first
2. trust tier (`trusted` > `unknown` > `untrusted` > `quarantined`)
3. importance (`must_remember` > `nice_to_have` > `unknown` > `ignore`)
4. retrieval strength (RRF)
5. retrieval breadth (`matched_count`)
6. recency (`ts` newer first)
7. original stable order

### 3) Protected tail is reserved, not best-effort only
When tail input is present and `--tail-budget-tokens > 0`:
- reserve tail token budget before warm admission
- reserve tail item slots before warm admission
- only the last `tail-max-items` tail lines are considered
- tail items land as `L0` / `recent_turn`

When tail input is present but tail budget is zero:
- tail stays disabled
- trace should make that visible (`tail_budget_disabled`)

### 4) Trace posture
`pack --trace` must expose enough policy receipts to explain:
- warm-vs-tail reservation
- graph preferred card refs / covered raw refs
- whether graph auto trigger fired and why
- per-candidate include/exclude reasons

Primary policy receipt lane:
- `trace.extensions.policy`

## Graph auto trigger policy interaction
`--use-graph=auto` follows the graph preflight trigger policy, with one explicit v1.1 rule:
- short-but-explicit operator artifact refs (for example `docs/specs/`, `DECISIONS`) may bypass the generic `too_short` anti-trigger
- ack-like short messages still stay rejected

Additional product guardrails:
- scope gate
  - explicit `--graph-scope` = `scope_source: explicit`, `scope_decision: allow`
  - deterministic local project token match = `scope_source: inferred`, `scope_decision: allow`
  - unresolved scope in auto mode = `scope_source: unresolved`, `scope_decision: skip`
- latency gate
  - `--graph-latency-soft-ms` and `--graph-latency-hard-ms` govern whether the graph bundle is composed into `bundle_text_with_graph`
  - `allow | degrade | skip` is exposed in `trace.extensions.graph.latency`

This preserves the low-noise posture while allowing real operator lookup shorthand.

## Error / fail-open rules
- graph failure must not break baseline pack
- tail file `-` on a TTY must fail fast with an explicit error instead of hanging
- missing or malformed tail lines are ignored, not promoted
- if budgets are exhausted, exclusion is explicit in trace reasons

## Stable invariants
- `context_pack.schema` stays `openclaw-mem.context-pack.v1`
- included items keep provenance (`recordRef`)
- ordinary `pack` still works when tail and graph features are unused
- docs and receipts must stay truthful to the actual codepath

## Verifier plan
Minimum regression gate:
1. graph synthesis preferred over covered raw ref
2. protected tail reserves both token budget and item slot
3. `--tail-file -` on TTY fails fast
4. auto graph skips when scope stays unresolved
5. short artifact/path refs can still trigger `--use-graph=auto` when scope is explicit or deterministically inferred
6. probe receipts expose thresholds and marginal-count reasoning
7. latency gate exposes allow/degrade/skip decisions and suppresses graph composition when degraded/skipped

Fixture lane:
- `docs/fixtures/context-pack-golden-scenarios.v0.yaml`
- `tests/data/CONTEXT_PACK_GOLDEN_SCENARIOS.v0.jsonl`
- `tests/test_context_pack_golden.py`

## Rollback
Rollback is one commit revert of the v1.1 pack-policy slice. No topology or backend ownership change is required.
