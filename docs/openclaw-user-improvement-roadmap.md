# OpenClaw user improvement roadmap (product-facing)

This page is the **product-facing** roadmap for `openclaw-mem`.

It is written for **OpenClaw operators** (people who run agents in real work), not for contributors.

If you want the engineering-only backlog, see:
- `docs/roadmap.md`
- `docs/completeness-roadmap.md`

---

## Problem statement (operator view)

OpenClaw agents become dramatically more useful when they can:
- remember durable constraints (timezone, safety rules, “don’t touch cron payloads”),
- retrieve the *right* decisions quickly (without prompt gymnastics),
- avoid cross-project contamination,
- and explain *why* a memory was injected.

Today, `openclaw-mem` is **already useful**, but the UX still has friction:
- recall can be “relevant but not first”,
- scope isolation is present but not “hard enough” to eliminate bleed,
- lifecycle is still mostly manual (DB grows; signal decays),
- explainability exists (receipts) but needs to be more operator-legible.

---

## What we optimize for (product principles)

1) **Local-first, fail-open**
- If a quality layer fails (embeddings, rerank, provider), the agent loop must continue.

2) **Rollbackable posture**
- All “takes ownership of the memory slot” features are opt-in and one-line rollback.

3) **Governance over vibes**
- Retrieval and capture must be auditable: receipts, trace, provenance.

4) **Namespace hygiene**
- A user should be able to run multiple projects without memory bleed unless explicitly allowed.

---

## One killer demo flow (showcase-ready)

Goal: a reproducible 5-minute demo that shows **before/after** impact.

Recommended flow:
1) Run the synthetic “durable self” demo:
   - `docs/showcase/inside-out-demo.md`
   - `./scripts/inside_out_demo.sh`
2) Show that the packed bundle consistently enforces:
   - timezone preference,
   - privacy stance (synthetic demo),
   - output style (index-first / bounded reveal).
3) Turn on `--trace` (or receipt verbosity) and show *why* memories were selected.
4) (Optional) switch slot backend to `openclaw-mem-engine` and demonstrate hybrid recall receipts.

---

## Improvement list (ranked by OpenClaw user value)

### Progress update (current cycle)
- ✅ Scope hardening pass shipped (`skipFallbackOnInvalidScope` default-on + hardened scope-tag extraction).
- ✅ Receipt UX pass shipped (`whySummary` + `whyTheseIds` + explicit fallback suppression markers).
- ✅ Step4 wiring shipped behind canary flag (`workingSet.enabled`, deterministic synthesis + pinned injection + optional `working_set:<scope>` persistence). Current evaluation status: **frozen / default-off** because A/B review found no measured reply-quality lift over baseline recall.


### P0 — Immediate wins (days)

These should be high-impact and low-risk.

- **Harder scope isolation by default**
  - Make cross-project bleed difficult to happen accidentally.
  - Default: strict scope validation + explicit fallback markers.
  - Acceptance: two projects in parallel; recall stays in-scope unless the operator opts into fallback scopes.

- **Recall ranking that matches operator expectations**
  - Improve deterministic ranking so “the obvious memory” is returned first.
  - Candidate approach (still deterministic): split **retention** from **activation**; use quota-mixed hot recall (`must` cap + `nice` floor + wildcard) instead of letting `must_remember` fill the whole budget.
  - First cut: quota-based selection now has a small deterministic golden fixture; base rank-fusion remains unchanged, while fallback overflow selection can use the record timestamp only as a stable tie-break.
  - Spec: `docs/specs/auto-recall-activation-vs-retention-v1.md`
  - Acceptance: on a small golden set, top-1/top-3 improves without increasing noise, and large `must_remember` pools no longer wash out turn-relevant memories.

- **Explainability that answers the operator’s question**
  - Receipts already exist; make them *more legible* for humans.
  - Show: tier searched, why skipped, why included/excluded, which scope(s) were consulted.
  - Acceptance: when an operator asks “why did it recall that?”, the receipt answers it in one screen.

- **Make `Roadmap` + this page discoverable in the docs nav**
  - Operators should not need to grep the repo to find the product view.

### P1 — Make it feel “pro” (1–2 weeks)

- **Importance grading: operator workflow + drift checks**
  - Baseline exists (`heuristic-v1`); add lightweight operator review + drift receipts.
  - Acceptance: operators can spot-check must/ignore precision and correct mistakes quickly.

- **Lifecycle MVP (archive-first, reversible)**
  - Use-based decay: track `last_used_at` based on *actual inclusion* (e.g., pack trace), not “retrieved”. First opt-in cut refreshes `detail_json.lifecycle.last_used_at` / `used_count` only for final pack records and preserves `archived_at` without hard delete.
  - Soft-archive low-value records; reversible.
  - Acceptance: DB growth is bounded; must_remember remains stable.

- **Docs memory as a first-class recall surface**
  - Operators want: “we already decided this” retrieval.
  - Acceptance: decisions/specs are retrievable by keyword even with no embeddings.

### P2 — Showcase-grade experience (2–4 weeks)

- **Optional: wire `pack` as the default context feeder (guarded)**
  - Default OFF; canary first.
  - Acceptance: consistent, smaller prompts; fewer “context bloat” failures; receipts prove what was injected.

- **“Inside-Out Memory” demo → real operator template**
  - Provide a ready-to-run template that users can adapt:
    - a sample DECISIONS file,
    - a sample memory namespace scheme,
    - a “one-command demo” script.

---

## High-ROI modules that can be developed independently (single-worker friendly)

These are intentionally scoped so **one subagent** can ship them end-to-end (docs + tests + receipts), without requiring coordination across many modules.

1) **Receipt UX pass (operator legibility)**
- Improve receipt fields/names; add clear skip reason taxonomy; add “why these IDs” summary.
- Minimal risk; strong adoption impact.

2) **Deterministic recency boost / tie-break policy**
- Keep the system deterministic; add a simple, auditable ranking tweak.
- Add golden-set regression tests.

3) **Scope strictness + fallback marker hardening**
- Normalize/validate scope values; better failure modes; better default isolation.

4) **Lifecycle MVP (soft archive) with receipts**
- Add `last_used_at` updates from `pack --trace` inclusion.
- Add a daily job that archives only `ignore`/low-priority first.

5) **Docs nav + docs landing polish**
- Add “Start here” + “Killer demo” + “Product roadmap” in nav.
- Ensure the docs site tells a coherent story.

6) **Golden set for “operator invariants”**
- A small test corpus (synthetic) that asserts:
  - timezone preference always recalled,
  - scope isolation works,
  - receipts remain bounded.

7) **AutoCapture hardening pass (false positives / secrets)**
- Tighten secret filters and dedupe.
- Add unit tests against known bad captures.
- Latest shipped slice (2026-04-27): expanded deterministic secret signatures (`sk-proj`, `github_pat`, AWS secret-access-key assignments, long Bearer auth values) with regression checks that keep receipts/errors bounded and non-leaking.

---

## Evidence / provenance

This roadmap is grounded in:
- existing receipts from `openclaw-mem-engine` recall/capture lifecycle,
- real operator friction observed in day-to-day OpenClaw usage,
- and the reproducible Inside-Out demo contract.

Where we lack evidence (e.g., ranking changes), we will gate rollout behind:
- a small golden set,
- regression tests,
- and a canary window.
