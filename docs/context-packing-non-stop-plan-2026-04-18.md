# Context Packing non-stop plan (2026-04-18)

Status: ACTIVE  
Owner: Lyria + CK  
Mode: non-stop / serial blades  
Scope: `openclaw-mem` context packing upgrade line

## 1) Verdict

This line upgrades `openclaw-mem` from a baseline packer into a bounded, trust-aware, provenance-first briefing engine with continuity handling and additive graph expansion.

We will run this as one non-stop milestone with four serial blades:

1. Golden Judge Harness
2. Protected Tail MVP
3. Pack Policy v1.1 Freeze
4. Graph-aware Additive Lane

The line should keep pushing by default until closure, a real blocker, stop-loss, or a new authority boundary.

---

## 2) Whole-picture promise

Ship a context system that:
- builds small, useful, auditable briefings instead of prompt soup
- preserves continuity without letting raw recent context take over the whole budget
- makes selection policy explicit and testable
- can expand into graph-aware retrieval without breaking baseline pack

Success means:
- judge exists
- continuity exists
- policy exists
- graph expansion exists
- all of it is traceable, fail-open, and rollbackable

---

## 3) Non-stop contract

### Allowed automatic forward motion
Within this line, the following are pre-approved unless risk changes materially:
- spec tightening within the existing product wedge
- fixtures, traces, tests, and receipts
- feature-flagged additive behavior
- fail-open / kill-switch / budget guardrails
- docs updates that keep durable truth honest

### Must pause and report
Pause only if any of the following happens:
- external login/auth/subscription gate blocks the next required move
- public CLI contract must change
- a new default-on behavior is required before proof exists
- graph work pressures a new hard backend dependency or cross-project default behavior
- latency, budget, or trust posture regresses materially
- the same root-cause hypothesis has already had 2 meaningful attempts

### Closure standard
Each blade closes only when all of the following are true:
- code/spec/tests landed for that blade
- verifier receipts exist
- docs truth updated where needed
- rollback / flag posture is clear
- next-blade gate is either ready or blocked with a truthful reason

---

## 4) Blade map

## Blade 1 - Golden Judge Harness

### Goal
Build the judge before changing the contestant.

### Promise
Create a deterministic replay/assert layer so later pack changes can be measured rather than vibe-checked.

### Bounded slice
- add 5-10 canonical scenarios over time (minimum 1 full scenario to start)
- define frozen inputs and expected include/exclude outcomes
- add a replay/assert harness
- freeze baseline trace expectations
- expose the smallest pack-policy runner interface needed for testing

### Contract / boundaries
Inputs:
- frozen query/scenario inputs
- current candidate sets or pack outputs

Outputs:
- deterministic expected selection behavior
- diffable trace receipts

Must not expand into:
- graph retrieval implementation
- protected tail implementation
- generalized scoring framework redesign

### Verifiers
- replay test passes on frozen scenarios
- same input yields same include/exclude reasons
- missing reason or missing citation fails the test

### Done when
- judge harness is runnable in-repo
- at least 1 end-to-end golden scenario lands
- later blades can reuse the harness directly

### Stop-loss
If building the harness requires broad refactoring of the live pack path, cut down to an external replay fixture runner first.

---

## Blade 2 - Protected Tail MVP

### Goal
Add bounded continuity without turning the system into recent-history soup.

### Promise
Keep a small protected recent tail at assembly time only, with hard budget caps and explicit overflow rules.

### Bounded slice
- define protected-tail contract
- reserve a fixed tail budget
- add hard overflow behavior
- keep it feature-flagged / default off until proven
- add trace fields showing tail allocation

### Contract / boundaries
Inputs:
- recent raw turns
- pack budget
- tail budget cap

Outputs:
- a final pack that includes bounded recent continuity

Rules:
- tail is raw recent continuity, not summarized prose
- no dynamic allocation in v1
- no tail compression lane in this blade

### Verifiers
- continuity scenario tests improve versus baseline
- budget cap tests stay green
- tail enabled/disabled comparisons are honest
- provenance and citations do not regress

### Done when
- protected tail is switchable
- receipts clearly show tail budget usage
- continuity benefit is proven on at least one scenario without budget blowout

### Stop-loss
If tail work couples too deeply to baseline pack internals, move it to an assembly wrapper first.

---

## Blade 3 - Pack Policy v1.1 Freeze

### Goal
Turn selection logic into an explicit contract instead of scattered hidden heuristics.

