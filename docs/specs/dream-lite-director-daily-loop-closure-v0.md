# Dream Lite Director daily loop closure v0

Status: implementation spec / blade map
Date: 2026-04-29
Owner: Lyria / OpenClaw memory lane

## Verdict

Dream Lite currently has a working maintenance lane (`recommend -> governor -> apply plan -> verify`) and a working Director packaging lane (`director observe -> stage -> checkpoint -> apply rehearsal`), but the product loop is not closed:

- the daily Dream Lite controller does not invoke Director artifacts;
- `director observe` only normalizes supplied `proposals[]` and does not author opinions;
- therefore a daily run can truthfully say `no_action` while silently skipping the expected Director view.

This spec closes the observable loop without pretending deterministic cron can be creative: the daily controller must always emit a Director observation/opinion status surface. If no proposal author exists, that absence becomes an explicit artifact.

## Blade map

### Blade 1 — Observation surface
Create a deterministic `director-observation.json` inside each daily Dream Lite run directory.

Inputs:
- `recommend.json`
- `governor.json`
- `plan.json`
- `verify-window.json`
- optional counterfactual summary artifacts when present
- small authority/reference snapshots by path + sha256 only, not full file dumps

Output path:
- `.state/openclaw-mem/dream-lite-daily/<run-ts>/director-observation.json`

Required shape:
```json
{
  "kind": "openclaw-mem.dream-director.observation-input.v0",
  "observation_window": "daily:<run-ts>",
  "source_refs": ["recommend.json", "governor.json", "plan.json", "verify-window.json"],
  "scene_notes": [],
  "reinforce": [],
  "cross_out": [],
  "fill_in": [],
  "proposals": []
}
```

### Blade 2 — Deterministic gap opinion
Until a governed LLM/agent opinion author is installed, deterministic code should emit only safe operational opinions about the loop itself, not persona/authority edits.

If `proposals[]` is empty, write:
- `.state/openclaw-mem/dream-lite-daily/<run-ts>/director-missing-opinion.json`

Required fields:
```json
{
  "kind": "openclaw-mem.dream-director.missing-opinion.v0",
  "status": "missing",
  "reason": "missing_director_proposal_author",
  "daily_run_dir": "...",
  "observation_ref": ".../director-observation.json",
  "recommended_next": "install_governed_director_opinion_author",
  "writes_performed": 0,
  "policy": {
    "read_only": true,
    "memory_mutation": "none",
    "authority_mutation": "none"
  }
}
```

### Blade 3 — Director packaging chain
Run the existing Director chain against the observation input on every daily run:

```bash
openclaw-mem dream-lite director observe --input "$outdir/director-observation.json" --out "$outdir/director-candidates.json" --json
openclaw-mem dream-lite director stage --candidates "$outdir/director-candidates.json" --out "$outdir/director-staged.json" --json
openclaw-mem dream-lite director checkpoint --staged "$outdir/director-staged.json" --out "$outdir/director-checkpoint.json" --json
openclaw-mem dream-lite director apply --checkpoint "$outdir/director-checkpoint.json" --rehearsal-dir "$outdir/director-rehearsal" --json
```

The apply step remains rehearsal-only. It must not mutate authority or memory truth.

### Blade 4 — Alerting contract
Daily controller remains silent on ordinary no-op green runs, but it should emit `NEEDS_CK` when:

- Dream Lite verify fails;
- a refresh candidate is staged;
- Director stage/checkpoint/apply is blocked;
- Director opinion author is missing and `OPENCLAW_MEM_DREAM_DIRECTOR_REQUIRE_OPINION=1`;
- Director candidate count > 0 and the candidate touches authority/safety surfaces.

Default: do not alert only because the proposal author is missing. Record it as an artifact so the product loop is observable without creating daily noise.

### Blade 5 — Future opinion author seam
Add an explicit seam, but do not enable an LLM lane in deterministic cron by default:

- env: `OPENCLAW_MEM_DREAM_DIRECTOR_PROPOSAL_FILE`
- if set and readable, merge/validate its `proposals[]` into `director-observation.json` before calling Director observe;
- if unset, produce `director-missing-opinion.json`.

Future governed agent/LLM author can write that proposal file or can be scheduled as a separate `agentTurn` job. This keeps deterministic cron deterministic and makes the missing author visible.

## Configuration / env contract

Target controller path for this install: `/root/.openclaw/workspace/tools/dream_lite_daily.py` (runtime workspace tool invoked by `/root/.openclaw/workspace/tools/cron-runner/jobs/dream_lite_daily_0320.sh`). The `openclaw-mem` repo owns the product spec and CLI; the runtime controller is patched in the workspace tool lane.

