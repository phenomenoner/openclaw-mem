# Self-model side-car skill — ops lane

Purpose: inspect, diff, govern, and selectively release the derived self-model side-car without promoting it into a second truth owner.

## What this lane is for
Use this lane when you need any of the following:
- current derived self snapshot for an agent/session/scope
- ranked attachment map (what the agent is gripping tightly)
- deterministic adjudication state review before you trust continuity claims
- bounded public-safe continuity summary for restrained external/operator-facing phrasing
- drift / migration comparison before prompt or model changes
- threat/tension scan for persona-prior dominance or conflicting stances
- governed weaken / rebind / retire receipts for stale or overconfident stances
- release-history inspection for replayable control-plane audit

## Hard boundary
- `openclaw-mem` remains memory-of-record.
- This side-car is derived, editable, and rebuildable.
- Do not market or describe outputs as consciousness, soul, or true ontological self.
- Do not write back into Store truth from this lane.

## Default CLI surface
```bash
uv run --python 3.13 -- python -m openclaw_mem continuity current --scope <scope> --session-id <session> --json
uv run --python 3.13 -- python -m openclaw_mem continuity attachment-map --snapshot <path> --json
uv run --python 3.13 -- python -m openclaw_mem continuity adjudication --snapshot <path> --json
uv run --python 3.13 -- python -m openclaw_mem continuity public-summary --snapshot <path> --json
uv run --python 3.13 -- python -m openclaw_mem continuity threat-feed --snapshot <path> --json
uv run --python 3.13 -- python -m openclaw_mem continuity diff --from <snapshot-a.json> --to <snapshot-b.json> --json
uv run --python 3.13 -- python -m openclaw_mem continuity release --stance <id> --reason <text> --mode weaken --factor 0.5 --json
uv run --python 3.13 -- python -m openclaw_mem continuity release --stance <id> --reason <text> --mode rebind --json
uv run --python 3.13 -- python -m openclaw_mem continuity release-history --scope <scope> --session-id <session> --stance <id> --json
uv run --python 3.13 -- python -m openclaw_mem continuity compare-migration \
  --baseline-persona-file baseline.json \
  --candidate-persona-file candidate.json \
  --scope <scope> --session-id <session> --json
uv run --python 3.13 -- python -m openclaw_mem continuity enable --cadence-seconds 300 --json
uv run --python 3.13 -- python -m openclaw_mem continuity status --json
uv run --python 3.13 -- python -m openclaw_mem continuity auto-run --scope <scope> --session-id <session> --cycles 1 --json
uv run --python 3.13 -- python -m openclaw_mem continuity disable --json
```

## Recommended operating pattern
1. Build `current` and persist it when you need an audit point.
2. Inspect `attachment-map` and `adjudication` before making release decisions.
3. Check `threat-feed` before claiming the model is stable.
4. Use `public-summary` only for restrained public-safe language, never as identity truth.
5. Use `release` only with a concrete operator reason, ideally scoped to the active scope/session.
6. Use `release-history` when you need to replay weaken -> rebind -> retire state transitions.
7. Use `compare-migration` before prompt/model/persona refreshes.
8. Enable the control plane only when you actually want autonomous receipts.
9. Rebuild `current` after release to verify the attachment actually loosened, recovered, or disappeared as expected.

## Inputs
- live `openclaw-mem` observations / episodic events DB
- optional observations JSONL / episodes JSONL files
- optional persona prior JSON (`roles`, `goals`, `refusals`, `style_commitments`, `stances`)
- side-car release receipts under the run dir

## Outputs
- current snapshot schema: `openclaw-mem.self-model.snapshot.v0`
- attachment map schema: `openclaw-mem.self-model.attachment-map.v0`
- adjudication report schema: `openclaw-mem.self-model.adjudication.v0`
- public summary schema: `openclaw-mem.self-model.public-summary.v0`
- threat feed schema: `openclaw-mem.self-model.threat-feed.v0`
- diff schema: `openclaw-mem.self-model.diff.v0`
- release receipt schema: `openclaw-mem.self-model.release-receipt.v0`
- release history schema: `openclaw-mem.self-model.release-history.v0`
- migration compare schema: `openclaw-mem.self-model.compare-migration.v0`

## Safety reminders
- Persona priors are hints, not sovereignty.
- If priors dominate evidence, surface that as a threat instead of pretending certainty.
- If evidence is thin, say the self-model is unstable rather than filling the gap with vibes.
