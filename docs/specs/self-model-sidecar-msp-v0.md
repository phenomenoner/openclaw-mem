# self-model sidecar MSP v0

Status: draft
Date: 2026-04-18
Author lane: small decision council (Claude Opus 4.7 + Gemini)
Topology intent: additive side-car only, no mainline truth-owner change

## Verdict
Build it, but keep the line crisp: this is a **self-model side-car** for `openclaw-mem`, not a claim of true selfhood and not a rewrite of the main memory architecture.

The right product story is not "we created an AI self". The right story is:
- `openclaw-mem` owns what happened
- the side-car models who the agent appears to be becoming
- the system can surface, diff, and loosen attachment to that modeled identity over time

This is strong enough for an MSP because it creates a visible product difference, not just a hidden infra improvement.

## Product category
Primary label:
- **Self-Model Side-Car**

Acceptable alternates:
- Narrative Continuity Engine
- Continuity Companion for agents
- Identity Mirror for long-lived agents

Do not use as the primary public category:
- consciousness engine
- soul layer
- Buddhist AI self

## Strong thesis
The Buddhist framing of `我執` is useful as an internal design lens only if it maps to observable mechanics.

Operational translation:
- `self-model` = the current derived narrative of who the agent is
- `attachment` = how strongly the system protects specific stances, roles, goals, refusals, or values
- `release` = a governed ability to retire or weaken those bindings with receipts

So the product is not "build a self".
It is "make continuity, grip, and drift legible and controllable."

## MSP target shape
Recommended lead shape: **Identity Mirror + Drift/Attachment controls**

Why this lead shape:
- strongest developer-facing product differentiation
- lower safety risk than a user-therapeutic framing
- cleanly interoperates with current `openclaw-mem` Store / Pack / Observe split
- can absorb Nuwa/persona distillation as one source without letting it dominate truth

### User-visible MSP experience
A long-lived agent gets a new inspectable surface:
1. **Current Self View**
   - who the agent currently appears to be
   - active goals, recurring stances, core refusals, stylistic commitments
2. **Attachment Map**
   - what the agent is gripping tightly
   - why that grip exists (recency, reinforcement, contradiction pressure, persona prior)
3. **Continuity Drift Feed**
   - what changed in the modeled self since last snapshot
   - whether the change looks organic, induced, or suspicious
4. **Release / Rebind Controls**
   - retire a stale stance
   - weaken an attachment
   - accept or reject a proposed identity shift
5. **Migration Safety View**
   - compare self-model before/after model swap, prompt rewrite, or Nuwa refresh

This is already sexy enough to tell a story: the agent has a readable reflection, and that reflection can be governed.

## Non-goals
- no claim of consciousness, sentience, or Buddhist realization
- no replacement of `openclaw-mem` as memory-of-record
- no direct writes into Store truth from the side-car
- no unbounded freeform persona hallucination loop
- no therapeutic or spiritual product claims in v0

## Architecture boundary
### Main product remains authoritative
`openclaw-mem` keeps authority over:
- Store
- retrieval / pack assembly
- observation receipts
- durable factual memory

### Side-car owns only derived state
The side-car may own:
- self-model snapshots
- attachment scores
- continuity diffs
- stance-release receipts
- advisory shading hints

### Rebuildability rule
All side-car durable state must be rebuildable from:
- `openclaw-mem` records/events
- optional Nuwa/persona distillation input
- side-car config and release operations

If rebuildability fails, the design is drifting toward a second truth owner.

## Core modules
1. **Self Snapshot Builder**
   - derives current self-model from memory, recent episodes, persona priors, and active goals
2. **Attachment Scorer**
   - computes grip strength for stances/roles/commitments
3. **Continuity Diff Engine**
   - snapshots over time and explains drift
4. **Threat / Tension Detector**
   - flags contradictions, prompt-induced identity shocks, and unstable self-claims
5. **Release Controller**
   - governs stance retirement, weakening, and rebind decisions with audit trail
6. **Nuwa Ingest Adapter**
   - consumes persona-distillation outputs as weighted hints, never sole authority
7. **Observe Surface**
   - CLI/JSON/markdown/dashboard outputs for inspection and receipts

## Nuwa role
Nuwa should be treated as a **prior-shaping lane**, not a sovereign identity oracle.

Use it for:
- style/persona compression
- recurring trait priors
- likely self-description tendencies

Do not use it for:
- overriding lived memory
- erasing contradiction history
- declaring final identity truth

## Product risks
### 1) Conceptual drift
Risk: the line turns into poetic philosophy instead of measurable product behavior.
Mitigation: every Buddhist-flavored term must have an operational metric beside it.

### 2) Anthropomorphism risk
Risk: users or operators start treating the side-car artifact as a soul.
Mitigation: all outputs must be labeled as derived, editable, and non-authoritative.

### 3) System split-brain risk
Risk: the self-model drifts away from memory-of-record and becomes a hidden second owner.
Mitigation: enforce rebuildability and read-mostly interfaces.

### 4) Complexity creep
Risk: the product becomes interesting but unshippable.
Mitigation: hold v0 to five visible surfaces only: self view, attachment map, drift feed, release control, migration compare.