Env vars:

- `OPENCLAW_MEM_DB` — SQLite DB path; default `/root/.openclaw/memory/openclaw-mem.sqlite`.
- `OPENCLAW_MEM_DREAM_LITE_RUN_DIR` — apply receipt verification dir; default `/root/.openclaw/memory/openclaw-mem/dream-lite-apply`.
- `OPENCLAW_MEM_DREAM_LITE_STATE_DIR` — daily artifact root; default `/root/.openclaw/workspace/.state/openclaw-mem/dream-lite-daily`.
- `OPENCLAW_MEM_DREAM_DIRECTOR_PROPOSAL_FILE` — optional proposal packet file. Default unset. If set, it is an untrusted local input and must pass the safety contract below.
- `OPENCLAW_MEM_DREAM_DIRECTOR_REQUIRE_OPINION` — when `1`, missing/invalid proposal author becomes `NEEDS_CK`; default unset/false.

Daily controller must never pass `--allow-authority-rehearsal`; authority/safety candidates remain blocked rehearsal evidence and require a separate explicit operator-controlled lane.

## Proposal-file safety contract

When `OPENCLAW_MEM_DREAM_DIRECTOR_PROPOSAL_FILE` is set:

- file must exist, be a regular file, and be no larger than 256 KiB;
- JSON must parse to an object with `proposals` as a list;
- maximum proposal count is 20;
- serialized `proposals[]` must be <= 40000 bytes;
- parse/schema/size failures must not crash the whole daily run; instead write `director-missing-opinion.json` with `reason=invalid_proposal_file` and emit `NEEDS_CK`;
- the controller still runs Director observe/stage/checkpoint/apply rehearsal against an observation with empty proposals, unless the failure prevents safe observation creation.

## Development plan

1. Patch `/root/.openclaw/workspace/tools/dream_lite_daily.py`:
   - add helper to write JSON artifacts;
   - add path+sha snapshot refs for `SOUL.md`, `AGENTS.md`, `MEMORY.md`, `TOOLS.md`, `USER.md`, and `IDENTITY.md` when present;
   - write `director-observation.json`;
   - optionally merge proposals from `OPENCLAW_MEM_DREAM_DIRECTOR_PROPOSAL_FILE`;
   - write `director-missing-opinion.json` when no proposals exist;
   - run Director observe/stage/checkpoint/apply rehearsal;
   - write all stdout payloads to named JSON files.
2. Add tests/smoke coverage:
   - daily run with no proposal file creates missing-opinion + empty Director artifacts;
   - daily run with proposal file creates candidate/staged/checkpoint/rehearsal artifacts;
   - no production memory mutation;
   - blocked Director stage/checkpoint surfaces `NEEDS_CK`.
3. Add docs update:
   - Dream Lite spec: daily loop now includes Director observability;
   - skill overlay: Dream Lite daily has a Director missing-opinion receipt until opinion author is installed.
4. WAL/receipt:
   - record topology: cron schedule unchanged, daily script behavior changed;
   - record config gates and default-off opinion author seam.

## Counterfactual verification matrix after implementation

All artifacts below must be produced under a scratch run dir, preferably:
`.state/openclaw-mem/dream-lite-counterfactual/<ts>/daily-run/`

### CF-1: Current real data, no proposal author
Command:
```bash
OPENCLAW_MEM_DREAM_LITE_STATE_DIR=<scratch> python3 tools/dream_lite_daily.py
```
Expected artifacts:
- `recommend.json`
- `governor.json`
- `plan.json`
- `verify-window.json`
- `director-observation.json`
- `director-missing-opinion.json`
- `director-candidates.json`
- `director-staged.json`
- `director-checkpoint.json`
- `director-apply.json`
- `director-rehearsal/*.rehearsal.json`
- `director-opinion.md` (render-only human readout derived from existing JSON artifacts)
- `daily-summary.json`

Expected facts:
- `plan.result = aborted` when current data still has no eligible refresh candidate;
- `director-missing-opinion.reason = missing_director_proposal_author`;
- `director-candidates.candidates = []`;
- `director-staged.patches = []`;
- `director-checkpoint.live_mutation = false`;
- `director-apply.writes_performed = 0`;
- `daily-summary.json.stages.director_missing_opinion.status = missing`;
- `director-opinion.md` states the missing-opinion reason and source artifact relationship;
- process output remains `NO_REPLY` unless stricter env requires opinion.

