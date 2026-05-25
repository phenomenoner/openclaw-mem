# Memory Strata Follow-up TODO v0

Status: **draft backlog / no runtime changes**  
Date: 2026-05-25  
Companion: `docs/specs/memory-strata-boundary-map-v0.md`  
Topology impact: **unchanged** — this backlog does not enable, disable, install, migrate, or reconfigure anything.

## 0. Goal

Turn the memory-strata boundary map into a staged, verifier-backed work program without mixing product work and CK/Lyria local ops policy.

Primary outcomes:

1. Make product-level memory strata inspectable and testable.
2. Keep durable writes single-owner and governed.
3. Prevent episodic/docs/graph/working-set lanes from collapsing into one memory blob.
4. Slim CK/Lyria bootstrap surfaces without losing essential operating semantics.
5. Build retrieval regression questions before changing runtime defaults.

## 1. Workstreams

### WS1 — Product architecture audit

Purpose: confirm the implemented product surfaces match the desired strata model.

- [ ] Inventory implemented commands and config for:
  - [ ] durable / long-term memory engine
  - [ ] episodic append/query/search/replay/redact/gc
  - [ ] episodic semantic lane (`episodes embed/search`; shipped verbatim-semantic retrieval over episodic evidence, distinct from durable engine hybrid recall)
  - [ ] working set / backbone lane
  - [ ] docs cold lane
  - [ ] graph refresh/query/drift/provenance
  - [ ] pack / Proactive Pack
- [ ] Produce one `memory strata status` report manually from existing commands.
- [ ] Identify gaps between docs and implementation.
- [ ] Mark each gap as:
  - [ ] doc drift
  - [ ] missing test
  - [ ] missing CLI/API
  - [ ] behavior bug
  - [ ] product decision needed

Verifier:

- A markdown audit report listing command evidence, config evidence, and unresolved unknowns.
- No source/runtime changes in this workstream.

Candidate artifact:

- `docs/receipts/memory-strata-product-audit-YYYY-MM-DD.md`

---

### WS2 — Durable / long-term memory policy hardening

Purpose: ensure long-term memory is not overloaded as both retention pool and hot-context prefix.

- [ ] Check current engine selection mode and whether `tier_quota_v1` is default or still gated.
- [ ] Build a small recall regression set with must/nice/unknown saturation cases.
- [ ] Verify repeat suppression behavior or document missing knobs.
- [ ] Verify Working Set dedupe against hot recall.
- [ ] Confirm receipts expose:
  - [ ] selection mode
  - [ ] quota usage
  - [ ] suppressed-by-repeat counts
  - [ ] pinned-by-working-set counts
  - [ ] excluded-as-backbone-duplicate counts
- [ ] Decide whether promotion from current mode to `tier_quota_v1` is product-ready.

Verifier:

- Synthetic fixture where a large `must_remember` pool does not suppress relevant `nice_to_have` recall.
- Receipt diff proving why selected memories were included/excluded.

Product vs ops:

- Product: selection algorithm, knobs, receipts, tests.
- Ops: which CK/Lyria memories are must/nice/unknown.

---

### WS3 — Episodic memory posture review

Purpose: verify episodic memory remains append-only evidence, not ungoverned durable truth.

- [ ] Confirm current spool/extract/ingest paths on this host.
- [ ] Confirm retention defaults and whether cron GC is enabled or manual.
- [ ] Verify summary-only default for query/replay/search.
- [ ] Verify payload inclusion requires explicit opt-in.
- [ ] Test redaction path on fixture data, not live sensitive rows.
- [ ] Confirm scope derivation behavior and fallback policy.
- [ ] Document whether conversation capture is enabled and what artifacts are stripped.

Verifier:

- Fixture-based append → ingest → query → replay → redact → query receipt.
- Counterfactual: query without `--include-payload` must not return raw payload.

Product vs ops:

- Product: schema, redaction, retention, CLI behavior.
- Ops: which sessions/scopes CK/Lyria chooses to capture or exclude.

---

### WS4 — Episodic semantic lane evaluation

Purpose: decide whether semantic retrieval over episodic evidence improves raw-trail recovery enough to use routinely, without confusing it with durable engine hybrid recall.

- [ ] Select 10 real episodic evidence queries.
- [ ] Run lexical baseline.
- [ ] Run hybrid/vector mode after `episodes embed` on the relevant scope.
- [ ] Compare hit quality, noise, and trace receipts.
- [ ] Check embedding freshness and model consistency.
- [ ] Define when to use episodic semantic lane vs durable recall.

