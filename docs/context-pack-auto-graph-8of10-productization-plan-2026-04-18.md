# Context pack auto-graph, path to 8/10 product maturity (2026-04-18)

Status: PROPOSED  
Owner: Lyria + CK  
Mode: Sakura Blade Dance / non-stop / verifier-backed  
Target line: `pack --use-graph=auto`

## Verdict

Do not widen feature scope first.
Push one bounded productization line that turns `--use-graph=auto` from a clever feature into a dependable default candidate.

Recommended serial blades:
1. Scope Gate v1
2. Latency Gate v1
3. Product-smoke + regression lane
4. Soak receipts + default-readiness review

This is the shortest honest path from roughly 6/10 to 8/10.

---

## Whole-picture promise

Make `pack --use-graph=auto` safe, explainable, and boring enough that we can seriously consider it for routine operator use.

What 8/10 means here:
- graph auto fires only in the right lane
- slow or weak graph paths degrade cleanly
- trace receipts explain the decision without archaeology
- regression coverage protects the contract
- short soak evidence says it behaves in real usage, not only fixtures

Fake progress:
- richer trigger cleverness without scope discipline
- more heuristics without latency posture
- docs optimism without soak receipts
- broad graph expansion before default-readiness is proven

---

## Maturity target

Current estimate:
- feature maturity: 7/10
- product maturity: 6/10
- safe-default readiness: 5.5/10

Promotion target for this line:
- product maturity: 8/10
- safe-default readiness: 7.5 to 8/10 after soak review

Promotion gate:
- all four blades green
- no contract drift in baseline pack when graph stays off
- no unresolved-scope false promotion in covered cases
- no latency gate regressions in verifier bundle
- soak receipts show stable allow/degrade/skip behavior across representative queries

---

## Blade map

## Blade 1. Scope Gate v1

### Goal
Constrain auto-graph to the correct project lane before it becomes more eager.

### Recommended bounded slice
Implement a deterministic scope resolver for `pack --use-graph=auto` with only three sources:
- explicit CLI scope
- deterministic local inference from artifact/project hints
- unresolved

### Contract
Inputs:
- query text
- `--graph-scope` if provided
- artifact/path hints already present in the query

Outputs:
- `resolved_scope`
- `scope_source = explicit | inferred | unresolved`
- `scope_decision = allow | degrade | skip`
- receipt fields in `trace.extensions.graph`

Rules:
- explicit scope always wins
- inferred scope is allowed only when derived from deterministic local hints
- unresolved scope never hard-fails baseline pack
- unresolved scope cannot silently promote to cross-project graph expansion

Non-goals:
- semantic scope inference
- cross-repo fuzzy matching
- topology redesign

### Done when
- deterministic resolver lands
- unresolved behavior is explicit and tested
- graph auto cannot accidentally promote unrelated project scope in covered cases

---

## Blade 2. Latency Gate v1

### Goal
Turn graph auto latency from an observation into a policy decision.

### Recommended bounded slice
Add a small gate with three outcomes:
- `allow`
- `degrade`
- `skip`

### Contract
Inputs:
- graph preflight/probe latency
- configured thresholds
- optional signal quality from stage0/stage1/probe

Outputs:
- `latency_ms`
- `latency_gate_decision = allow | degrade | skip`
- `latency_threshold_soft_ms`
- `latency_threshold_hard_ms`
- `degraded` boolean

Recommended starting thresholds:
- soft: 150 ms
- hard: 300 ms

Behavior:
- under soft: allow normal graph-aware bundle behavior
- over soft but under hard: degrade to baseline-primary behavior, keep receipts
- over hard: skip graph bundle composition in auto mode, preserve fail-open baseline

Invariants:
- latency gates are additive, not baseline-breaking
- graph latency cannot make plain pack worse than graph-off behavior
- receipts must show not just latency, but the decision it caused

### Done when
- thresholds actually change runtime behavior
- tests cover allow/degrade/skip
- no contract break in existing graph-off or graph-on explicit modes

---

## Blade 3. Product smoke + regression lane

### Goal
Make the feature defendable as a product surface, not just a code path.

### Recommended bounded slice
Extend deterministic regression coverage and add one operator-facing smoke bundle.

### Required coverage
Golden/fixture scenarios should cover at least:
- explicit scope allow
- deterministic inferred scope allow
- unresolved scope degrade
- unresolved scope skip when signal is too weak
- low-latency allow
- soft-threshold degrade
- hard-threshold skip
- short explicit artifact ref still allowed when truthful
- graph failure fail-open to baseline pack

### Operator smoke bundle
Provide one human-readable verifier sequence for:
- graph auto with explicit scope
- graph auto with unresolved scope
- graph auto with artificial slow-path or mocked threshold pressure
- receipt inspection for decision fields

### Done when
- regression suite expresses the intended product contract
- an operator can run one clear smoke bundle and inspect receipts without source diving

---

## Blade 4. Soak receipts + default-readiness review

### Goal
Earn the jump from feature confidence to product confidence.

### Recommended bounded slice
Run a short bounded soak over representative query classes and review the receipts as a product gate.

