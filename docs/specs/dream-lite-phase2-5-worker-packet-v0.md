# Working packet — Dream Lite Phase 2→5 non-stop push

## Goal
Advance Dream Lite from Phase 1 plan-only to Phase 5 checkpoint-gated rehearsal without broad autonomy.

Ship bounded surfaces:
- Phase 2: wet-run canary for exactly one governor-approved `refresh_card` target.
- Phase 3: sidecar witness packet becomes a blocking gate for wet-run by default.
- Phase 4: explicit cohort caps / verifier window, still `refresh_card` only.
- Phase 5: Dream Director authority rehearsal can checkpoint and materialize a rehearsal patch/snapshot, but must not silently canonize authority files.

## Non-negotiable constraints
- `compile_new_card` remains proposal-only.
- Wet-run mutates only graph synthesis card state through existing `graph synth refresh` semantics: insert a replacement synthesis-card row and update the old row to `superseded`.
- Authority files (`SOUL.md`, `AGENTS.md`, `MEMORY.md`, tool/safety rules) are never changed without checkpoint, rollback artifact, and explicit `director rehearsal apply --allow-authority-rehearsal` style flag.
- No background cron in this slice.
- No OpenClaw core `/dreaming` integration.
- No prompt jailbreak wording in CLI; Director prompt remains spec/documentation only.

## Proposed CLI delta

### Dream Lite apply
```bash
openclaw-mem dream-lite apply run \
  --plan apply-plan.json \
  --witness witness.json \
  --run-dir ~/.openclaw/memory/openclaw-mem/dream-lite-apply \
  --json

openclaw-mem dream-lite apply rollback \
  --rollback rollback.json \
  --json

openclaw-mem dream-lite apply verify \
  --since 24h \
  --run-dir ~/.openclaw/memory/openclaw-mem/dream-lite-apply \
  --json
```

`run` behavior:
- input must be Phase-1 `openclaw-mem.dream-lite.apply.v0` receipt with `result=planned`, `mode=dry_run`, `writes_performed=0`, `recommended_action=refresh_card`, `governor_decision=approved_for_apply`, `apply_lane=graph.synth.refresh`.
- witness must be `openclaw-mem.self-reflection.dream-witness.v0` with `verdict=ok`, unless `--allow-missing-witness` is supplied. No default bypass.
- current target must exist and be a synthesis card.
- run recomputes the live `before_hash` from the current target row; if the plan has a non-null `target.before_hash`, it must match or abort.
- before snapshot must include source row summary + full detail JSON + hash.
- enforce plan TTL and rolling 24h write cap before mutation.
- call existing `_graph_synth_refresh_payload(...)` for mutation.
- write before / after / rollback receipts under run-dir.
- commit only if all gates pass.

`rollback` behavior:
- restore old synthesis card detail JSON / summary from rollback payload.
- refresh creates a replacement synthesis card; rollback must not hard-delete it. Mark the replacement card `graph_synthesis.status=rolled_back` and add lifecycle rollback metadata.
- emit rollback-applied receipt.

`verify --since` behavior:
- scan recent after/rollback receipts.
- verify every applied wet-run has before, after, rollback, witness ok, writes count, hash continuity.
- report status `pass|fail|inconclusive`.

### Self-reflection witness
Phase 3 minimum: deterministic witness file validator. It does not need a model writer yet.

Witness schema:
- kind: `openclaw-mem.self-reflection.dream-witness.v0`
- verdict: `ok|flagged|missing`
- coherence_risk: `low|medium|high|unknown`
- reasons[]
- apply_run_id or plan_run_id

Rules:
- `flagged` blocks.
- `missing` blocks unless explicit override.
- `coherence_risk=high` blocks even if verdict text is malformed/ok.

### Director rehearsal
```bash
openclaw-mem dream-lite director apply \
  --checkpoint checkpoint.json \
  --rehearsal-dir ~/.openclaw/memory/openclaw-mem/dream-director-rehearsal \
  --allow-authority-rehearsal \
  --json
```

Behavior:
- read checkpoint -> staged patch -> candidates.
- verify staged patch hash.
- if checkpoint_required and flag absent: abort.
- create full pre-change snapshots for target authority files if files exist.
- write a rehearsal artifact, not live canon by default.
- If we implement actual file edits in this slice, only allow patch operations with explicit `oldText/newText` and require exact match + rollback artifact. Phase 5 first cut is rehearsal materialization only, not live authority mutation. `--allow-authority-rehearsal` allows an authority rehearsal artifact; it never enables live authority-file mutation in this slice.

## Implementation slice recommendation
1. Add apply run/rollback/verify implementation with receipts and tests.
2. Add witness schema + validator tests.
3. Add director apply as **rehearsal materialization only**; no live authority edits yet.
4. Update docs/skills/roadmap from plan-only to Phase 5 bounded-rehearsal wording.
5. Version bump to next patch.

## Required tests
- apply run aborts missing/flagged/high-risk witness.
- apply run aborts tampered plan / wrong action / authority target / >1 candidate impossible.
- apply run refreshes a fixture stale synthesis card and writes before/after/rollback.
- rollback restores old card and marks new card rolled_back without hard delete.
- verify --since fails when rollback receipt missing and passes on complete fixture.
- director apply aborts checkpoint_required without flag.
- director apply detects staged hash mismatch.
- director apply writes rehearsal artifact and snapshots with `writes_performed=0` for live authority files.

## Stop-loss
If fixture creation for real graph synth refresh becomes the main work, ship `apply run` only, but it must still include receipt snapshots, witness gate, and rate cap. Do not ship a renamed `graph synth refresh` alias without canary receipts.
