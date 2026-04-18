# Self-model side-car skill — ops lane

Purpose: inspect, diff, govern, and selectively release the derived self-model side-car without promoting it into a second truth owner.

## What this lane is for
Use this lane when you need any of the following:
- current derived self snapshot for an agent/session/scope
- ranked attachment map (what the agent is gripping tightly)
- drift / migration comparison before prompt or model changes
- threat/tension scan for persona-prior dominance or conflicting stances
- governed weakening/retirement receipts for stale stances

## Hard boundary
- `openclaw-mem` remains memory-of-record.
- This side-car is derived, editable, and rebuildable.
- Do not market or describe outputs as consciousness, soul, or true ontological self.
- Do not write back into Store truth from this lane.

## Default CLI surface
```bash
openclaw-mem continuity current --scope <scope> --session-id <session> --json
openclaw-mem continuity attachment-map --snapshot <path> --json
openclaw-mem continuity threat-feed --snapshot <path> --json
openclaw-mem continuity diff --from <snapshot-a.json> --to <snapshot-b.json> --json
openclaw-mem continuity release --stance <id> --reason <text> --mode weaken --factor 0.5 --json
openclaw-mem continuity compare-migration \
  --baseline-persona-file baseline.json \
  --candidate-persona-file candidate.json \
  --scope <scope> --session-id <session> --json
openclaw-mem continuity enable --cadence-seconds 300 --json
openclaw-mem continuity status --json
openclaw-mem continuity auto-run --scope <scope> --session-id <session> --cycles 1 --json
openclaw-mem continuity disable --json
```

## Recommended operating pattern
1. Build `current` and persist it when you need an audit point.
2. Inspect `attachment-map` before making release decisions.
3. Check `threat-feed` before claiming the model is stable.
4. Use `release` only with a concrete operator reason, ideally scoped to the active scope/session.
5. Use `compare-migration` before prompt/model/persona refreshes.
6. Enable the control plane only when you actually want autonomous receipts.
7. Rebuild `current` after release to verify the attachment actually loosened.

## Inputs
- live `openclaw-mem` observations / episodic events DB
- optional observations JSONL / episodes JSONL files
- optional persona prior JSON (`roles`, `goals`, `refusals`, `style_commitments`, `stances`)
- side-car release receipts under the run dir

## Outputs
- current snapshot schema: `openclaw-mem.self-model.snapshot.v0`
- attachment map schema: `openclaw-mem.self-model.attachment-map.v0`
- threat feed schema: `openclaw-mem.self-model.threat-feed.v0`
- diff schema: `openclaw-mem.self-model.diff.v0`
- release receipt schema: `openclaw-mem.self-model.release-receipt.v0`
- migration compare schema: `openclaw-mem.self-model.compare-migration.v0`

## Safety reminders
- Persona priors are hints, not sovereignty.
- If priors dominate evidence, surface that as a threat instead of pretending certainty.
- If evidence is thin, say the self-model is unstable rather than filling the gap with vibes.
