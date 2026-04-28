# Working packet — Dream Lite apply + Dream Director phase 1

## Goal
Ship the first implementation slice for `dream-lite-apply-self-reflection-sidecar-v0` without enabling live mutation.

Phase target:
- Phase 0: schema/spec artifacts exist.
- Phase 1 / 1b: CLI dry-run planning surfaces exist for Dream Lite apply and Dream Director instruction candidates.
- No authority file or synthesis-card mutation.

## Product slice
Add a new CLI family:

```bash
openclaw-mem dream-lite apply plan --governor-packet <path> --out <receipt.json>
openclaw-mem dream-lite apply verify --receipt <receipt.json>
openclaw-mem dream-lite director observe --input <daily.json> --out <candidates.json>
openclaw-mem dream-lite director stage --candidates <candidates.json> --out <staged.json>
openclaw-mem dream-lite director checkpoint --staged <staged.json> --out <checkpoint.json>
```

Optional parser aliases may accept `--from-file` where existing repo style prefers it.

## Scope
### In
- Parser + command handlers.
- Deterministic JSON packet emitters.
- JSON-schema docs for:
  - `openclaw-mem.dream-lite.apply.v0`
  - `openclaw-mem.dream-director.instruction-candidate.v0`
- Unit tests for parser and fail-closed gates.
- Public docs + skill note updates.

### Out
- No `apply run` wet-run mutation.
- No background cron.
- No write to `SOUL.md`, `AGENTS.md`, `MEMORY.md`, or memory DB.
- No OpenClaw core dreaming integration.
- No remote services.

## Phase-1 surface delta
The full spec describes later `run`, `rollback`, `verify --since`, and `director apply` surfaces. This packet wires only plan-only / staged-only Phase 1 commands: `apply plan`, `apply verify --receipt`, `director observe`, `director stage`, and `director checkpoint`. Wet-run and authority apply are deferred.

## Schema decisions from second-brain review
- `target.before_hash = null` is legal in Phase 1 dry-run planning; the real hash gate starts in Phase 2 when card resolution is implemented.
- For `mode=dry_run` / `result=planned` and all aborted receipts, `snapshot_ref`, `rollback_ref`, and `sidecar_witness_ref` may be `null`. The verifier must branch by mode/result and must not require wet-run artifacts in Phase 1.
- Director observe accepts a JSON object with optional `kind=openclaw-mem.dream-director.observation-input.v0`; if omitted, it still emits a deterministic empty/stub candidate packet.
- `director stage` emits a JSON envelope `openclaw-mem.dream-director.staged-patch.v0`, not a raw unified diff.
- `director checkpoint` emits `openclaw-mem.dream-director.checkpoint.v0`.
- Deterministic tests use `--run-id` and `--now`.
- Phase 1 CLI does not embed or render the Dream Director prompt; the prompt frame lives in the spec only.
- Schemas live under `docs/specs/*.schema.json`.
- `writes_performed = 0` is required in Phase 1 output packets.

## Command behavior
### `dream-lite apply plan`
Input: governor packet JSON (`openclaw-mem.optimize.governor-review.v0`).

Select only candidates where:
- `decision == approved_for_apply`
- `recommended_action == refresh_card`
- `apply_lane == graph.synth.refresh`
- `target.recordRef` is present

If exactly one eligible candidate exists:
- emit receipt kind `openclaw-mem.dream-lite.apply.v0`
- mode `dry_run`
- result `planned`
- include packet refs, candidate id, target recordRef, `before_hash=null` in Phase 1, dry-run diff summary, `snapshot_ref=null`, `rollback_ref=null`, sidecar witness placeholder `missing`
- `writes_performed = 0`

If zero candidates:
- emit valid receipt with result `aborted`, blocked_reason `no_eligible_refresh_card_candidate`.
- if a `compile_new_card` item was otherwise approved, prefer blocked_reason `compile_new_card_not_apply_eligible_in_v0`.

If >1 candidate:
- emit valid receipt with result `aborted`, blocked_reason `max_candidates_per_run_exceeded`.

### `dream-lite apply verify`
Validate receipt shape and gates:
- kind is correct
- no writes were performed
- only `refresh_card` can be planned
- authority/safety surfaces are absent from target
- rollback/snapshot/checkpoint fields exist for planned receipts

### `dream-lite director observe`
Input: a small JSON packet containing summaries / refs. No LLM call in CLI v0.
Output deterministic instruction-candidate packet with empty/stub candidate arrays if no explicit proposals are supplied.

### `dream-lite director stage`
Convert candidate patches into a staged JSON envelope only if every candidate is `auto_draft` or has `checkpoint_required=true` for authority surfaces. Otherwise abort. Enforce `max_candidates_per_observe` and `max_patch_bytes`.

### `dream-lite director checkpoint`
Hash the staged JSON envelope and emit checkpoint metadata. It does not apply the patch.

## Safety invariants
- All v0 commands are zero-write to memory / authority files.
- Director prompt is represented as observation-frame text, not as a guardrail-bypass instruction.
- Authority-surface candidates require checkpoint metadata.
- `compile_new_card` is rejected even if governor packet says `approved_for_apply`.
- Output packets are deterministic enough for tests.

## Files likely touched
- `openclaw_mem/cli.py`
- `tests/test_dream_lite_apply.py`
- `docs/specs/dream-lite-apply-self-reflection-sidecar-v0.md`
- `docs/specs/dream-lite-apply-phase1-working-packet-v0.md`
- `docs/schemas/*.json` or `docs/specs/*.schema.json`
- `docs/agent-memory-skill.md`
- `skills/agent-memory-skill.global.md`
- `skills/agent-memory-skill.readonly.md`
- `mkdocs.yml`

## Verification
Minimum:
```bash
python3 -m unittest -q tests.test_dream_lite_apply
python3 -m unittest -q tests.test_cli tests.test_optimize_governor_review tests.test_dream_lite_apply
python3 -m openclaw_mem dream-lite apply plan --governor-packet /path/to/governor.json --json
python3 -m openclaw_mem dream-lite director observe --input /path/to/daily.json --json
```

Docs gate:
```bash
mkdocs build --strict
```
If local docs deps are missing, record dependency blocker and run syntax/markdown sanity instead.

## Commit / release posture
- Commit implementation + docs locally.
- Push to remote main only after tests pass.
- Tag only if the slice is install-enabled and public docs are coherent.
- Installation proof: run CLI from repo and, if package tooling permits, editable install smoke.
