# Spec — optimize-assist nine-point hardening roadmap v0

## Status
- Stage: execution planning
- Scope: shortest-path non-stop push from ~5.5-6/10 toward ~9/10 for `openclaw-mem` optimize-assist safe autonomy posture
- Mode: hardening-first, fail-closed, verifier-backed

## Verdict
Do not chase 9/10 by widening mutation breadth first.
The shortest truthful path is to remove the current fail-open and trust-gap defects, then prove the controller under real end-to-end execution.

## Whole-picture promise
A 9/10-class optimize-assist lane should be able to:
- classify, challenge, verify, and promote itself using first-party evidence
- preserve family-level quarantine and controller demotion under disagreement or regression
- survive overlapping runs and partial-write crashes without corrupting controller truth
- justify its autonomy claims with non-mocked end-to-end proof, not only unit-path receipts

Fake progress would be:
- adding more autonomous mutation families before controller correctness is hardened
- accepting external gate artifacts as promotion truth
- claiming near-ceiling posture while family quarantine or controller state integrity can fail open

## Current blockers
1. Challenger family taxonomy mismatch can fail open for importance-family quarantine.
2. Promotion truth is still partly externalized through `--promotion-gate-receipt` input.
3. `controller-state.json` lacks lock + atomic-write + integrity chaining.
4. Runner confidence relies too heavily on mocked `_run` tests instead of real end-to-end execution.
5. Some gate defaults remain optimistic enough that missing evidence can be interpreted too generously.

## Score ladder

### To claim 7/10
Must land:
- unified family taxonomy
- negative test proving challenger quarantine blocks importance-family candidates
- controller-state locking + atomic rename + integrity digest

Meaning:
- bounded autonomy is now mostly trustworthy at the controller-correctness layer

### To claim 8/10
Must land:
- native promotion-truth generation inside the runner
- external promotion receipt no longer accepted as authoritative input
- promotion receipts become output artifacts chained to runner/controller truth

Meaning:
- the system no longer depends on operator-fed core evidence to widen authority

### To claim 9/10
Must land:
- non-mocked end-to-end runner harness in CI
- gate-skeptic audit pass removing optimistic safety defaults
- crash / overlap / partial-write recovery proof
- docs mapping each major safety invariant to a named verifier

Meaning:
- near-ceiling posture is supported by enforced invariants, not only architecture intent

## Blade map for `櫻花刀舞 non-stop`

### Blade A — unified family taxonomy
Target outcome:
- one canonical family classifier shared by CLI challenger path and runner filter path

Ship:
- central family helper module
- shared `FAMILY_NAMES`
- `unknown => quarantine/fail_closed`
- negative regression test proving importance-family quarantine blocks apply

Why first:
- this is the highest-ROI correctness fix and closes the largest current fail-open path

### Blade B — controller-state integrity
Target outcome:
- controller state becomes serialized, atomic, and integrity-checkable

Ship:
- lock file with exclusive write lock
- temp-file write + fsync + atomic replace
- `schema_version`, `revision`, `state_digest`
- overlap/concurrency regression coverage

Why second:
- unattended controller claims are weak if overlap can clobber truth

### Blade C — native promotion truth
Target outcome:
- promotion gating uses first-party evidence generated inside the runner

Ship:
- runner computes promotion metrics from verifier/effect/challenger/controller receipts
- promotion receipt becomes emitted output, not trusted input
- incomplete native inputs fail closed

Why third:
- this closes the biggest remaining trust gap before stronger autonomy claims

### Blade D — end-to-end runner proof harness
Target outcome:
- one real runner path proves quarantine, locking, promotion, and determinism without mocked `_run`

Ship:
- fixture-backed e2e test invoking the real runner process
- proofs for quarantine enforcement, overlap serialization, missing-input fail-closed, and deterministic rerun

Why fourth:
- this converts architecture intent into CI-enforced truth

### Blade E — gate-skeptic audit pass
Target outcome:
- no safety-critical default quietly passes when evidence is missing

Ship:
- audit all promotion/watchdog/controller boolean defaults
- replace optimistic defaults with explicit required-present semantics
- add negative tests for missing/malformed safety evidence

Why fifth:
- this is the last hardening sweep before a truthful 9/10 claim

## Bundling guidance
- Bundle Blade A with its negative regression test.
- Bundle Blade B lock + atomic rename + digest in one pass.
- Keep Blade C separate so promotion-contract changes stay easy to review/rollback.
- Land Blade D after A/B/C so e2e proof exercises the hardened controller.
- Land Blade E as a narrow audit PR/pass with explicit fail-closed regressions.

## Verifier plan
Per blade, require at least:
- one happy-path verifier
- one negative fail-closed verifier
- one artifact/receipt assertion proving the controller recorded the decision truthfully

Minimum named verifiers:
- family quarantine mismatch regression test
- controller-state overlap test
- controller-state crash/partial-write recovery test
- native promotion-truth completeness test
- end-to-end runner smoke test without mocked subprocesses
- missing-evidence gate-fail test

## Hardening review checklist
Review every blade against:
- no `unknown` enum/value passes through as allowed
- no safety-critical `dict.get(..., True)` defaults
- no silently swallowed parse/load errors in gating paths
- no ad-hoc controller-state read/write bypassing the locked helper
- every new blocker/quarantine reason emitted in receipts/counters
- at least one test that would have failed before the blade landed

## Rollback / WAL closure
For each blade that changes repo truth, close with:
- code
- tests
- docs/changelog touch if operator truth changed
- topology statement
- push receipt

## Topology statement
- runtime/system topology: unchanged
- autonomy/governor/controller execution truth: changed only when blades land

## Recommendation
Run this as a `櫻花刀舞 non-stop` serial queue:
1. Blade A
2. Blade B
3. Blade C
4. Blade D
5. Blade E

Do not widen mutation-family scope before Blades A-C are green.
That would increase apparent autonomy while lowering safety truth.
