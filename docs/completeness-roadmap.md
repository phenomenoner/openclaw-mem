# Completeness roadmap (vs memory-lancedb-pro)

Goal: keep `openclaw-mem` **comparable in completeness** to `win4r/memory-lancedb-pro` at the level of *operator-facing* capabilities (not necessarily identical UI).

Reference project: <https://github.com/win4r/memory-lancedb-pro>

## Current baseline (shipped)
- ✅ Hybrid recall (FTS + vector) in `openclaw-mem-engine`
- ✅ Scope-aware filtering + policy tiers (must → nice → optional unknown)
- ✅ M1 automation:
  - ✅ autoRecall (conservative, skip trivial prompts, capped, escaped)
  - ✅ autoCapture (strict allowlist, secret-skip, dedupe, capped)
- ✅ Deterministic, rollbackable ops posture (slot switch + per-feature disable)

## Gap backlog (fill-in plan)

### P0 — Operator parity (must be comparable)
1) ✅ **Admin surfaces (comparable)**
   - Shipped in `openclaw-mem-engine`:
     - list memories (scope/category/limit filters)
     - stats (counts by scope/category + size/age summaries)
     - export (sanitized deterministic JSONL/JSON)
     - import (append + dedupe + dry-run)
   - Surfaces:
     - tool API: `memory_list`, `memory_stats`, `memory_export`, `memory_import`
     - CLI: `openclaw memory <list|stats|export|import>` when plugin CLI is loaded
     - fallback namespace: `openclaw ltm <list|stats|export|import>`
   - Acceptance met: operator can audit counts by scope/category and export a sanitized snapshot with receipts.

2) **Receipts/debug transparency for recall**
   - Expose (configurable): ftsTop / vecTop / fusedTop summaries (no secrets)
   - Acceptance: when recall happens, we can explain *why* an item was pulled

3) **Namespace & scope hygiene**
   - Ensure safe defaults: project isolation, explicit scope tags, no cross-project bleed
   - Acceptance: same user runs 2 projects; recall doesn’t cross unless explicitly allowed

### P1 — Quality parity (makes it feel “pro”)
4) **Fusion/ranking improvements (still deterministic)**
   - Calibrate hybrid fusion weights; add optional recency boost
   - Acceptance: recall quality improves on benchmark + no large regressions

5) **Retention/TTL policy (opt-in)**
   - Optional TTL/decay for low-importance captures
   - Acceptance: DB growth bounded without losing must_remember

6) **Safety hardening**
   - Stronger secret detector + PII heuristics; capture redaction rules
   - Acceptance: no obvious secrets captured in test corpus

### P2 — UX/Website completeness (nice, but helps adoption)
7) **Docs polish (README/About/website)**
   - One killer demo flow, before/after, architecture diagram

8) **Operator runbooks**
   - Upgrade, rollback, incident playbook, troubleshooting

## Execution protocol
- We fill this backlog via **single-agent hacking mode** runs (one worker), each run:
  - updates docs (what changed + how to verify)
  - ships code + tests
  - logs Decision/Tech Note if it changes ops posture

## Next slice (recommended)
P0-1 → P0-2 → P0-3.
