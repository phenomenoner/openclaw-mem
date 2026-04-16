# Spec — self-optimizing memory autonomy ramp v0

## Status
- Stage: planning only
- Scope: next bounded step after the governed assist-apply canary
- Goal: move from "safe canary" toward "usefully autonomous" without collapsing the scout / governor / writer split
- Execution mode: roadmap reference for `櫻花刀舞` non-stop push toward bounded full autonomy

## Verdict
The next milestone is **not** a broad release.
It is a bounded autonomy ramp that expands low-risk self-apply classes, adds effect measurement, and keeps a hard stop on high-risk mutation.

## Whole-picture promise
The memory layer should feel like it is **actually improving itself** under risk control.
That means:
- low-risk maintenance changes can land with little or no human friction
- medium-risk changes still produce a clean approval packet
- high-risk changes remain proposal-only
- every mutation stays auditable, reversible, and measurable against retrieval quality

Fake progress would be:
- adding more receipts without more autonomy
- adding more autonomy without measurable quality gates
- calling a conservative canary a release when it still feels mostly manual

## Roadmap

### Phase 1 - effect receipt foundation
Goal: turn mutation into a measurable loop.

Ship:
- effect receipt artifact for every assist run
- bounded `optimization.assist.effect` metadata on applied rows
- baseline capture for later 24h follow-up measurement

Exit criteria:
- every apply run emits effect artifacts
- missing effect receipt rate is zero
- fixture tests prove artifact generation and receipt persistence

### Phase 2 - evidence-weighted risk classifier
Goal: classify candidates as `low | medium | high` using evidence, not just whitelists.

Ship:
- explicit classifier contract
- packetized `risk_level`, `risk_reasons`, `auto_apply_eligible`
- tests for edge cases and conflicting evidence families

Exit criteria:
- sampled manual review precision meets threshold
- low-risk eligibility is deterministic and auditable

Implementation note:
- classifier foundation is now shipped in the governed optimize-assist lane
- evolution packets carry `risk_level`, `risk_reasons`, and `auto_apply_eligible`
- governor approval flags still fail closed when classifier output is not `low` + eligible
- broader unattended apply remains a later phase

### Phase 3 - unattended low-risk apply
Goal: let narrow low-risk classes self-apply without a human in the loop.

Ship:
- unattended apply for stale mark, bounded importance delta, and score-label alignment
- per-run / per-day family caps
- fail-closed cap enforcement

Exit criteria:
- rollback replay stays green
- canary receipts show bounded unattended writes without cap drift

Implementation note:
- family-cap foundation is now shipped for bounded importance adjustments
- assist apply enforces per-run and rolling-24h caps for `adjust_importance_score`
- broader unattended default-on posture still waits for controller/watchdog phases

### Phase 4 - autonomy controller + watchdog
Goal: promote the command chain into a controller that can pause itself.

Ship:
- controller state machine (`dry_run`, `canary_apply`, `auto_low_risk`, `paused_regression`)
- regression watchdogs
- automatic pause on missing effect receipts / quality regression / rollback replay failure

Exit criteria:
- watchdog tests pass
- pause/resume behavior is explicit and receipted

### Phase 5 - bounded fully autonomous posture
Goal: default unattended low-risk operation with explicit promotion gates.

Ship:
- promotion checklist and thresholds
- default unattended low-risk lane
- medium-risk governor packet path retained, high-risk proposal-only retained

Exit criteria:
- promotion gates stay green for multiple cycles
- the system is unattended by default only within the bounded low-risk envelope

## Recommended bounded slice
Ship **Phase 1: effect receipt foundation** first, then continue serially toward Phase 5.

This slice should add exactly three things:

1. **Effect receipt artifact**
   - emit a compact effect artifact on every assist run
   - capture baseline signals needed for later follow-up measurement

2. **Row-level effect metadata**
   - write bounded `optimization.assist.effect` metadata on applied rows
   - keep the metadata minimal and rollbackable

3. **Follow-up measurement hook**
   - define the contract for later 24h quality comparison
   - do not broaden mutation authority in this phase

This slice is small enough to land quickly, but real enough to prevent later unattended apply from becoming blind mutation.

## Contract / boundary rules

### Inputs
- `observations`
- `pack_lifecycle_shadow_log`
- existing optimize review / policy-loop signals
- explicit runner / cron invocation context

### Outputs
- proposal packet with explicit `risk_level`
- optional approved packet for unattended low-risk apply
- before / after / rollback receipts
- new effect receipt summarizing whether the change helped, held steady, or regressed