Verifier:

- Before/after table: query, expected session/evidence, lexical result, hybrid result, verdict.
- At least one negative/counterfactual query where hybrid should not overclaim.

Product vs ops:

- Product: lane mechanics, trace, embedding refresh behavior.
- Ops: which scopes get embedded and how often.

---

### WS5 — Working Set / Backbone contract

Purpose: keep active context useful without turning it into stale hidden memory.

- [ ] Identify current Working Set source records and persistence location.
- [ ] Confirm whether each backbone item cites a source durable/doc/decision record.
- [ ] Define TTL or refresh triggers.
- [ ] Verify dedupe against hot recall.
- [ ] Define stale-backbone detection.
- [ ] Decide which items are allowed to be pinned vs must re-win relevance.

Verifier:

- Trace showing Working Set injection plus hot recall exclusions for duplicate content.
- Stale Working Set fixture that produces a warning or replacement candidate.

Product vs ops:

- Product: Working Set schema, trace, TTL/staleness rules.
- Ops: CK/Lyria active-goal contents.

---

### WS6 — Docs cold lane and bootstrap slimming

Purpose: move low-frequency long-form truth out of hot bootstrap while keeping it searchable and citable.

- [ ] Audit `MEMORY.md` and `AGENTS.md` for low-frequency details.
- [ ] Identify content that should move to docs/operator canon/skill appendix.
- [ ] Verify docs cold lane can retrieve moved content.
- [ ] Create a retrieval test before deleting or moving any bootstrap rule.
- [ ] Target `MEMORY.md` below safer operating size after moves.

Verifier:

- Pre/post file sizes.
- Retrieval test for every moved high-value rule.
- Diff review proving no authority boundary was lost.

Product vs ops:

- Product: docs cold lane retrieval quality and receipts.
- Ops: CK/Lyria bootstrap content choices, including non-compressible semantics that must remain hot-loaded:
  - CK address/pronoun rule
  - core persona and truth-first stance
  - authority boundaries
  - memory recall requirement for prior context
  - non-stop / stop-loss contract

---

### WS7 — Graph / topology governance

Purpose: make relationship retrieval useful without making graph cache a competing truth source.

- [ ] Write local CK/Lyria graph ontology v0 outside product defaults, or under an explicitly ops-only docs path:
  - [ ] node types
  - [ ] edge types
  - [ ] naming rules
  - [ ] provenance requirements
  - [ ] privacy exclusions
- [ ] Build one small topology fixture for a real ops line.
- [ ] Run upstream/downstream/writers/provenance queries.
- [ ] Run drift/orphan checks if available.
- [ ] Decide which graph relationships belong in product examples vs private local ontology; private ontology must not become a shipped default.

Verifier:

- Topology fixture + query outputs.
- Provenance for every edge.
- Counterfactual: derived graph DB deleted/rebuilt from topology source without losing truth.

Product vs ops:

- Product: graph query/refresh/drift/provenance CLI and schema.
- Ops: CK/Lyria ontology and private relationship graph policy.

---

### WS8 — Pack / Proactive Pack integration review

Purpose: ensure final context injection remains bounded, cited, and debuggable.

- [ ] Run `pack` on representative queries with graph/docs/episodic/durable candidates.
- [ ] Check budget enforcement.
- [ ] Check include/exclude reasons.
- [ ] Check source coverage and citations.
- [ ] Check failure posture when a lane is unavailable.
- [ ] Check whether lifecycle `last_used` or equivalent updates are clear and bounded.

Verifier:

- `pack --trace` artifacts for happy path and one failed-lane path.
- Counterfactual: disabling graph lane still produces baseline pack with failure noted.

Product vs ops:

- Product: pack contract, trace schema, failure posture.
- Ops: which lanes are enabled for CK/Lyria prompts by default.

---

### WS9 — Promotion / writeback governor

Purpose: define when evidence becomes durable truth.

- [ ] Define candidate sources:
  - [ ] episodic events
  - [ ] docs cold lane
  - [ ] graph topology/provenance
  - [ ] pack traces
  - [ ] user explicit memory requests
- [ ] State explicitly that none of these sources write durable memory until the governed promotion contract is implemented and enabled.
- [ ] Define allowed candidate categories:
  - [ ] preference
  - [ ] decision
  - [ ] project state
  - [ ] operating rule
  - [ ] relationship/topology fact, with explicit privacy/scope gate