### Soak set
Use a small fixed matrix, for example 12 to 20 queries across:
- explicit project/scope asks
- artifact-hint asks
- ambiguous/unresolved asks
- dependency/status asks
- recent-summary asks
- known graph-poor asks

### Required receipts
Collect at least:
- allow/degrade/skip counts
- average and p95 latency for auto path
- number of fail-open baseline recoveries
- any false-positive scope promotions
- any cases where graph made the answer bundle worse

### Decision rule
Promote from 6/10 to 8/10 only if:
- no baseline-breaking regressions
- no cross-project false promotions in the soak set
- latency gate behaves as designed
- receipt clarity is good enough for operator diagnosis

### Done when
- soak note exists as a durable receipt
- final recommendation says either “ready for guarded default candidate” or “hold at 7/10 with named blocker”

---

## Implementation order

### Pass A
- land scope resolver contract and trace fields
- add deterministic tests
- update docs truth

### Pass B
- land latency gate and decision receipts
- add allow/degrade/skip tests
- update docs truth

### Pass C
- extend golden fixtures and operator smoke bundle
- verify regression contract

### Pass D
- run bounded soak
- write go/no-go review note
- if durable truth changes, write WAL and push

---

## Boundary rules

### Inputs we are allowed to use
- existing query text
- explicit graph scope
- deterministic artifact/path hints already surfaced in query
- existing graph preflight/probe signals
- existing pack baseline outputs and trace surfaces

### Inputs we are not allowed to invent
- opaque semantic scope classifier
- hidden cross-project defaults
- heuristic expansion that cannot be explained in receipts

### Output surfaces that must stay stable
- baseline `pack` behavior when graph is off
- fail-open posture when graph path fails or is skipped
- additive trace fields only, unless explicitly versioned

### Error posture
- graph-side failures must never break baseline pack
- TTY / input hazards continue to fail fast where appropriate
- if a gate cannot decide, default to conservative degrade/skip rather than aggressive promotion

---

## Verifier plan

Primary verifier bundle:

```bash
uv run --python 3.13 --frozen -- python -m unittest \
  tests.test_context_pack_golden \
  tests.test_cli \
  tests.test_json_contracts \
  tests.test_agent_memory_skill_fixture
```

Additional expected checks:
- targeted tests for scope allow/degrade/skip
- targeted tests for latency allow/degrade/skip
- smoke commands that inspect `trace.extensions.graph`
- before/after receipt comparison proving graph-off behavior unchanged

Required receipt fields after productization:
- `resolved_scope`
- `scope_source`
- `scope_decision`
- `latency_ms`
- `latency_gate_decision`
- threshold fields used for the decision
- trigger reason when graph auto fires
- fail-open note when graph path is skipped or degraded

---

## Delegation packet

If delegated to a coding worker:

- Objective
  - Productize `pack --use-graph=auto` from 6/10 to an 8/10 candidate without widening scope.

- Scope boundary
  - Only blades 1 to 3 for implementation.
  - Blade 4 may collect bounded soak receipts but must not silently change defaults.

- First artifact expected
  - Contract patch or doc sketch for scope + latency receipts before broad edits.

- Exact verifier
  - `uv run --python 3.13 --frozen -- python -m unittest tests.test_context_pack_golden tests.test_cli tests.test_json_contracts tests.test_agent_memory_skill_fixture`

- Stop-loss
  - Stop if scope resolution requires a topology redesign.
  - Stop if latency gate requires deep pack-pipeline surgery.
  - Stop after two meaningful attempts on the same root-cause.

- Do not touch
  - unrelated retrieval/ranking behavior
  - broad graph schema redesign
  - default config flips without an explicit review gate

- Return if blocked
  - anomaly list
  - minimal repro
  - contract delta proposal
  - exact failing verifier

---

## Rollback / WAL closure

Rollback posture:
- each blade should be revertable independently
- additive receipts are preferred over destructive contract rewrites
- no default flip in the same pass as first implementation unless soak already proves it

WAL closure required when durable truth changes:
- decision note for scope/latency gate contract
- verification receipt summary
- topology statement: unchanged unless proven otherwise
- push receipts for code repo and ledger repo

---

## Tradeoffs / open risks

### Tradeoff 1: conservative scope gate vs recall
Conservative scope resolution may skip some useful graph calls.
That is acceptable for this phase. Wrong promotion is more dangerous than a missed assist.

### Tradeoff 2: latency gate vs occasional graph value
A hard skip will sometimes leave value on the table.
That is still the right trade for a product surface.

### Tradeoff 3: soak cost vs confidence
A short soak adds time, but without it we are grading a feature, not a product.

### Named risks
- ambiguous artifact hints may still look deterministic when they are not
- latency thresholds may need project-specific tuning after the first soak
- receipt verbosity could get messy if we do not keep the fields tight

---

## Recommendation from marshal stance

If we want an honest shot at 8/10, do not go shopping for new graph tricks.

Just close the product gap:
- right scope
- right latency posture
- right regression lane
- one bounded soak with receipts

That is the shortest path that actually changes my score.