### State changes allowed in this phase
Only `observations.detail_json` fields already inside the assist whitelist, plus the minimal whitelist expansion below.

### Proposed whitelist expansion
Keep all current fields, and add the following bounded writes:
- `/importance/score`
  - absolute delta <= 0.10 for unattended low-risk mode
- `/importance/label`
  - must remain consistent with score bucket
- `/optimization/assist/effect`
  - bounded metadata only:
    - `measured_at`
    - `effect_window`
    - `effect_summary`
    - `quality_delta`

### Explicitly out of scope
- row deletion
- summary rewrite
- scope rewrite
- cross-row merge/split
- config mutation
- prompt/routing mutation
- any unattended high-risk action

## Candidate low-risk auto-apply classes

### Class A — stale lifecycle mark
Already shipped.
Keep it as the baseline unattended class.

### Class B — bounded importance downshift
Use when all are true:
- repeated miss / low-value resurfacing pressure is present
- no recent-use protection
- current importance score is parseable
- proposed absolute delta <= 0.10

### Class C — bounded importance upshift
Use when all are true:
- repeated successful reuse signal is present
- target row has stable scope / evidence refs
- current importance score is parseable
- proposed absolute delta <= 0.10

### Class D — score-label alignment
Use only as a follow-on to B/C when the label would otherwise be inconsistent with the new score bucket.

## Risk ladder for the next phase

### Low risk
Can auto-apply when all gates are green.
Examples:
- stale mark
- small importance score adjustment
- label alignment

### Medium risk
Must go through explicit governor approval.
Examples:
- larger score delta
- many-row fanout inside one scope
- conflicting evidence families

### High risk
Proposal only.
Examples:
- merge/split
- cross-scope changes
- delete/archive mutation
- anything that changes retrieval semantics broadly

## Guardrails required before unattended low-risk mode

### Per-run / per-day caps
- `max_rows_per_apply_run`: keep 5
- `max_rows_per_24h`: start at 20
- `max_importance_adjustments_per_run`: 3
- `max_importance_adjustments_per_24h`: 10
- `max_field_families_per_row`: keep 1

### Quality gates
Require all before unattended low-risk mode is enabled by default:
- no increase in repeated-miss groups beyond a small tolerance window
- no drop in eligible-writeback / retrieval-quality proxy metrics beyond tolerance
- approval precision from sampled manual review remains above threshold
- rollback replay remains green on fixture DB

### Suggested initial thresholds
- `manual_review_sample_precision >= 0.9`
- `repeated_miss_regression_pct <= 5%`
- `effect_receipt_missing_pct = 0`
- `rollback_replay_pass = true`

## Effect measurement contract
Every unattended low-risk apply should emit a compact effect receipt:

```json
{
  "kind": "openclaw-mem.optimize.assist.effect.v0",
  "run_id": "...",
  "proposal_id": "...",
  "measured_at": "...",
  "effect_window": "24h",
  "effect_summary": "improved|neutral|regressed|insufficient_data",
  "quality_delta": {
    "repeated_miss_groups": -1,
    "low_value_resurface_count": -2
  }
}
```

This is not proof of truth, but it is the minimum contract that turns mutation into a measurable loop rather than a blind write.

## Verifier plan

### Tests
- parser coverage for new low-risk classes / flags
- classifier tests for low / medium / high routing
- apply tests for bounded importance updates
- rollback replay tests for importance changes
- effect-receipt generation tests
- canary cap-enforcement tests

### Smoke commands
- dry-run runner smoke on `:memory:`
- fixture DB run with sample low-risk importance changes
- rollback replay smoke
- effect receipt smoke with synthetic before/after signal windows

### Human review receipts
- sample packet diff review
- sample rollback artifact inspection
- sample effect receipt inspection

## Delegation packet
If delegated to a coding/review lane, ask for:
- first artifact: command map + contract delta
- exact verifier list before patching
- no docs-site copy polish before the contract/test edge exists
- stop if the worker starts broadening mutation beyond the explicit whitelist

## Rollback / WAL closure
When this phase is implemented, close with:
- spec delta
- code/tests
- docs for enablement posture
- changelog note
- topology statement
- push receipt

## Tradeoffs / open risks
- More autonomy raises the chance of subtle retrieval drift.
- Importance score adjustment is more powerful than lifecycle marking, so effect measurement is mandatory.
- The sweet spot is not "no human in the loop". It is "human attention spent only on medium/high-risk mutations".