### CF-2: Current real data + synthetic proposal file
Input proposal file:
```json
{
  "proposals": [
    {
      "candidate_id": "semantic-delta-gate-for-aggressive-dreaming",
      "risk_class": "journal_only",
      "apply_lane": "auto_draft",
      "scene_notes": ["Aggressive force-refresh created lifecycle churn without semantic delta."],
      "reinforce": ["Require semantic delta before wet memory mutation."],
      "cross_out": ["Do not count lifecycle-only refresh as useful Dreaming output."],
      "fill_in": ["Install a governed Director opinion author."],
      "candidate_patches": [
        {"path": "notes/dream-director-opinion-loop.md", "op": "note", "text": "Daily Director opinion loop should emit semantic-delta judgments."}
      ],
      "rationale_refs": ["plan.json", "verify-window.json"]
    }
  ]
}
```
Expected artifacts:
- all CF-1 artifacts except `director-missing-opinion.json`, which must be absent;
- `director-candidates.candidates[0].candidate_id = semantic-delta-gate-for-aggressive-dreaming`;
- `director-staged.candidate_count = 1`;
- `director-staged.patches[0].path = notes/dream-director-opinion-loop.md`;
- `director-checkpoint.live_mutation = false`;
- `director-apply.live_mutation = false`;
- `director-opinion.md` renders the candidate's scene notes / reinforce / cross out / fill in / patch fields without adding new claims;
- process output remains `NO_REPLY` unless configured to alert on any Director candidate.

### CF-3: Strict mode no proposal author
Env:
```bash
OPENCLAW_MEM_DREAM_DIRECTOR_REQUIRE_OPINION=1
```
Expected:
- artifacts same as CF-1;
- stdout contains `NEEDS_CK: dream-lite director opinion missing artifact=<.../director-missing-opinion.json>`.

### CF-4: Authority-surface proposal
Proposal patch path: `AGENTS.md` or `MEMORY.md`.
Expected:
- `director-candidates.checkpoint_required = true`;
- `director-staged.checkpoint_required = true`;
- `director-checkpoint.live_mutation = false`;
- `director-apply.blocked_reasons` contains `authority_rehearsal_requires_explicit_flag`;
- `director-apply.live_mutation = false`;
- stdout contains `NEEDS_CK: dream-lite director authority candidate staged artifact=<.../director-checkpoint.json>`.

### CF-5: Regression of previous Dream Lite behavior
Expected:
- existing `recommend/governor/plan/verify` artifacts unchanged in schema and decision;
- no wet `dream-lite apply run` is invoked by daily controller;
- no SQLite production memory writes occur in default daily run.



### CF-6: Malformed proposal file
Env:
```bash
OPENCLAW_MEM_DREAM_DIRECTOR_PROPOSAL_FILE=<bad-json-or-too-large-file>
```
Expected:
- `director-missing-opinion.reason = invalid_proposal_file`;
- `daily-summary.json.needs_ck = true`;
- stdout contains `NEEDS_CK: dream-lite director proposal file invalid artifact=<.../director-missing-opinion.json>`;
- process does not mutate memory or authority truth.

### CF-7: Explicit empty proposal file
Input: `{"proposals": []}`.
Expected:
- same missing-opinion behavior as CF-1 with `reason=missing_director_proposal_author`;
- no Director candidate patches.

## Known fail-loud edge

If an upstream CLI command exits non-zero before producing JSON (`recommend`, `governor`, `plan`, `verify`, or any Director stage), the controller exits with `ERROR: ...` and may not write `daily-summary.json` for that run. Current `openclaw-mem` Dream Lite commands normally encode blocked states as JSON, so this is acceptable for v0; future hardening may add a pre-summary failure receipt.

## Acceptance gates

- Unit/smoke tests pass.
- `python3 tools/dream_lite_daily.py` produces the full artifact family in a scratch state dir.
- Current no-candidate state is no longer silent internally: it has explicit Director missing-opinion artifacts.
- No external writes, no authority mutation, no memory truth mutation.
- Existing cron schedule remains unchanged unless CK explicitly approves config changes.
- Daily controller never passes `--allow-authority-rehearsal`.
- Proposal file reads enforce the 256 KiB / 20 proposal / 40000-byte serialized proposal caps.
- `daily-summary.json` aggregates all stage refs/status and `needs_ck` truth, including `stages.director_opinion.ref`.

## Rollback

- Revert `tools/dream_lite_daily.py` changes.
- Remove only scratch `.state/openclaw-mem/dream-lite-*` test artifacts if needed.
- Cron topology does not need rollback if schedule remains unchanged.
