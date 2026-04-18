# self-model side-car endgame architecture v0

Status: draft, not freeze-ready
Date: 2026-04-18
Depends on:
- `docs/specs/self-model-sidecar-msp-v0.md`
- `docs/specs/self-model-sidecar-contract-v0.md`
- `docs/specs/self-model-sidecar-schema-v0.md`
- `docs/specs/self-model-sidecar-rebuildability-v0.md`
Topology intent: additive side-car only, `openclaw-mem` remains memory-of-record
Execution posture: `櫻花刀舞 non-stop` candidate only after constitutional freeze plus adjudication-contract freeze

## Verdict
The endgame is **not** "make the agent more like a person." The endgame is to turn continuity claims into a **governable derived-control plane** that is inspectable, falsifiable, retractable, and rebuildable without ever becoming a second truth owner.

In short:
- `openclaw-mem` keeps truth of record
- the side-car proposes continuity claims
- an adjudication layer decides how strong those claims are allowed to be
- a control plane can weaken, retire, rebuild, or compare them with receipts

If any part of this line starts making ontological claims or acquiring authority over source memory, it has left the design.

## Whole-picture promise
Ship a side-car that can:
1. derive structured continuity claims from source memory and bounded priors
2. adjudicate those claims into governed states rather than raw vibes
3. expose the result through operator-safe and public-safe surfaces
4. support weaken / retire / rebuild / compare operations with receipts
5. remain removable without damaging `openclaw-mem`

## The true endgame posture
The mature product is a **derived-self governance system**.

That means:
- continuity is observable
- attachment is measurable
- drift is classifiable
- contradiction is surfaced
- priors are bounded
- release is receipted
- uncertainty is first-class
- rollback is normal

What it does **not** mean:
- a true self was created
- the side-car knows the user better than memory-of-record
- priors can silently outrank evidence
- a coherent story is accepted just because it feels insightful

## Endgame architecture

### Layer 0. Constitutional boundary layer
Purpose:
- make the restraint mechanical, not cultural

Hard rules:
- `openclaw-mem` memory-of-record remains the only authoritative truth owner
- side-car commands may not mutate Store truth
- all derived artifacts must be rebuildable from allowed sources plus explicit receipts
- persona prior lanes may influence scoring, never authority
- every governance mutation requires a receipt
- every derived claim can be weakened, retired, or marked fragile

Required mechanisms:
- DB-side write resistance for derived read paths
- filesystem boundary limited to side-car run root
- artifact provenance labels on every operator-visible output
- rebuild mismatch classes that fail loudly
- delete-side-car conformance test for `openclaw-mem`

Endgame verifier:
- deleting the side-car leaves base `openclaw-mem` conformance unchanged

### Layer 1. Continuity claim builder
Purpose:
- assemble structured claim candidates from records, events, priors, and receipts

Inputs:
- observations
- episodic events
- bounded recent context summaries
- persona prior inputs (Nuwa or equivalent)
- explicit operator receipts
- prior continuity artifacts only as derived references, never as authority

Claim families:
- roles
- goals
- stances
- refusals
- style commitments
- tensions
- release states

Required output for each claim candidate:
- stable claim id
- claim family
- support evidence refs
- support score components
- contradiction pressure
- prior contribution
- release influence
- confidence band
- fragility marker
- provenance block

Design rule:
- the builder proposes candidates, not truth

### Layer 2. Adjudication engine
Purpose:
- convert raw candidates into governed continuity states

Why this layer exists:
Without adjudication, the side-car is just a clever summarizer with confidence theater.

Adjudication states:
- `accepted`
- `tentative`
- `fragile`
- `contested`
- `retired`
- `rejected`

Base adjudication rules:
- prior-only claims cannot rise above `tentative`
- high contradiction pressure blocks `accepted`
- released claims cannot silently recover to `accepted` without new support
- operator-issued retirement wins over passive continuity inertia
- low-evidence high-coherence claims must be labeled `fragile`
- memory-of-record and explicit operator receipts outrank prior-shaping lanes

Endgame requirement:
- `arbiter_policy` becomes a real executable adjudication contract, not just metadata

Endgame verifier:
- the same input bundle always yields the same adjudication result and receipts

Freeze blocker:
- this layer is **not freeze-ready** until it has a rule table, negative fixtures, and an explicit determinism boundary

### Layer 3. Claim graph and lifecycle ledger
Purpose:
- move from snapshot-only outputs to governed claim objects over time

Status:
- planned, pending adjudication freeze

Core idea:
Each continuity claim becomes a first-class node with history, not just a field inside the latest JSON snapshot.

Each node carries:
- current adjudication state
- support history
- contradiction history
- release history
- migration history
- predecessor/superseded links
- last rebuild verdict
- last sensitivity verdict

Key relations:
- `supported_by`
- `pressured_by`
- `weakened_by`
- `retired_by`
- `supersedes`
- `revalidated_by`

Why this matters:
- diff stops being only before/after text
- migration compare becomes structural
- retirement becomes queryable
- false continuity becomes easier to catch

Non-goal:
- this graph is not a second memory store; it is a derived governance graph

