# Context pack auto-graph productization, day-1 Sakura Blade Dance plan (2026-04-18)

Status: ACTIVE  
Owner: Lyria + CK  
Mode: Sakura Blade Dance / non-stop / one-day bounded push  
Line: `--use-graph=auto` productization slice

## 1) Verdict

Push the productization line now, but keep it to one bounded day:
- scope discipline first
- latency gate second
- regression lane hookup third only if the first two are green

Recommended day-1 serial blades:
1. Scope Gate MVP
2. Latency Gate + receipt contract
3. Product smoke + regression hookup prep

This is a productization slice, not a research expansion slice.

---

## 2) Whole-picture promise

Make `pack --use-graph=auto` safe enough to feel like a product surface:
- graph auto only fires when the project/scope case is good enough
- graph auto can explain why it ran, why it skipped, and how much latency it cost
- slow or weak graph paths degrade cleanly instead of polluting the prompt path

Success means:
- scope is bounded
- latency is governed
- trace receipts are decision-grade
- fail-open stays intact

Fake progress would be:
- more trigger cleverness without scope discipline
- more receipts without a real gate decision
- benchmark talk without a latency cutoff that changes behavior

---

## 3) Day-1 blade map

## Blade 1, Scope Gate MVP

### Goal
Constrain auto graph to the right project lane before we make it more eager.

### Bounded slice
- define a deterministic `graph_scope_resolver` contract for `pack --use-graph=auto`
- distinguish at least:
  - explicit CLI `--graph-scope`
  - project-path / artifact-hint inferred scope
  - unresolved scope
- add a conservative policy:
  - explicit scope always allowed
  - inferred scope allowed only when confidence is deterministic and local
  - unresolved scope stays fail-open and conservative
- add trace receipts for scope source / confidence / decision

### Contract
Inputs:
- query text
- optional `--graph-scope`
- path/artifact hints already present in query

Outputs:
- `resolved_scope`
- `scope_source` = `explicit | inferred | unresolved`
- `scope_decision` = `allow | degrade | skip`

Invariants:
- no cross-project default expansion
- unresolved scope must not hard-fail baseline pack

### Done when
- one deterministic scope resolution path lands
- unresolved scope behavior is explicit in trace
- tests prove no accidental cross-project promotion in the covered cases

---

## Blade 2, Latency Gate + receipt contract

### Goal
Turn graph auto latency into a policy decision, not just an observation.

### Bounded slice
- measure preflight latency in the auto path
- define a small latency gate with 3 outcomes:
  - `allow`
  - `degrade`
  - `skip`
- record the gate decision in trace
- on degrade/skip, baseline pack remains primary

### Contract
Inputs:
- graph preflight/probe latency
- configurable thresholds

Outputs:
- `latency_ms`
- `latency_gate_decision`
- `latency_threshold_ms`
- `degraded` boolean

Initial recommended thresholds:
- soft threshold: 150 ms
- hard threshold: 300 ms

Initial posture:
- over soft threshold: keep graph receipts but prefer baseline-only bundle in auto mode when value is marginal
- over hard threshold: skip graph bundle composition in auto mode

### Done when
- latency receipts exist
- thresholds actually change behavior
- fail-open and baseline correctness stay intact

---

## Blade 3, Product smoke + regression hookup prep

### Goal
Prove the lane is ready to move from feature behavior into a guarded product lane.

### Bounded slice
- extend golden fixtures for:
  - explicit scope allow
  - unresolved scope degrade/skip
  - low-latency allow
  - high-latency skip/degrade
- add one human-readable smoke command bundle
- defer full CI wiring if day budget gets tight, but leave the verifier path clean

### Done when
- the new gates are covered by deterministic fixtures/tests
- operator can run one clear verifier command bundle

---

## 4) One-day timeline

### Block A, 0.5 to 1.5h
- inspect current graph-auto path
- define scope gate contract in doc first
- identify smallest code seam

### Block B, 1.5 to 3h
- implement Scope Gate MVP
- add tests and trace receipts
- run first verifier pass

### Block C, 1.5 to 2.5h
- implement latency gate and receipts
- add tests for soft/hard threshold behavior
- run second verifier pass

### Block D, 1 to 1.5h
- extend golden fixtures and smoke bundle
- update docs truth
- run full verifier bundle

### Block E, 0.5 to 1h
- Small Decision Meeting synthesis
- WAL / decision closure if durable truth changed
- commit + push

---

## 5) Verifier bundle

Primary verifier command:

```bash
uv run --python 3.13 --frozen -- python -m unittest \
  tests.test_context_pack_golden \
  tests.test_cli \
  tests.test_json_contracts \
  tests.test_agent_memory_skill_fixture
```

Expected receipts:
- scope resolution receipts in `trace.extensions.graph`
- latency gate receipts in `trace.extensions.graph`
- golden fixtures covering allow / degrade / skip cases

---

## 6) Stop-loss

Stop and report if any is true:
- scope resolution starts requiring broad topology redesign
- latency gate cannot be implemented without deep pack pipeline reshaping
- more than 2 test iterations are spent on wrapper mechanics rather than policy behavior
- adding the gates would require changing public stable contract fields rather than additive receipts

---

## 7) Recommendation from marshal stance

For day 1, do not chase smarter trigger recall.
Do not widen graph associations.
Do not optimize ranking.

Just make auto graph safe enough to ship with pride:
- the right scope
- the right latency posture
- the right receipts

---

## 8) Backlog writeback

### Immediate backlog
- [ ] Scope Gate MVP, explicit scope vs unresolved only
- [ ] Latency Gate + threshold receipts
- [ ] Golden fixture expansion for productization cases
- [x] Small Decision Meeting synthesis
- [ ] WAL / push closure

### Deferred backlog
- [ ] richer inferred-scope heuristics
- [ ] project-scope fallback to topology knowledge
- [ ] formal regression-lane hookup in CI / release path
- [ ] latency histogram / benchmark corpus beyond day-1 thresholds

---

## 9) Small Decision Meeting synthesis

### Cross-validation result
Both advisory lanes converged on the same day-1 posture:
- sequence is correct: scope gate first, latency gate second, regression hookup third
- the biggest day-1 risk is scope inference turning into a heuristic rabbit hole
- if time is tight, cut inferred-scope heuristics first
- a sharper day-1 cut is: explicit scope vs unresolved only, then latency gate, then smoke/regression prep

### Validated recommendation
For day 1, trim Blade 1 aggressively:
- do **not** chase rich inferred-scope heuristics yet
- treat `--graph-scope` as the high-confidence path
- keep everything else conservative / unresolved / fail-open unless an obvious deterministic local artifact rule exists

### Product stance after validation
This confirms the line is productization work, not research work:
- shipping a trustworthy explicit-scope + latency-governed auto lane beats shipping a more magical but flaky inferred-scope lane
