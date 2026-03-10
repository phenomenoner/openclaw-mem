# Topology auto-extract (repo map → topology seed) v0

Status: **spec stub** (roadmap item; not implemented).
Update 2026-03-10: openclaw-mem graph topology-extract is implemented in CLI, including default --spec-dir fallback to <workspace>/openclaw-async-coding-playbook/cron/jobs.

Purpose: move L3 topology from “curated/demo-first” to a system that can **discover and refresh** a minimal repo/system map deterministically.

Non-goals:
- No LLM-based extraction.
- No parsing of file contents/code semantics.
- No silent overwrites of operator-authored topology.

---

## Inputs (deterministic sources)

v0 sources (host-local):
1) **Workspace repo roots**
   - detect git repos under a provided root (e.g. `/root/.openclaw/workspace`)
   - capture metadata only: `{path, git_remote?, default_branch?, last_commit_ts?}`
2) **OpenClaw cron registry**
   - `/root/.openclaw/cron/jobs.json`
   - extract: jobId, enabled, schedule, sessionTarget, delivery
3) **Playbook cron specs (optional)**
   - `openclaw-async-coding-playbook/cron/jobs/*.md`
   - treat as “operator-authored provenance” for: commands/scripts/artifacts

## Output (seed topology file)

A small seed file (YAML or JSON) with:
- `nodes[]` (repos, cron jobs, artifacts, scripts)
- `edges[]` (job → script, job → repo, job → artifact)
- provenance for each edge (file/line or source kind)

Safety constraints:
- no secrets
- no raw log bodies
- no code snippets

## CLI surface (v0)

- `openclaw-mem graph topology-extract --workspace <path> --cron-jobs <jobs.json> --out <seed.yaml> --json`
  - emits a receipt with counts + provenance groups
- `openclaw-mem graph topology-diff --seed <seed.yaml> --curated <topology.yaml>`
  - suggest-only diff (never auto-apply)

## Promotion rule (seed → curated)

- Seed is **reference only**.
- Curated topology remains source-of-truth.
- Promotion is a human review step (PR / manual edit) with receipts.

## Acceptance criteria (v0)

- Running extract twice with no underlying changes yields identical output.
- Output is small enough to pack as L3 (bounded subgraph).
- A drift check can detect newly added cron jobs or repos missing from curated topology.
