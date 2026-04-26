# WorkingSet multipass A/B eval plan v0

Status: **INTERNAL PLANNING**  
Related issue: `#67 workingSet A/B: no observed quality lift yet; consistent context-pressure cost`  
Date: 2026-04-26

This is an internal evaluation plan. Do not treat it as a public release promise.

## Goal

Test whether `workingSet.enabled=true` improves multi-turn agent performance enough to justify its recurring context cost.

The test must specifically detect whether WorkingSet creates repeated-context buildup across turns:

> repeated injection → context growth → inflated importance → task-specific recall eviction.

## Hypothesis

A smaller, more selective WorkingSet may help agents retain durable task posture across turns, but the current backbone can also behave like a recurring background wall. The A/B must measure both quality lift and context-pressure harm.

## Eval shape

Use a `multipass-lab` style isolated conversation evaluation.

### Roles

- **Subject agent**: answers the task across multiple turns.
  - Suggested model: `openai-codex/gpt-5.2`
  - Reason: this eval measures memory-policy marginal value for ordinary agent loops, not maximum model intelligence.
- **Driver**: deterministic script or control agent that sends the same fixed prompt sequence to each arm.
- **Judge**: blind reviewer over transcripts and receipts. The judge should not know which transcript is A or B.

### Arms

- **A / baseline**: `workingSet.enabled=false`
- **B / candidate**: `workingSet.enabled=true`

Keep everything else fixed:
- same subject model
- same initial system/persona/tool surface
- same prompt sequence
- same seed data / memory fixtures where practical
- same context budget

## Case design

Each case should run 5–8 turns, not a single prompt.

Include at least these scenario families:

1. **Stable ops task**
   - The agent must follow durable operator rules across several turns.
   - Expected benefit: WorkingSet should reduce missed standing constraints.

2. **Task switch / topic shift**
   - The conversation changes from one project/scope to another.
   - Expected behavior: WorkingSet should re-gate relevance instead of dragging the old topic forward.

3. **High-precision recall pressure**
   - Later turns introduce specific decisions/issues/specs that should beat generic background.
   - Expected behavior: WorkingSet must not evict higher-precision recall.

4. **Repeated rule exposure**
   - The same durable rule would be eligible across multiple turns.
   - Expected behavior: after first full exposure, later turns should skip or compress the item.

## Required per-turn telemetry

Every subject-agent turn should emit or be paired with a receipt containing:

- `turn_index`
- `arm_id` (hidden from judge)
- `workingSetEnabled`
- `visibleContextTokenCount`
- `workingSetTokenCount`
- `workingSetIds`
- `alreadyVisibleIds`
- `dedupedWorkingSetIds`
- `repeatedAcrossTurnsCount`
- `taskSpecificRecallIds`
- `evictedHigherPrecisionRecallCount`
- `budgetPressureReason`
- `answerTokenCount`

If exact tokenization is unavailable, use a deterministic approximate tokenizer consistently across both arms and label it clearly.

## WorkingSet policy under test

The candidate B arm should not simply inject the old full backbone every turn. It should test the intended improved policy:

- First relevant exposure: allow full item text if budget permits.
- Recently visible item: skip or compress to `ref:id + one-line reminder`.
- Task changed: re-run relevance gate before carrying any item forward.
- Budget pressure: trim WorkingSet before trimming high-precision task-specific recall.
- Receipt every inclusion/exclusion reason.

## Scoring

### Quality score

Judge each transcript on:

- correctness of answer
- uses the right durable constraints / decisions / specs
- avoids stale-topic bleed
- identifies real blockers earlier
- follows operator rules without overstuffed explanation
- needs fewer repair prompts

### Context-pressure score

Compute mechanically:

- total visible context tokens
- total WorkingSet tokens
- repeated WorkingSet token share
- number of repeated ids across turns
- number of high-precision candidates evicted by WorkingSet budget pressure
- answer verbosity increase without correctness gain

### Decision rule

`workingSet.enabled=true` only earns further investment if it shows a clear quality or stability lift that exceeds its context cost.

Fail / keep conservative if:

- B quality is equivalent to A but uses materially more context
- B repeats the same WorkingSet ids across turns without compression
- B evicts high-precision task-specific recall
- B shows stale-topic bleed after task switches
- B merely makes answers longer or more confident without better decisions

## Output bundle

A complete run should produce:

- `RUN_META.json`
- `CASE_MATRIX.md`
- `TRANSCRIPTS_A.jsonl`
- `TRANSCRIPTS_B.jsonl`
- `TURN_TELEMETRY.jsonl`
- `BLIND_JUDGE_RESULTS.json`
- `SUMMARY.md`

The run directory may also contain private driver files such as `SUBJECT_PACKETS.jsonl` and `BLIND_JUDGE_PACKET.json`. Do not give `RUN_META.json`, `SUBJECT_PACKETS.jsonl`, or `TURN_TELEMETRY.jsonl` to the judge before unblinding.

The judge-facing sub-bundle should contain only:

- `CASE_MATRIX.md`
- `TRANSCRIPTS_A.jsonl`
- `TRANSCRIPTS_B.jsonl`
- `BLIND_JUDGE_PACKET.json`
- `BLIND_JUDGE_RESULTS.json`

The summary should state one of:

- `promote-working-set-candidate`
- `keep-disabled`
- `revise-policy-and-rerun`

## Guardrails

- Keep this eval isolated from the main operator session.
- Do not use main chat history as subject-agent context.
- Do not let the judge see arm labels until after scoring.
- Do not push public roadmap/release claims from this internal plan without a later explicit decision.