- [ ] Define blocked categories:
  - [ ] secrets
  - [ ] transient misunderstandings
  - [ ] untrusted external claims without provenance
  - [ ] private relationship/narrative material outside explicit scope
- [ ] Create review packet schema:
  - [ ] proposed memory text
  - [ ] source evidence refs
  - [ ] scope
  - [ ] category
  - [ ] trust tier
  - [ ] expiry / retention tier
  - [ ] rollback/delete command
- [ ] Define apply receipt.

Verifier:

- Fixture with 5 candidates: 2 accepted, 2 rejected, 1 deferred.
- First implementation cycles require apply dry-run review packets without writes; live apply can be enabled only after reviewed receipts prove safe.

Product vs ops:

- Product: generic promotion/review/apply workflow, including dry-run-first and rollback receipt requirements.
- Ops: CK/Lyria thresholds and categories.

---

### WS10 — Retrieval regression harness

Purpose: make future memory changes measurable before changing defaults.

- [ ] Build 10–20 real queries grouped by intent:
  - [ ] stable preference / decision
  - [ ] session trail
  - [ ] raw wording
  - [ ] active goal
  - [ ] spec/doc lookup
  - [ ] dependency/impact
  - [ ] final pack quality
- [ ] Define expected lane(s) and expected evidence.
- [ ] Run current baseline.
- [ ] Save machine-readable results.
- [ ] Use same set before any default changes.

Verifier:

- Regression fixture file.
- Baseline receipt.
- A report that names misses and false positives.

Product vs ops:

- Product: reusable harness format and runner.
- Ops: CK/Lyria private query set.

## 2. Suggested execution order

### Milestone 1 — Map before mutation

- [ ] WS1 Product architecture audit
- [ ] WS10 Retrieval regression harness baseline
- [ ] WS6 Bootstrap slimming pre-audit only

Exit criteria:

- We know what exists, what is enabled, and what fails today.
- No runtime behavior changed.

### Milestone 2 — Evidence lanes

- [ ] WS3 Episodic posture review
- [ ] WS4 Episodic semantic lane evaluation
- [ ] WS8 Pack trace review

Exit criteria:

- Raw evidence retrieval is understood and bounded.
- Pack trace can explain final injection.

### Milestone 3 — Activation quality

- [ ] WS2 Durable / long-term policy hardening
- [ ] WS5 Working Set contract, including whether any pack/use-signal writeback is allowed

Exit criteria:

- Retention and activation are empirically separated.
- Stable must memories no longer monopolize hot context.

### Milestone 4 — Relationship memory

- [ ] WS7 Graph / topology governance
- [ ] Integrate graph findings into pack regression set.

Exit criteria:

- Graph answers relationship questions with provenance.
- Graph remains derived unless backed by topology source.

### Milestone 5 — Governed promotion

- [ ] WS9 Promotion / writeback governor
- [ ] Apply only after dry-run review packets prove safe.

Exit criteria:

- Evidence-to-truth promotion is explicit, reversible, and receipted.

## 3. Open decisions for CK

These should be answered before broad rollout, not before this documentation commit.

1. Should CK/Lyria local workspace governance live inside `openclaw-mem` docs, the workspace operator canon, or both with a pointer split?
2. Which scopes are allowed to use episodic conversation capture by default?
3. Should private relationship/narrative memory be excluded from all graph defaults unless explicitly scoped?
4. What is the target safe size for `MEMORY.md` after slimming: 8KB, 10KB, or 12KB?
5. After verifying current gating/default state, should `tier_quota_v1` be treated as a product promotion candidate now, or wait for a regression baseline?
6. Should graph be used in `pack --use-graph=auto` for CK/Lyria local tasks by default, or stay manual until regression evidence exists?

## 4. Stop-loss rules

Stop and report if any workstream hits one of these:

- Two attempts fail with the same root cause.
- Runtime/config change becomes necessary before a read-only audit is complete.
- A proposed change would create a second durable write path.
- A lane starts returning private/unsafe content outside its scope.
- A verifier cannot distinguish working behavior from broken behavior.

## 5. Closure checklist for future implementation slices

Before claiming any future slice complete:

- [ ] Spec and verifier named before mutation.
- [ ] Product vs ops boundary stated.
- [ ] Runtime/topology impact stated.
- [ ] Dry-run or fixture smoke run.
- [ ] Counterfactual test included where meaningful.
- [ ] Human-readable report derived from artifacts.
- [ ] Rollback note included.
- [ ] If rules/routing/docs/topology changed, run stale-rule retirement review.
