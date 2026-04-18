# self-model sidecar contract v0

Status: draft
Date: 2026-04-18
Depends on:
- `docs/specs/self-model-sidecar-msp-v0.md`
- `docs/specs/self-model-sidecar-execution-brief-v0.md`
Topology: unchanged

## Verdict
Freeze the semantic contract around a **derived self-model side-car** while keeping `openclaw-mem` as the sole authority for memory-of-record.

Recommended operator naming:
- internal concept: **self-model side-car**
- external/operator surface default: **continuity**

Reason:
- `self` is product-strong but anthropomorphism-heavy
- `continuity` is more truthful for a first operator surface
- docs may still describe the underlying concept as self-model where precision helps

## Whole-picture promise
Give long-lived agents an inspectable, diffable, governable continuity layer without implying consciousness or creating a second truth owner.

## Core semantic objects

### 1. self-model
Definition:
- a derived, editable, non-authoritative representation of who the agent currently appears to be across time

Includes:
- recurring stances
- active goals
- role commitments
- persistent refusals
- stylistic commitments
- recent tensions affecting continuity

Excludes:
- raw memory-of-record
- truth claims about the user
- claims of consciousness or inner sentience

Operational test:
- if the artifact cannot be recomputed from upstream records, priors, config, and release receipts, it is not a valid self-model artifact

### 2. attachment
Definition:
- the measurable strength with which the side-car protects or preserves a stance, role, goal, refusal, or style commitment

Attachment is a score, not a mystical essence.
It must be explained through observable factors such as:
- recency
- reinforcement count
- contradiction pressure
- explicit operator pinning
- persona-prior support
- release history

Operational test:
- every attachment score must include an evidence bundle or rationale fields sufficient for human inspection

### 3. release
Definition:
- a governed operation that weakens, retires, or de-prioritizes a stance binding in the derived self-model

Release is not deletion of source memory.
Release only affects future self-model derivation and continuity weighting.

Operational test:
- release produces a durable receipt with target stance id, reason, actor, timestamp, and resulting state

### 4. drift
Definition:
- a change in the derived self-model between two snapshots

Drift classes:
- organic drift
- induced drift
- suspicious drift
- no-op / insignificant drift

Operational test:
- every drift event references before/after snapshots and a machine-readable change summary

### 5. threat / tension
Definition:
- a contradiction, shock, or unresolved pressure that may destabilize continuity or force a stance update

Examples:
- prompt rewrite shock
- model swap shock
- persona-prior conflict
- contradiction between recent actions and long-held stance

Operational test:
- threat/tension entries must reference the conflicting sources or signals

## Authority map
### `openclaw-mem` remains authoritative for
- Store
- retrieval / pack assembly
- Observe receipts
- durable factual memory
- source interaction records

### side-car may be authoritative only for
- self-model snapshots
- attachment scores
- continuity diff artifacts
- release receipts
- advisory continuity hints

### side-car may not do
- overwrite source memory-of-record
- silently alter Store truth
- declare user truth from persona priors
- erase contradiction history

## Nuwa / persona distillation contract
Nuwa is allowed as a **prior-shaping input lane** only.

Allowed uses:
- stylistic prior hints
- recurring trait priors
- self-description priors

Disallowed uses:
- final identity authority
- direct overwrite of memory-derived stance
- contradiction suppression
- source-memory deletion or rewrite

Weighting rule:
- a Nuwa prior may raise confidence in a stance, but may not unilaterally create an authoritative stance without corroborating memory-derived evidence or explicit operator action

## Naming contract
Recommended CLI namespace for v0:
- `python3 -m openclaw_mem continuity ...`

Canonical naming rule:
- operator surface noun: `continuity`
- internal architecture term: `self-model`
- artifact prefixes should follow the operator noun for grep-ability, for example `cnt_snap_`, `cnt_diff_`, `cnt_rel_`

Rationale:
- lower anthropomorphism risk
- cleaner product posture for operators
- leaves room to discuss self-model internally without putting `self` at the sharp operator edge

Compatibility note:
- `self` may later exist as an alias if product posture shifts, but should not be the default in v0

## Non-goals
- no claim of self-awareness, sentience, or consciousness
- no Buddhist truth claims or spiritual coaching surface
- no therapy feature set in v0
- no replacement of `openclaw-mem` retrieval or memory-of-record
- no hidden second owner for continuity truth
- no mutation path that bypasses receipts

## Anthropomorphism guardrails
Required labels on operator-facing outputs:
- derived
- editable
- non-authoritative

Prohibited product claims in v0 docs:
- "the agent has a soul"
- "the agent became conscious"
- "this reveals the true inner self"

Required explanatory stance:
- this system models continuity and attachment dynamics, not consciousness

## Why side-car, not Pack
The side-car is justified only if it owns distinct operator value that Pack alone cannot cleanly hold.

Allowed justifications:
- explicit inspectability of continuity state
- continuity diff and migration compare surfaces
- governed release/rebind operations with receipts
- separate threat/tension control plane

Review gate:
- if more than 70 percent of delivered value is only retrieval shading with no distinct control-plane surface, re-evaluate whether the thin parts belong back in Pack

## Required operator surfaces for v0
- `continuity current`
- `continuity attachment-map`
- `continuity diff`
- `continuity tension-feed`
- release surface may remain internal-only until safety review clears it

## Error namespace split
### Runtime contract errors
- `insufficient_source_evidence`
- `contradictory_source_evidence`
- `non_authoritative_overwrite_attempt`
- `missing_required_snapshot`
- `unsupported_release_target`

### Rebuild mismatch classes
These are rebuild-time validation failures, not ordinary runtime contract errors.
- `missing_upstream_source`
- `config_version_unknown`
- `release_receipt_conflict`
- `artifact_provenance_missing`
- `recomputed_artifact_mismatch`

## Acceptance checks for this contract
The contract is only valid if all are true:
1. a reviewer can explain every key term without metaphysical language
2. the operator surface does not imply authoritative selfhood
3. Nuwa remains a weighted prior, not a sovereign source
4. release affects derived continuity only, not source memory
5. the side-car still has a reason to exist beyond Pack-only shading

## Open questions
1. Should `release` be public in v0 or internal-only?
2. Should `continuity` have a `self` alias at launch or only later?
3. Do we want a distinct term for style-only attachments vs stance attachments?
4. Do we want `tension-feed` to stay named that way publicly, or expose a friendlier label while keeping `tension` as the canonical contract term?