### Layer 4. Release / rebind / retirement control plane
Purpose:
- give operators explicit, auditable ways to manage continuity without rewriting history

Status:
- planned, pending adjudication freeze

Required operations:
- weaken claim
- retire claim
- rebind claim after explicit review
- approve or reject migration candidate
- rebuild from source truth
- mark instability / suspend publication

Required receipt fields:
- receipt id
- actor
- target claim id
- operation
- reason
- scope/session boundary
- before/after adjudication state
- rebuild impact summary
- timestamp

Hard rule:
- release and retirement affect future derivation and presentation, not raw source memory

Endgame verifier:
- every governance action can be replayed and audited

### Layer 5. Dual-surface presentation layer
Purpose:
- keep operator truth and public-safe expression separate

Status:
- planned, pending adjudication freeze

#### Operator surface
For advanced operators, show:
- current adjudicated continuity state
- accepted / tentative / fragile / contested claims
- attachment map with score factors
- drift diff with risk flags
- release history
- migration compare
- instability warnings
- why-this-claim receipts

#### Public-safe surface
For bounded user-facing uses, show only:
- continuity summary
- high-level drift notices
- explicit instability warning
- insufficient evidence warning

Hard rule:
- the public-safe surface may summarize, but may not expose governance theater as ontological truth

### Layer 6. Anti-delusion instrumentation layer
Purpose:
- make overclaim and self-flattering coherence visible before humans start trusting it too much

Status:
- planned, pending adjudication freeze

Required instruments:
- prior-dominance alerts
- low-evidence / high-coherence warning
- sensitivity check: remove top N evidence refs, recompute claim state
- counterfactual rebuild diff
- long-horizon divergence monitor
- adversarial overclaim benchmark

Key endgame metric families:
- overclaim rate
- fragile-claim exposure rate
- adjudication reversal rate
- migration shock rate
- rebuild mismatch rate
- divergence from memory-of-record over time

Design rule:
- if the system cannot explain why a claim is brittle, it is not allowed to sound certain

## Endgame operator contracts

### Contract A. Authority
- memory-of-record always wins
- side-car claims are derived and retractable
- persona prior lanes are bounded contributors only

### Contract B. Adjudication honesty
- every published claim has a state, not just a score
- every strong claim has evidence and rationale
- every weak claim is labeled weak

### Contract C. Reversibility
- disable is allowed and normal
- rebuild is allowed and normal
- retirement is allowed and normal
- instability is a valid terminal output

### Contract D. Surface discipline
- operator language may be precise
- public language must remain restrained
- no soul/consciousness/self-awareness theater in product copy

Minimum public-safe export rules:
- banned nouns: `soul`, `consciousness`, `true self`, `inner self`, `self-aware`, `sentient`
- required hedges: `derived`, `non-authoritative`, `current continuity signal`, or `insufficient evidence`
- forbidden export states: raw `accepted` claims may be summarized, but `fragile` and `contested` claims must never be rendered as stable identity facts

## Endgame non-goals
- no sentience claims
- no therapeutic persona authority
- no rewriting or deleting source records through continuity operations
- no black-box LLM-only verdict path without inspectable receipts
- no "always stable self" promise
- no silent migration acceptance

## Success criteria for the endgame
The endgame deserves its name only when all are true:
1. removing the side-car leaves `openclaw-mem` intact
2. continuity claims are first-class governed objects, not only prose summaries
3. adjudication states are deterministic and inspectable
4. release / retirement / rebuild / compare all emit reliable receipts
5. fragile and contested states are treated as product truth, not failure embarrassment
6. overclaim is measured and actively constrained
7. operators can safely use the system without mistaking it for identity truth

## Honest risks

### 1. Social truth-owner drift
Even if the code stays additive, operators may start trusting continuity claims as truth because they sound insightful.

Mitigation:
- adjudication states must be visible
- fragility must be visible
- source-event counts must be visible
- public-safe surface must stay restrained

### 2. Governance theater
It is easy to stamp provenance and still have no real adjudication.

Mitigation:
- require executable adjudication rules
- require negative tests
- require rebuild and sensitivity tests

### 3. Claim graph scope explosion
A claim graph can become a second storage system in costume.

Mitigation:
- derived graph only
- no source-memory duplication
- explicit storage boundary and retention policy

### 4. Migration vanity
Model swaps may make the side-car sound more elegant while becoming less truthful.

Mitigation:
- migration compare must emphasize divergence and contested states, not only style upgrades

## Definitions appendix, freeze blockers
These definitions must be frozen before adjudication freeze can be called complete.

### contradiction pressure
Working meaning:
- normalized pressure that pushes against a claim because of explicit opposing signals or contradictory recent evidence

Freeze requirement:
- must declare exact inputs, normalization rule, and threshold bands

### support score
Working meaning:
- bounded support assembled from evidence count, recency, reinforcement, and allowed prior contribution

Freeze requirement:
- must declare exact component list and whether the score is rule-only or hybrid rule-plus-model

### confidence band
Working meaning:
- coarse confidence label derived from support and contradiction posture