### Promise
Make trust, importance, recency, and budget handling legible, testable, and traceable.

### Bounded slice
- define `pack_policy` contract surface
- define precedence for trust / importance / recency / budget
- define tail pre-allocation behavior
- define include/exclude reason vocabulary
- update trace schema for policy visibility

### Contract / boundaries
Must define:
- candidate ranking order
- trust gating behavior
- nice-to-have caps
- L2 admission rules
- fail-open behavior
- how tail reduces remaining budget

Must defer:
- learned tuners
- dynamic weighting
- general-purpose optimization framework
- self-adjusting policy loops

### Verifiers
- golden scenarios remain stable or improve intentionally
- fixed-weight policy outputs are deterministic
- trace reasons are machine-checkable
- policy text and implementation agree

### Done when
- policy contract is landed and small enough to stay human-auditable
- selection logic is explainable from trace receipts
- baseline vs tail tension is governed explicitly

### Stop-loss
If the policy file starts growing into a large framework rather than a compact contract, cut the scope back immediately.

---

## Blade 4 - Graph-aware Additive Lane

### Goal
Add graph neighborhood expansion without breaking the baseline pack lane.

### Promise
Make graph retrieval additive, bounded, project-scoped, kill-switchable, and fail-open.

### Bounded slice sequence
1. project-scoped graph index / preflight
2. graph pack
3. optional pack integration
4. defer cross-project edges by default

### Contract / boundaries
Inputs:
- query
- project scope
- graph enabled flag
- graph budget cap

Outputs:
- bounded graph candidates or graph-aware pack additions

Invariants:
- graph failure must not break baseline pack
- graph can be disabled cleanly
- safe mode is default
- no cross-project default expansion

### Verifiers
- graph on/off integration tests
- graph failure fallback test
- redaction-safe trace receipts
- latency gate
- project-scope correctness checks

### Done when
- graph lane produces explainable value
- fail-open behavior is proven
- latency stays inside an agreed gate
- graph receipts explain path / inclusion reasons sufficiently

### Stop-loss
If graph work starts forcing a graph-database or other new hard infrastructure dependency, stop at the portable artifact / in-memory adjacency level.

---

## 5) Serial handoff gates

- Blade 1 -> Blade 2: judge harness exists and is usable
- Blade 2 -> Blade 3: protected-tail tension is visible in receipts/tests
- Blade 3 -> Blade 4: policy contract is frozen and passing golden tests
- Blade 4 -> Closure: graph lane is additive, fail-open, and within latency guardrails

---

## 6) Anti-fake-progress rules

The following do not count as real advancement on this line by themselves:
- fixtures without runnable assertions
- flags without integration tests
- new trace fields without a verifier consuming them
- graph demos without fail-open proof
- policy prose without a matching executable contract
- broad refactors that do not close the blade gate

---

## 7) Verifier bundle (line-level)

Each blade should leave behind the smallest truthful verifier bundle:
- tests or replay checks
- before/after trace receipts
- budget behavior proof where relevant
- fallback / kill-switch proof where relevant
- docs update if durable truth changed

Line-level success checks:
- pack remains bounded
- provenance stays intact
- trust handling is visible
- continuity improves without swamping the bundle
- graph value is additive, not required for baseline correctness

---

## 8) Rollback posture

- new behavior should remain feature-flagged until proven
- baseline pack path stays intact throughout the line
- protected tail can be disabled cleanly
- graph lane remains additive and kill-switchable
- if a blade regresses trust, budget, or baseline correctness, revert that blade rather than dragging the whole line forward dishonestly

---

## 9) Progress ledger

### Current line state
- Status: planned, not yet executing code
- Active blade: Blade 1 prep
- Last updated: 2026-04-18 08:59 Asia/Taipei

### Planned first artifact
- file map
- first golden scenario
- replay/assert harness
- exact verifier commands

### Progress updates
- 2026-04-18 08:59 Asia/Taipei - Initial non-stop execution plan landed. No code changes yet.

---

## 10) Open risks to watch

- Blade 1 scope creep into full pack refactor
- Blade 2 budget starvation from a non-evictable tail
- Blade 3 turning into theory-heavy scoring architecture
- Blade 4 stale graph vs fresh tail conflict
- graph lane silently degrading latency

---

## 11) Next action

Start Blade 1 with the smallest useful artifact:
- identify file map
- land 1 canonical golden scenario
- land replay/assert harness
- define exact verifier commands
