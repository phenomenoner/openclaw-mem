# Remote positioning rework blade map — 2026-05-08

## Goal
Make the remote-facing `openclaw-mem` positioning clearer for GitHub visitors: README opening, product positioning, About page, package/GitHub description language, and evaluator path links should explain that this is not just another agent memory SDK, but a local-first memory governance layer / context supply chain for inspectable, cited, rollbackable agent context.

## Boundary
- In scope: public-facing wording and metadata that shape first impression.
- Out of scope: runtime behavior, CLI contract changes, release version bump, new feature claims not already supported by docs/proofs.

## Inputs
- Current README, PRODUCT_POSITIONING, docs/about, pyproject description, GitHub repo metadata if available.
- Market contrast: Mem0/Zep/Letta/Cognee/Supermemory are memory engines/frameworks; `openclaw-mem` should own governance/audit/pack/rollback positioning.

## Outputs / artifacts
- Patched docs/metadata.
- Independent editor and second-brain review receipts.
- Verifier output showing changed files, docs links sanity, package metadata parse, and final git diff summary.
- Commit + push to `origin/main` if checks pass.

## Invariants
- Do not claim hosted SaaS, benchmark leadership, or features not shipped.
- Keep Store / Pack / Observe as the stable product loop.
- Keep Advanced Labs opt-in and below the fold.
- Preserve local-first, plain artifact, citations/receipts/rollback proof standard.
- No topology/config/runtime impact.

## Verifier plan
- Dry-run: inspect docs and package metadata; check `pyproject.toml` parses.
- Counterfactual QA: scan for overclaim words and broken internal links in touched markdown.
- Human-readable report: this blade map + review receipts + final closure note.
- Live smoke: `git push origin main` and remote readback via `git ls-remote` / `gh repo view` if available.

## Rollback
- Revert the commit or restore from git diff before push. After push, use `git revert <commit>` if wording must be rolled back.

## Topology/config impact
Unchanged. Docs/metadata only.
