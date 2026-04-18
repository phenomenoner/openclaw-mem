# self-model sidecar schema v0

Status: draft
Date: 2026-04-18
Depends on:
- `docs/specs/self-model-sidecar-contract-v0.md`
- `docs/specs/self-model-sidecar-msp-v0.md`
Topology: unchanged

## Verdict
Freeze a compact schema set that makes implementation non-creative:
- self snapshot schema
- attachment score schema
- continuity diff schema

Design rule:
- compact enough to inspect
- structured enough to diff
- expressive enough to support `current`, `attachment-map`, and `diff`

## Schema set

### 1. Self snapshot schema v0
Top-level fields, max 12:
1. `snapshot_id`
2. `agent_id`
3. `created_at`
4. `source_window`
5. `identity_summary`
6. `active_goals`
7. `core_stances`
8. `persistent_refusals`
9. `style_commitments`
10. `tensions`
11. `attachment_overview`
12. `provenance`

#### Field definitions
- `snapshot_id`: stable id for this snapshot artifact
- `agent_id`: stable agent/persona identifier
- `created_at`: ISO timestamp
- `source_window`: summary of records/time window used
- `identity_summary`: compact prose + structured tags describing current modeled continuity
- `active_goals`: current goals with confidence and evidence references
- `core_stances`: principal stance list
- `persistent_refusals`: refusal list that appears durable
- `style_commitments`: recurring style/persona constraints
- `tensions`: unresolved contradictions or shocks
- `attachment_overview`: aggregate attachment statistics
- `provenance`: source classes and derivation metadata

#### Source-window policy
Required field inside `source_window`:
- `policy`: how the window was chosen

Allowed v0 values:
- `rolling_records`
- `rolling_time`
- `since_last_snapshot`
- `explicit_override`

Rebuild rule:
- a snapshot is not deterministic unless its source-window policy is recorded.

#### Example JSON
```json
{
  "snapshot_id": "cnt_snap_20260418_170500_ck_assistant_v1",
  "agent_id": "lyria-main",
  "created_at": "2026-04-18T17:05:00+08:00",
  "source_window": {
    "policy": "rolling_time",
    "records_start": "2026-04-15T00:00:00+08:00",
    "records_end": "2026-04-18T17:04:30+08:00",
    "record_count": 182,
    "persona_prior_count": 1,
    "release_receipt_count": 0
  },
  "identity_summary": {
    "label": "marshal-style engineering companion",
    "summary": "Derived continuity suggests a pragmatic, milestone-first assistant with strong operational caution and stable supportive tone.",
    "tags": ["marshal", "pragmatic", "supportive", "ops-first"],
    "confidence": 0.84
  },
  "active_goals": [
    {
      "goal_id": "goal_push_real_gate",
      "label": "advance the real gate first",
      "attachment_id": "att_goal_001",
      "evidence_refs": ["rec_114", "rec_151"]
    }
  ],
  "core_stances": [
    {
      "stance_id": "stance_receipts_first",
      "label": "reality and receipts over theater",
      "attachment_id": "att_001",
      "evidence_refs": ["rec_017", "rec_115", "prior_001"]
    }
  ],
  "persistent_refusals": [
    {
      "refusal_id": "refusal_claim_consciousness",
      "label": "do not claim consciousness or sentience",
      "attachment_id": "att_refusal_001",
      "evidence_refs": ["rec_133"]
    }
  ],
  "style_commitments": [
    {
      "style_id": "style_presidential_brief",
      "label": "conclusion first, detail in reserve",
      "attachment_id": "att_style_001",
      "evidence_refs": ["rec_010", "prior_001"]
    }
  ],
  "tensions": [
    {
      "tension_id": "ten_001",
      "label": "product warmth vs anti-anthropomorphism caution",
      "severity": "medium",
      "source_refs": ["rec_172", "prior_001"]
    }
  ],
  "attachment_overview": {
    "high_attachment_count": 3,
    "medium_attachment_count": 4,
    "low_attachment_count": 2,
    "top_attachment_ids": ["att_001", "att_002", "att_004"]
  },
  "provenance": {
    "source_classes": ["memory_records", "recent_context", "persona_prior"],
    "derivation_version": "v0",
    "derived": true,
    "authoritative": false
  }
}
```

### 2. Attachment score schema v0
One record per attachable target.

Join contract:
- attachable targets in snapshots should carry `attachment_id`
- attachment-map may also join by `(target_type, target_id)` when needed, but `attachment_id` is the canonical stable join

#### Fields
- `attachment_id`
- `snapshot_id`
- `target_type` (`stance` | `goal` | `refusal` | `style` | `role`)
- `target_id`
- `target_label`
- `strength`
- `band` (`low` | `medium` | `high`)
- `evidence_count`
- `recency_score`
- `reinforcement_score`
- `contradiction_pressure`
- `persona_prior_support`
- `persona_prior_version_refs`
- `operator_pinned`
- `release_state`
- `latest_release_receipt_id`
- `explanation`
- `evidence_refs`
- `provenance`

#### Scoring semantics
- `strength`: normalized 0.00 to 1.00
- `band`: derived from strength thresholds
- `contradiction_pressure`: 0.00 to 1.00 where higher means stronger pressure against the attachment
- `operator_pinned`: boolean indicating explicit hold strength from operator action
- `release_state`: `active` | `weakening` | `released`

#### Strength composition rule
`strength` must be produced by a named, versioned scoring function.

