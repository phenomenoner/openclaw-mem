# self-model sidecar rebuildability v0

Status: draft
Date: 2026-04-18
Depends on:
- `docs/specs/self-model-sidecar-contract-v0.md`
- `docs/specs/self-model-sidecar-schema-v0.md`
Topology: unchanged

## Verdict
Freeze rebuildability as a hard design invariant before implementation.

Rule:
- every durable side-car artifact must be rebuildable from allowed upstream sources plus explicit side-car operations
- if an artifact cannot be rebuilt, it is either out of scope or requires explicit exception review

## Whole-picture promise
Prevent the side-car from silently becoming a second truth owner while still allowing it to hold useful derived state, historical diffs, and release receipts.

## Source-of-truth map
### Authoritative upstream sources
1. `openclaw-mem` memory-of-record
   - source interaction records
   - stored memory facts
   - packed context summaries when intentionally emitted
   - observation receipts when relevant
2. explicit side-car config
   - scoring thresholds
   - source-window policy defaults
   - retention rules
   - feature flags
3. explicit release/rebind operations
   - operator-approved or system-approved release receipts
4. optional Nuwa/persona prior inputs
   - treated as weighted priors only

### Non-authoritative derived artifacts
These may be persisted, but are always rebuildable:
- self snapshots
- attachment records
- continuity diffs
- threat/tension artifacts
- migration compare outputs

## Deterministic rebuild procedure
Ordered procedure for rebuilding derived state:
1. load side-car config version
2. load source memory-of-record for the requested window or target agent
3. load applicable release receipts
4. load optional persona prior inputs
5. resolve source-window policy for the rebuild target
6. derive self snapshot under frozen schema
7. derive attachment records from the snapshot and evidence bundle using the versioned scoring function
8. derive continuity diffs from ordered snapshots
9. derive threat/tension artifacts from contradiction and shock rules
10. validate artifact provenance and non-authoritative labels

The sequence must be deterministic for a fixed input set, config version, source-window policy, and prior-version set.

## Persistence boundary
### Allowed durable state
Preferred durable root:
- `/root/.openclaw/workspace/.state/openclaw-mem-self-model-sidecar/`

Allowed persisted classes:
- snapshot artifacts
- attachment artifacts
- diff artifacts
- release receipts
- migration compare artifacts
- rebuild receipts / verification logs

Receipt sovereignty rule:
- release receipts are authoritative inputs and must live in a durable sovereign lane, not an easily-wiped transient cache
- for v0, they may live under the side-car durable root if that root is treated as sovereign durable state rather than scratch
- if the implementation cannot guarantee that durability posture, route release receipts into a broader `openclaw-mem` receipts lane instead

### Disallowed durable state
- raw duplicate copy of full memory-of-record unless explicitly justified for fixture/testing use
- silent shadow truth store for user identity
- unstated caches whose contents affect derivation but are not reproducible

## Retention rule
Default retention posture for v0:
- keep the latest derived snapshot set for active agents
- keep release receipts durably
- keep diff history long enough for migration comparison and validation
- permit pruning of rebuildable transient artifacts as long as rebuild receipts and source references remain intact

Exact numeric retention limits can remain implementation-configurable in v0, but the rule split must hold:
- receipts survive
- transient derivations may be regenerated

## Kill-switch contract
Disabling the side-car must do all of the following:
1. stop future side-car derivation work
2. stop advisory continuity outputs
3. preserve source memory-of-record untouched
4. preserve release receipts and past artifacts unless explicit cleanup is requested
5. allow later rebuild/re-enable from upstream sources and receipts

Disabling the side-car must not:
- corrupt `openclaw-mem`
- block normal memory retrieval
- mutate Store truth
- leave hidden partial weighting inside base memory behavior

## Rebuild receipt requirements
A rebuild run should emit a receipt containing at least:
- `rebuild_id`
- `agent_id`
- `config_version`
- `source_window_policy`
- source window / source counts
- persona prior inputs used
- release receipt counts
- artifact counts produced
- validation result
- mismatch count if any
- timestamp

## Mismatch handling
Required mismatch classes:
- `missing_upstream_source`
- `config_version_unknown`
- `release_receipt_conflict`
- `artifact_provenance_missing`
- `recomputed_artifact_mismatch`

Namespace rule:
- these mismatch classes are rebuild-time validation outcomes
- they are distinct from runtime contract errors such as `insufficient_source_evidence` or `unsupported_release_target`

Default posture:
- surface mismatch loudly
- do not silently bless stale artifacts as authoritative

## Nuwa-specific rebuild rule
Nuwa/persona prior inputs must be versioned and attributable.

If a prior input disappears or changes, rebuild behavior must do one of:
- recompute with the new prior version and emit drift accordingly
- mark the rebuild as using a missing/changed prior and surface the mismatch

Nuwa prior changes must never silently rewrite historical source memory.

## Migration compare posture
Migration compare is a first-class rebuild consumer.

A migration compare run should be able to rebuild:
- baseline side-car state under old config/prompt/model assumptions
- candidate side-car state under new assumptions
- a diff artifact that explains continuity changes

## Acceptance checks for rebuildability freeze
1. every durable artifact type has a named upstream source class
2. deterministic rebuild order is documented
3. kill-switch leaves base `openclaw-mem` intact by contract
4. receipts outlive transient derivations
5. missing priors or mismatches surface as explicit errors, not silent drift

## Open questions
1. Do we want snapshot content-addressing in v0 or simple stable ids first?
2. Should migration compare artifacts have separate retention from ordinary diffs?
3. Should release receipts be stored inside the side-car root or in a broader `openclaw-mem` receipts lane?