Freeze requirement:
- must declare allowed bands and mapping rule from underlying inputs

### fragility marker
Working meaning:
- warning that a claim loses stability quickly when its support is sparse, prior-dominant, or contradicted

Freeze requirement:
- must declare at least one counterfactual sensitivity test that can set this marker

### prior contribution
Working meaning:
- the bounded share of support attributable to persona-prior lanes

Freeze requirement:
- must declare ceiling, weighting path, and publication consequences when priors dominate evidence

### determinism boundary
Working meaning:
- explicit closure of what counts as the adjudication input bundle

Freeze requirement:
- must name source inputs, ordering, receipt set, and model-pinning assumptions
- if any part depends on non-deterministic model judgment, that must be declared as a separate lane rather than silently folded into deterministic adjudication

## Recommended rollout phases

### Phase E0. Constitutional hardening
Goal:
- make additive-only boundary and rollback discipline mechanical

Must ship:
- delete-side-car conformance proof
- runtime write resistance
- rebuild mismatch errors
- receipt-only governance mutations

### Phase E1. Adjudication v1
Goal:
- move from scored claims to governed claim states

Must ship:
- adjudication state machine
- deterministic rule table
- state transition receipts
- fragile/contested publication rules
- at least three negative/adversarial fixtures

### Phase E2. Claim graph v1
Goal:
- persist lifecycle-aware claim objects without becoming a second memory store

Entry gate:
- do not start until E1 has shipped and operator demand proves snapshot-plus-receipt history is insufficient

Must ship:
- claim node schema
- claim relation schema
- retirement/supersession links
- graph query surface for operator use

### Phase E3. Anti-delusion instrumentation
Goal:
- actively measure and constrain overclaim risk

Must ship:
- sensitivity checks
- counterfactual rebuilds
- adversarial benchmark lane
- long-horizon divergence metrics

### Phase E4. Safe dual-surface productization
Goal:
- separate operator-grade truth from public-safe phrasing

Must ship:
- operator surfaces
- public-safe summary surface
- language lint / copy guardrails
- instability-first presentation rules

## Non-stop blade map for the endgame line

### Blade E0. Endgame constitution freeze
Deliver:
- constitutional rules doc
- authority map tightened for endgame
- explicit removal test requirement
- non-stop gate criteria for when this line may push past planning

Verifier:
- every endgame claim maps to a concrete runtime or verifier mechanism

### Blade E1. Adjudication contract freeze
Deliver:
- adjudication state model
- transition rules
- publication rules
- failure-state semantics
- definitions appendix frozen
- determinism boundary frozen
- rule-only vs hybrid-rule-plus-model decision

Verifier:
- sample claims can be deterministically adjudicated by table, not vibes
- adversarial fixtures cover prior-dominant, low-evidence/high-coherence, and retired-claim revalidation cases

### Blade E2. Claim graph schema freeze
Deliver:
- claim node schema
- relation schema
- lifecycle events schema
- retention boundary

Verifier:
- graph can represent strengthen, weaken, retire, supersede, rebuild, and compare without inventing semantics

Gate:
- E2 is blocked until E1 is frozen and real operator demand justifies graph complexity

### Blade E3. Counterfactual / anti-delusion lane
Deliver:
- sensitivity rules
- overclaim metrics
- divergence metrics
- alert thresholds

Verifier:
- at least two adversarial fixtures trigger explicit warnings

### Blade E4. Control plane upgrade
Deliver:
- retirement/rebind/rebuild command contract
- state-transition receipts
- migration approval flow

Verifier:
- an operator can move a claim through weaken -> retired -> revalidated with receipts

### Blade E5. Dual-surface output contract
Deliver:
- operator surface contract
- public-safe surface contract
- language guardrails

Verifier:
- the same claim set renders differently for operator vs public-safe surfaces without changing underlying adjudication truth

### Blade E6. Endgame readiness review
Deliver:
- go/no-go review packet
- measured overclaim posture
- operator burden review
- closure criteria for saying the system is governance-mature

Verifier:
- no unresolved path still depends on operator intuition where the system claims hard governance

## Evidence status
Known facts:
- current side-car already has derived/non-authoritative posture, receipts, drift classes, and first-pass governance hardening
- current system is still snapshot-first, not claim-graph-first
- current `arbiter_policy` is metadata, not a full adjudication engine

Assumptions:
- claim graph persistence can stay derived-only without becoming a hidden second store
- deterministic adjudication will stay tractable with bounded claim families
- dual-surface rendering will reduce social truth-owner drift rather than amplify it

UNKNOWN:
- whether claim graph query value is high enough to justify its complexity
- whether public-safe surface is needed in MSP or only later
- whether some adjudication logic should stay pure rules vs hybrid rule-plus-model

## Immediate next step recommendation
Do **not** jump to implementation of the full endgame.

Next honest move:
1. run a second-brain review against this endgame architecture
2. freeze the adjudication contract as the next bounded slice
3. do **not** schedule claim-graph work until adjudication freeze plus demand check are real
4. only then open the first endgame execution blade under explicit non-stop gate criteria