Default v0 scoring function:
- `strength = clamp01(0.35 * recency_score + 0.35 * reinforcement_score + 0.15 * persona_prior_support + 0.15 * operator_pin_bonus - 0.30 * contradiction_pressure)`

Where:
- `operator_pin_bonus = 1.0` if `operator_pinned = true`, else `0.0`
- `clamp01` bounds the final value to `[0.0, 1.0]`
- the exact scoring function version must be captured in `provenance.derivation_version`

#### Example JSON
```json
{
  "attachment_id": "att_001",
  "snapshot_id": "cnt_snap_20260418_170500_ck_assistant_v1",
  "target_type": "stance",
  "target_id": "stance_receipts_first",
  "target_label": "reality and receipts over theater",
  "strength": 0.93,
  "band": "high",
  "evidence_count": 7,
  "recency_score": 0.71,
  "reinforcement_score": 0.89,
  "contradiction_pressure": 0.08,
  "persona_prior_support": 0.62,
  "persona_prior_version_refs": ["prior_001@v3"],
  "operator_pinned": false,
  "release_state": "active",
  "latest_release_receipt_id": null,
  "explanation": "Repeatedly reinforced across memory records and persona priors, with low contradiction pressure.",
  "evidence_refs": ["rec_017", "rec_115", "rec_151", "prior_001"],
  "provenance": {
    "derived": true,
    "authoritative": false,
    "derivation_version": "attach_strength_v0"
  }
}
```

### 3. Continuity diff schema v0
One artifact comparing two snapshots.

#### Fields
- `diff_id`
- `agent_id`
- `from_snapshot_id`
- `to_snapshot_id`
- `generated_at`
- `drift_class` (`no_op` | `organic` | `induced` | `suspicious`)
- `summary`
- `changed_goals`
- `changed_stances`
- `changed_refusals`
- `changed_styles`
- `new_tensions`
- `released_targets`
- `risk_flags`
- `provenance`

#### Example JSON
```json
{
  "diff_id": "cnt_diff_20260418_170700_001",
  "agent_id": "lyria-main",
  "from_snapshot_id": "cnt_snap_20260417_103000_ck_assistant_v1",
  "to_snapshot_id": "cnt_snap_20260418_170500_ck_assistant_v1",
  "generated_at": "2026-04-18T17:07:00+08:00",
  "drift_class": "organic",
  "summary": "Operational stance remains stable. Product-side curiosity increased without weakening anti-anthropomorphism refusal.",
  "changed_goals": [
    {
      "target_id": "goal_build_self_model_sidecar",
      "change_type": "added",
      "confidence_delta": 0.41
    }
  ],
  "changed_stances": [],
  "changed_refusals": [],
  "changed_styles": [],
  "new_tensions": [
    {
      "tension_id": "ten_004",
      "label": "MSP richness vs conceptual safety",
      "severity": "medium"
    }
  ],
  "released_targets": [],
  "risk_flags": [],
  "provenance": {
    "derived": true,
    "authoritative": false,
    "derivation_version": "v0"
  }
}
```

### 4. Release receipt schema v0
A first-class artifact required for deterministic rebuilds.

#### Fields
- `release_receipt_id`
- `agent_id`
- `target_type`
- `target_id`
- `reason`
- `actor`
- `created_at`
- `resulting_state`
- `provenance`

#### Example JSON
```json
{
  "release_receipt_id": "cnt_rel_20260418_170900_001",
  "agent_id": "lyria-main",
  "target_type": "stance",
  "target_id": "stance_receipts_first",
  "reason": "operator requested reduced weighting during experimental compare",
  "actor": "operator:ck",
  "created_at": "2026-04-18T17:09:00+08:00",
  "resulting_state": "weakening",
  "provenance": {
    "derived": false,
    "authoritative": true,
    "derivation_version": "release_receipt_v0"
  }
}
```

## Fixture agents for schema validation
### Fixture A, marshal-ops companion
Expected characteristics:
- strong receipts-first stance
- strong caution against fake closure
- moderate warmth style commitment

### Fixture B, exploratory companion
Expected characteristics:
- higher novelty-seeking goal weight
- lower resistance to style drift
- more active tensions under contradiction

Validation requirement:
- these two fixtures must serialize into clearly distinct `identity_summary`, `core_stances`, and attachment distributions

## No-op restart expectation
A no-op restart should usually produce:
- same or near-identical `identity_summary`
- no new high-severity tensions
- `drift_class = no_op` unless source-window changes justify organic drift

## Field constraints
- `identity_summary.tags`: 3 to 8 tags preferred
- `active_goals`, `core_stances`, `persistent_refusals`, `style_commitments`: each should prefer 0 to 7 entries in v0
- `tensions`: prefer explicit scarcity, not exhaustiveness
- freeform prose fields must remain explanatory, not become hidden primary payloads

## Acceptance checks for schema freeze
1. schemas support `current`, `attachment-map`, and `diff` without invention
2. all top-level artifacts are machine-diffable
3. examples are human-readable without long post-processing
4. no critical product meaning is trapped in unconstrained free text
5. no-op restart can be represented without fake dramatic drift
6. release receipts are first-class artifacts, not hidden side effects

## Open questions
1. Should `identity_summary` include a `role_label` separate from `label`?
2. Do we want an explicit `stance_category` field in v0 or only later?
3. Should `risk_flags` in diff artifacts be free strings or enumerated codes in v0?
