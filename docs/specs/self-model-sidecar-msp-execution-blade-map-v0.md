# self-model sidecar MSP execution blade map v0

Status: draft
Date: 2026-04-18
Depends on:
- `docs/specs/self-model-sidecar-contract-v0.md`
- `docs/specs/self-model-sidecar-schema-v0.md`
- `docs/specs/self-model-sidecar-rebuildability-v0.md`
Goal state: installable, enableable, and autonomously working MSP
Topology intent: additive side-car with explicit enablement path

## Verdict
This line is now ready to enter implementation, but only through a staged non-stop blade map.

Target is not just "feature complete". Target is:
- installable
- enableable
- verifier-backed
- safe to leave running autonomously
- still clearly non-authoritative relative to `openclaw-mem`

Do not jump straight from docs to autonomy wiring. The honest path is seven blades.

## Whole-picture promise
Ship a side-car that can be installed into `openclaw-mem`, enabled with explicit operator intent, produce continuity artifacts automatically, and survive disable/re-enable cycles without damaging base memory behavior.

## Success bar for MSP
An MSP-ready state means all of the following are true:
1. package/code can be installed in a normal `openclaw-mem` environment
2. `continuity current` and `continuity attachment-map` work on fixture and real bounded data
3. continuity snapshots can be generated automatically on a bounded cadence
4. diff/tension surfaces make drift legible
5. side-car can be enabled/disabled explicitly
6. autonomous runs produce receipts, not silent magic
7. kill-switch and rebuild path are proven
8. docs explain how to install, enable, observe, disable, and recover

## Non-stop execution order

### Blade 0. Planning freeze closure
Already completed.

Exit artifacts:
- contract v0
- schema v0
- rebuildability v0

### Blade 1. Read-only core surfaces
Deliver:
- continuity domain scaffolding
- `continuity current`
- `continuity attachment-map`
- fixture loader / fixture outputs
- smoke tests

Verifier:
- two-agent fixture set produces distinct outputs
- no-op restart stability test stays green
- outputs carry derived/non-authoritative labels

Stop-loss:
- if the code must invent contract semantics, stop and return diff against docs

### Blade 2. Diff and tension lane
Deliver:
- `continuity diff`
- `continuity tension-feed`
- drift classification logic
- migration compare-ready internal diff model

Verifier:
- prompt/model/role perturbation fixture produces meaningful diff
- no-op restart yields `no_op` or near-zero drift
- tensions cite sources/signals

Stop-loss:
- if diff output only parrots prose without stable machine structure, cut scope and fix schema adherence

### Blade 3. Persistence and rebuild lane
Deliver:
- durable state root wiring
- snapshot persistence
- attachment persistence
- diff persistence
- rebuild receipt emission
- deterministic rebuild command/path

Verifier:
- rebuild from source reproduces artifacts for a fixed fixture input set
- rebuild mismatches surface explicitly
- provenance present on all derived artifacts

Stop-loss:
- if any artifact cannot be reproduced from allowed sources, freeze and adjudicate before continuing

### Blade 4. Enable/disable control plane
Deliver:
- feature flag / enablement config
- install docs and config snippet
- disable path
- kill-switch smoke
- zero-regression proof for base `openclaw-mem`

Verifier:
- enabled state produces continuity artifacts
- disabled state leaves base memory behavior intact
- disable/re-enable cycle works without hidden residue

Stop-loss:
- if enable/disable mutates base memory semantics invisibly, stop

### Blade 5. Autonomous working lane
Deliver:
- bounded scheduler/controller path for automatic snapshot generation
- observe receipts for autonomous runs
- cadence/threshold config
- dry-run mode

Verifier:
- autonomous dry-run emits receipts over multiple cycles
- bounded live mode produces artifacts without manual triggering
- no silent failures, every skipped run has a reason

Stop-loss:
- if autonomous mode cannot explain why it ran or skipped, it is not ready

### Blade 6. MSP installability and operator story
Deliver:
- docs: install / enable / observe / disable / rebuild / recover
- package wiring or plugin registration path
- showcase artifacts
- before/after migration compare story

Verifier:
- fresh operator can follow install docs on bounded environment
- one end-to-end demo works without repo archeology
- product story can be shown with real artifacts

Stop-loss:
- if the operator story depends on implicit workspace tribal knowledge, docs are not done

### Blade 7. Autonomy readiness review
Deliver:
- explicit review of safety, receipts, kill-switch, rebuild, and operator burden
- go/no-go packet for leaving it running

Verifier:
- autonomous runs have receipts
- disable path proven
- rebuild path proven
- operator burden judged acceptable

Stop-loss:
- if autonomy still requires constant babysitting, do not declare it autonomously working

## Recommended first implementation slice
Start with Blade 1 only.

Reason:
- fastest proving edge
- highest semantic pressure relief
- produces visible product value
- creates the artifacts needed for every later blade

## Dependency rules
- do not start Blade 3 before Blade 1 outputs are real
- do not start autonomous scheduling before enable/disable control plane exists
- do not expose release/rebind publicly before persistence and rebuild are proven
- do not claim MSP closure until install docs and autonomy receipts exist

## Verification ladder
1. fixture tests
2. bounded real-data smoke
3. persistence + rebuild smoke
4. enable/disable smoke
5. autonomous dry-run soak
6. bounded live autonomous proof

## Topology / mutation posture
- planning phase: topology unchanged
- implementation may add side-car package/config/docs surfaces
- autonomy phase may add scheduler/controller wiring, which becomes a topology-affecting change and must be receipted as such

## Honest readiness status
Current state:
- ready for implementation
- not ready to promise autonomous working MSP in one blind coding pass
- ready to begin Blade 1 immediately

Meaning:
- we are out of spec fog
- we are not yet at install/enable/autonomy closure
- the line is mature enough to hand to a coding worker slice by slice without hand-wavy invention