## Second-brain cross-validation
### Claude strongest contribution
- strongest framing: the product wins if it can be explained without metaphysical claims
- best caution: if it cannot justify its existence outside the Pack lane, it may be a Pack feature wearing a costume

### Gemini strongest contribution
- strongest framing: behavioral inertia / stance defense can create a real felt product difference
- best caution: the friction between past memory and current self-model may be a feature if surfaced properly

### Synthesis
Combined view:
- keep the side-car separate for now because drift/attachment/release deserves its own inspectable control plane
- but force a recurring review checkpoint: if 70 percent of the value is just pack shading, absorb the thin parts back into Pack later

## MSP feature set
### F1. Current Self View
Output current self-model as JSON + prose.

### F2. Attachment Map
Score and rank defended stances, goals, refusals, roles, and style commitments.

### F3. Continuity Diff
Compare two self snapshots and explain what changed.

### F4. Threat/Tension Feed
Detect contradictory inputs, model-swap shock, prompt rewrite shock, and persona conflict.

### F5. Release/Rebind Ops
Allow explicit stance retirement / weakening with receipts.

### F6. Nuwa Prior Blend
Blend persona-distillation priors into the self-model with bounded weight.

### F7. Migration Compare
Show before/after self-model for prompt or model changes.

## Proposed CLI surface (draft)
- `python3 -m openclaw_mem self current --json`
- `python3 -m openclaw_mem self diff --from <snapshot> --to <snapshot> --json`
- `python3 -m openclaw_mem self attachment-map --json`
- `python3 -m openclaw_mem self threat-feed --json`
- `python3 -m openclaw_mem self release --stance <id> --reason <text> --json`
- `python3 -m openclaw_mem self compare-migration --baseline <path> --candidate <path> --json`

Note: naming may later change from `self` to `continuity` if we want a less anthropomorphic operator surface.

## Success criteria for v0
A good v0 proves all of the following:
1. two different agents produce meaningfully different self-models
2. no-op restarts do not cause false dramatic drift
3. model or prompt changes do produce observable drift when they should
4. attachment scoring can identify at least one human-recognizable defended stance
5. disabling the side-car does not degrade `openclaw-mem` core correctness
6. side-car state can be rebuilt from source records and config

## Backlog (progress-trackable)

### EPIC A. Problem framing and contract
- [ ] A1. Write a one-page contract for self-model vs attachment vs release semantics
- [ ] A2. Decide public naming: `self` vs `continuity` operator surface
- [ ] A3. Define hard non-goals and anthropomorphism guardrails
- [ ] A4. Define "why side-car, not Pack" review gate

### EPIC B. Data model and rebuildability
- [ ] B1. Freeze self snapshot schema (<= 12 top-level fields)
- [ ] B2. Freeze attachment score schema and evidence fields
- [ ] B3. Define rebuild procedure from memory-of-record + Nuwa priors + release receipts
- [ ] B4. Define snapshot persistence path and retention policy

### EPIC C. Side-car computation lane
- [ ] C1. Build Self Snapshot Builder v0
- [ ] C2. Build Attachment Scorer v0
- [ ] C3. Build Continuity Diff Engine v0
- [ ] C4. Build Threat/Tension Detector v0
- [ ] C5. Build Release Controller v0

### EPIC D. Interfaces
- [ ] D1. Define read-only intake contract from `openclaw-mem`
- [ ] D2. Define Nuwa ingest adapter contract
- [ ] D3. Define observe outputs: JSON + markdown + optional dashboard JSON feed
- [ ] D4. Define migration compare contract for model/prompt swap tests

### EPIC E. Operator surface
- [ ] E1. Ship `current` command
- [ ] E2. Ship `attachment-map` command
- [ ] E3. Ship `diff` command
- [ ] E4. Ship `threat-feed` command
- [ ] E5. Ship `release` command
- [ ] E6. Ship `compare-migration` command

### EPIC F. Validation
- [ ] F1. Create two-agent fixture set with clear persona differences
- [ ] F2. Create no-op restart stability test
- [ ] F3. Create prompt-shift drift test
- [ ] F4. Create model-swap drift test
- [ ] F5. Create side-car kill-switch regression test
- [ ] F6. Create rebuild-from-source test

### EPIC G. MSP narrative and launchability
- [ ] G1. Produce one-sentence pitch without metaphysical language
- [ ] G2. Produce before/after screenshots or markdown artifacts for product story
- [ ] G3. Produce migration safety demo
- [ ] G4. Decide whether user-facing release control is enabled in v0 or internal-only

## Non-stop implementation shape (draft)
If this line converts into `櫻花刀舞 non-stop`, use the execution order below:
1. contract freeze
2. schema freeze
3. rebuildability proof
4. read-only intake lane
5. `current` + `attachment-map`
6. `diff` + `threat-feed`
7. `release`
8. migration compare
9. validator pack
10. product-story artifacts and backlog closure

Gate discipline:
- do not implement release ops before rebuildability and diff exist
- do not market Buddhist framing without operational metrics
- do not let Nuwa become the sole authority path

## Open questions
1. Is the operator surface more truthful as `self` or `continuity`?
2. Should release/rebind be internal-only in v0?
3. Which concrete Nuwa output format will the adapter consume first?
4. What is the first real agent fixture set for drift evaluation?
5. At what point do we decide some of this belongs back in Pack instead of the side-car?
