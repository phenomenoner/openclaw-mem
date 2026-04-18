# self-model side-car endgame adjudication freeze packet v0

Status: draft
Date: 2026-04-18
Parent:
- `docs/specs/self-model-sidecar-endgame-architecture-v0.md`
Topology: unchanged

## Verdict
If the endgame line is going to move honestly, the next bounded slice is **adjudication contract freeze**, not claim graph work.

This packet exists to keep `櫻花刀舞 non-stop` disciplined:
- non-stop is allowed only after the adjudication contract is concrete enough to prevent governance theater
- anything downstream that depends on adjudication stays blocked until this packet is frozen

## Why this is the next gate
Everything ambitious in the endgame depends on adjudication semantics:
- claim graph lifecycle
- migration compare severity
- public-safe export rules
- anti-delusion instrumentation thresholds
- retirement and revalidation behavior

If adjudication is vague, the rest becomes elegant scaffolding around ungrounded judgment.

## Required freeze outputs
1. **State model**
   - `accepted`
   - `tentative`
   - `fragile`
   - `contested`
   - `retired`
   - `rejected`

2. **Input bundle definition**
   - source evidence refs
   - contradiction pressure
   - support score components
   - prior contribution
   - release state
   - operator receipts
   - determinism boundary

3. **Transition rule table**
   - what can move a claim into each state
   - what blocks a claim from rising in state
   - what events force downgrade or retirement

4. **Publication/export rules**
   - which states may appear on operator surface
   - which states may appear on public-safe surface
   - required hedges and banned renderings

5. **Negative fixtures**
   - prior-dominant but evidence-thin claim
   - low-evidence high-coherence claim
   - retired claim with weak new support
   - contested claim under explicit contradiction pressure

## Freeze blockers
The packet is not ready if any remain true:
- contradiction pressure is still only a phrase
- support score still lacks exact inputs
- determinism boundary is not explicit
- rule-only vs hybrid-rule-plus-model is undecided
- fragile vs contested semantics still overlap ambiguously

## Non-stop execution rule for this line
`櫻花刀舞 non-stop` may continue automatically **within adjudication freeze only** when:
- each next step stays inside docs/spec/tests for adjudication semantics
- no new topology or persistence surface is introduced
- no claim graph persistence is started
- no public-facing product language is expanded beyond the current guardrails

Stop-loss back to CK if:
- rule-only adjudication looks non-viable
- claim families need to be cut materially
- hybrid model judgment becomes unavoidable for core adjudication
- graph demand no longer looks justified

## Recommended immediate sub-blades
### A1. Definitions freeze
- contradiction pressure
- support score
- confidence band
- fragility marker
- prior contribution
- determinism boundary

### A2. Rule table freeze
- state entry rules
- downgrade rules
- retirement rules
- revalidation rules

### A3. Publication contract freeze
- operator-safe output rules
- public-safe output rules
- banned language and required hedges

### A4. Adversarial fixture pack
- 3 to 5 negative fixtures with expected adjudication outcomes

## Success criteria
This packet is frozen only when:
1. a reviewer can adjudicate sample claims by table, not intuition
2. negative fixtures produce stable expected states
3. export rules make overclaim mechanically harder
4. downstream work can consume adjudication results without inventing semantics
