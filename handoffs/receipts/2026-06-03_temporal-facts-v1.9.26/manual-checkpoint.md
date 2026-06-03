# Manual checkpoint mirror

Timestamp: 2026-06-03 13:40 Asia/Taipei

This mirror exists because CK sent `/checkpoint` in Discord and the slash command reached the agent chat as text. A bounded recent scan did not find a native `.checkpoint.*.jsonl` receipt.

Primary checkpoint artifact:

`/root/.openclaw/workspace/handoffs/2026-06-03_openclaw-mem-temporal-facts-checkpoint.md`

## Checkpoint summary

- `openclaw-mem` temporal fact materialized view line is complete.
- Release commit: `ec2deea0b4975529ce7a7ea45c6a8d56ec4b36a3`
- Release tag: `v1.9.26` -> `ec2deea0b4975529ce7a7ea45c6a8d56ec4b36a3`
- Five-qi docs alignment commit: `a459369679552564464817953aa32011bf9f5088`
- Finale tag: `temporal-facts-grand-finale-2026-06-03` -> `a459369679552564464817953aa32011bf9f5088`
- Local CLI lane is active at `openclaw_mem = 1.9.26`.
- `openclaw-mem graph fact registry` returns `openclaw-mem.graph.fact.predicate-registry.v0` with 9 predicates.
- Topology unchanged: no Gateway config, cron topology, memory backend, prompt-injection path, model routing, runtime model, or external service topology changed.

## Ingest note

Direct docs cold-lane ingest of `/root/.openclaw/workspace/handoffs/...` was blocked by `source_roots_not_allowlisted`, so this allowlisted repo-local mirror is the searchable checkpoint receipt.
