# self-model sidecar execution brief v0

Status: draft
Date: 2026-04-18
Depends on: `docs/specs/self-model-sidecar-msp-v0.md`
Execution posture: `櫻花刀舞 non-stop` ready after planning gates freeze
Topology intent: additive only, topology unchanged in planning phase

## Verdict
Run this line as a **three-blade planning freeze first**, then move into implementation slices.

Blade 1 must freeze the semantic contract.
Blade 2 must freeze the snapshot/attachment schemas.
Blade 3 must freeze rebuildability and truth-owner boundaries.

Do **not** start coding the side-car before all three are receipted.

## Whole-picture promise
Ship an additive self-model side-car that gives `openclaw-mem` a visible product-difference surface, without corrupting the main system's Store / Pack / Observe split or inventing a second memory truth owner.

Real milestone advanced by this line:
- `openclaw-mem` gains an inspectable, diffable, governable continuity layer.

Fake progress on this line:
- poetic docs without measurable contracts
- CLI names without schema truth
- coding a snapshot builder before rebuildability rules exist
- letting Nuwa implicitly become identity authority

## Recommended bounded slice
**Slice P0, planning freeze**

Deliver three artifacts in order:
1. **Contract freeze**
   - semantics for `self-model`, `attachment`, `release`, `threat`, `drift`
   - naming decision: operator surface `self` vs `continuity`
   - explicit non-goals and anthropomorphism guardrails
2. **Schema freeze**
   - self snapshot schema v0
   - attachment score schema v0
   - continuity diff event schema v0
3. **Rebuildability freeze**
   - exact source-of-truth map
   - rebuild procedure
   - kill-switch expectations
   - side-car state retention and persistence boundary

Exit condition for P0:
- a worker could implement `current` and `attachment-map` without inventing semantics.

## Contract / boundary rules

### System boundary
`openclaw-mem` remains authoritative for:
- memory-of-record
- retrieval / pack assembly
- observation receipts
- durable factual memory

The side-car is authoritative only for:
- derived self snapshots
- attachment scores
- continuity diffs
- release receipts
- advisory shading hints

### Inputs
Allowed inputs to the side-car:
- `openclaw-mem` records/events
- recent interaction windows or packed context summaries
- active goals / role hints when explicitly available
- Nuwa/persona distillation outputs as weighted priors
- side-car config
- explicit release/rebind operations

### Outputs
Required outputs:
- machine-readable JSON artifacts
- human-readable markdown/prose view
- stable IDs for snapshots, stances, and diff events
- receipts for release/rebind operations

### Errors / blocked states
Must distinguish at least:
- insufficient source evidence
- contradictory source evidence
- missing persona prior input
- rebuild mismatch
- non-authoritative overwrite attempt

### State changes
Planning phase: docs/specs only.
Implementation phase later may write only to side-car-derived state lanes.
No writes into `openclaw-mem` Store truth are allowed from side-car commands.

### Invariants
- side-car is rebuildable from allowed sources
- disabling side-car does not break base `openclaw-mem`
- Nuwa cannot directly overwrite memory-derived signals
- every Buddhist-flavored internal term maps to an operational metric
- operator-facing outputs label the artifact as derived and editable

## Blade map

### Blade 1. Contract freeze
**Goal**
Freeze language so later code does not smuggle metaphysics or second-owner drift.

**Deliverables**
- one-page contract doc
- naming decision for public operator surface
- non-goals / anthropomorphism guardrails section
- `why side-car, not Pack` review gate

**Verifier**
- terminology table exists with operational definitions
- every key term has a measurable or inspectable expression
- one-sentence public pitch works without metaphysical wording

**Stop-loss**
If the team cannot explain the product without "selfhood" theater, pause here.

### Blade 2. Schema freeze
**Goal**
Make implementation non-creative.

**Deliverables**
- self snapshot schema with <= 12 top-level fields
- attachment score schema including evidence inputs and scoring rationale
- continuity diff schema with stable IDs and before/after references
- example fixture artifacts for two clearly different agents

**Verifier**
- schemas compile as valid JSON examples
- two fixture agents serialize into clearly different snapshots
- a no-op restart fixture does not imply spurious drift by schema design

**Stop-loss**
If the schema starts hiding product decisions inside freeform text blobs, cut scope.

### Blade 3. Rebuildability freeze
**Goal**
Prevent second truth-owner drift before code exists.

**Deliverables**
- source-of-truth map
- rebuild procedure from records + priors + release receipts
- persistence path / retention rule
- kill-switch and disable behavior spec

**Verifier**
- rebuild procedure can be described as a deterministic ordered sequence
- kill-switch leaves base `openclaw-mem` intact by contract
- every durable side-car artifact names its upstream source class

**Stop-loss**
If any required side-car state cannot be rebuilt, it needs explicit justification or must be cut.

## Verifier plan
### Planning-phase verifiers
- spec review against current MSP doc
- terminology table completeness check
- example snapshot JSONs for at least two agents
- example attachment map JSON
- rebuild procedure walkthrough with no hidden source
- topology statement: unchanged

### First implementation verifiers after P0
These are named now so planning stays honest:
- `current` command smoke on fixture data
- `attachment-map` command smoke on fixture data
- no-op restart stability test
- side-car disable smoke proving no regression to base memory path

## Delegation packet
If delegated to a coding worker after P0 freeze, give exactly this packet:

### Objective
Implement the first read-only side-car surfaces, `current` and `attachment-map`, against the frozen contract/schema/rebuildability docs.

### Scope boundary
- touch only side-car surfaces and supporting docs/tests
- do not add release/rebind mutating paths yet
- do not change `openclaw-mem` Store truth model
- do not broaden Nuwa into an authority path

### First artifact expected
- anomaly list against the frozen contract
- minimal patch plan
- fixture-based sample outputs

### Exact verifier
- fixture smoke for `current`
- fixture smoke for `attachment-map`
- no-op restart stability test remains green

### Files/surfaces not to touch
- live production cron topology
- unrelated optimize-assist surfaces
- broad repo restructures

### Stop-loss conditions
- contract ambiguity blocks implementation
- schema needs invention beyond frozen docs
- rebuildability rule cannot be upheld in the proposed codepath

## Rollback / WAL closure
Planning phase closure bundle:
- spec docs added/updated
- topology statement: unchanged
- no runtime mutation claims

When implementation truth changes later, closure must include:
- code + tests + docs
- smoke receipts
- topology statement
- decision/WAL update if side-car posture or operator guidance changes materially

## Tradeoffs / open risks
- `self` is product-stronger, `continuity` is safer. Default recommendation: keep the internal concept as self-model, but strongly consider `continuity` as the operator surface if anthropomorphism risk feels too high.
- A side-car gives a cleaner control plane today, but some thin shading logic may later belong in Pack. Review after first two read-only commands ship.
- Nuwa integration is strategically valuable, but it should enter only after the memory-derived baseline exists.

## Progress-ready next artifacts
The next three docs to write under non-stop execution are:
1. `self-model-sidecar-contract-v0.md`
2. `self-model-sidecar-schema-v0.md`
3. `self-model-sidecar-rebuildability-v0.md`
