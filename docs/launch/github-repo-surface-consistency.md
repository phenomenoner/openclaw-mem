# GitHub repo surface consistency

Use this file as the durable spec for the GitHub-facing surfaces of `openclaw-mem`.

Scope note: maintainer-facing guidance in a public repo; it governs outward language but is not itself end-user product documentation.

## Goal

When someone encounters the repo through GitHub search, pinned repos, releases, or social previews, they should get the same first impression:

> `openclaw-mem` is about **trust-aware context packing** for OpenClaw.

Not generic memory storage. Not backend internals first. Not a universal graph-schema claim.

## Canonical messaging

### One-line description

**Trust-aware context packing for OpenClaw — pack only what the agent should trust.**

### Expanded line

Trust-aware context packing for OpenClaw — pack only what the agent should trust, with provenance, receipts, and local-first recall.

### Problem statement

Long-running agents do not just forget. They also admit stale, weak, or hostile context into future prompts. `openclaw-mem` narrows around that admission problem.

---

## Public repo messaging sequence

1. **Problem**: trustworthy memory behavior under long-running pressure.
2. **Approach**: trust-aware context packing with explicit trust tiers + receipts.
3. **Proof**: synthetic before/after artifact as the first deep link.
4. **Adoption path**: sidecar-first install path, optional mem-engine promotion.

Use this order in README / About / release body intros.

---

## GitHub About / repo description

### Final description

`Trust-aware context packing for OpenClaw — pack only what the agent should trust, with provenance, receipts, and local-first recall.`

### Homepage

Keep homepage pointed at docs root:
- `https://phenomenoner.github.io/openclaw-mem/`

Why:
- root page is the stable landing surface
- proof pages are better as strong links from README/docs, not the repo website URL itself

---

## Pinned repo note

Pinned repositories do not expose a separate custom blurb beyond repository description.

So the repo description is effectively pin text.

Current pin-safe line:

`Trust-aware context packing for OpenClaw — pack only what the agent should trust, with provenance, receipts, and local-first recall.`

Short fallback:

`Trust-aware context packing for OpenClaw.`

---

## Release tagline

### Short release tagline

**Trust-aware context packing for OpenClaw: smaller prompt packs, explicit trust tiers, and receipts for why memory entered the pack.**

### Slightly longer version

`openclaw-mem` now frames its core value around **trust-aware context packing**: building smaller, safer prompt packs with visible trust tiers, provenance, and receipts.

Use this line near the top of release notes when the release materially strengthens pack selection/provenance/citations/memory hygiene.

---

## Social preview spec

### Recommended headline

**Trust-aware context packing for OpenClaw**

### Recommended subhead

**Pack only what the agent should trust**

### Optional footer chips

- provenance
- receipts
- local-first recall

### What the image should imply visually

- before: noisy / larger / mixed-trust pack
- after: smaller / cleaner / trust-gated pack
- emphasis on selection, not storage volume

### Avoid on the social preview image

- too many flags / CLI snippets
- backend nouns as headline (`LanceDB`, `hybrid engine`, `SQLite sidecar`)
- giant explanatory walls of text

### Suggested alt-text / caption

`openclaw-mem: trust-aware context packing for OpenClaw — pack only what the agent should trust.`

---

## Proof links to pair with GitHub surfaces

Use these for second-click depth after the one-line pitch:

- Canonical proof: `docs/showcase/trust-aware-context-pack-proof.md`
- Proof metrics: `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`
- Companion demo: `docs/showcase/inside-out-demo.md`
- Copy pack: `docs/launch/trust-aware-context-pack-copy-pack.md`
- Operator checklist: `docs/launch/proof-first-relaunch-checklist.md`
- Release-surface proof pack: `docs/launch/release-surface-proof-pack-v0.md`

---

## Repository topics guidance

Keep topics aligned to positioning first, implementation second.

Preferred set:
- `openclaw`
- `openclaw-plugin`
- `agent-memory`
- `context-engineering`
- `prompt-packing`
- `provenance`
- `local-first`
- `memory-systems`
- `llmops`
- `observability`
- `sqlite`

Backend-specific topics like `vector-search`, `hybrid-search`, `embeddings`, `lancedb` are true, but should not dominate first impression unless discovery data proves they matter more.

## Boundary checks (must stay true)

- KOL/GTM lanes remain linked-but-separate (no authority merge in this spec).
- Query-plane default and action-plane write-gated framing remain explicit.
- Graph/reference/knowledge-graph messaging stays a flagship feature family, not an overclaimed universal schema.
- For publicly released materials, internal narrative and external narrative must remain clearly separated; do not publish internal framing formulas or backstage positioning language as outward-facing copy.
