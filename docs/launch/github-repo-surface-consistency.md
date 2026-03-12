# GitHub repo surface consistency

Use this file as the durable spec for the GitHub-facing surfaces of `openclaw-mem`.

## Goal

When someone encounters the repo through GitHub search, a pinned repo list, a release page, or a shared link preview, they should get the same first impression:

> `openclaw-mem` is about **trust-aware context packing** for OpenClaw.

Not generic memory storage. Not vector-search-first packaging. Not backend internals.

## Canonical message spine

### One-line wedge

**Trust-aware memory for OpenClaw — pack only what the agent should trust.**

### Expanded line

Trust-aware memory for OpenClaw — pack only what the agent should trust, with provenance, receipts, and local-first recall.

### Problem statement

Long-running agents do not just forget. They also admit stale, weak, or hostile context into future prompts. `openclaw-mem` narrows around that admission problem.

---

## GitHub About / repo description

### Final description

`Trust-aware memory for OpenClaw — pack only what the agent should trust, with provenance, receipts, and local-first recall.`

### Homepage

Keep homepage pointed at the docs root:
- `https://phenomenoner.github.io/openclaw-mem/`

Why:
- the root page is the stable landing surface
- proof pages are better as strong links from README/docs, not the repo website URL itself

---

## Pinned repo note

GitHub pinned repositories do not expose a separate custom blurb beyond the repository description.

That means the repo description itself is effectively the pin text.

Current pin-safe line:

`Trust-aware memory for OpenClaw — pack only what the agent should trust, with provenance, receipts, and local-first recall.`

If a shorter version is ever needed, use:

`Trust-aware context packing for OpenClaw.`

---

## Release tagline

### Short release tagline

**Trust-aware context packing for OpenClaw: smaller prompt packs, explicit trust tiers, and receipts for why memory entered the pack.**

### Slightly longer version

`openclaw-mem` now frames its core value around **trust-aware context packing**: building smaller, safer prompt packs with visible trust tiers, provenance, and receipts.

Use this line near the top of release notes when the release materially strengthens pack selection, provenance, citations, or memory hygiene.

---

## Social preview spec

GitHub social preview is best when it states the wedge in one glance.

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
- after: smaller / cleaner / gated pack
- emphasis on selection, not storage volume

### Avoid on the social preview image

- too many flags / CLI snippets
- backend nouns as the headline (`LanceDB`, `hybrid engine`, `SQLite sidecar`)
- giant walls of explanatory text

### Suggested alt-text / caption

`openclaw-mem: trust-aware context packing for OpenClaw — pack only what the agent should trust.`

---

## Proof links to pair with GitHub surfaces

Use these when you need a second click after the one-line pitch:

- Canonical proof: `docs/showcase/trust-aware-context-pack-proof.md`
- Proof metrics: `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`
- Companion demo: `docs/showcase/inside-out-demo.md`
- Copy pack: `docs/launch/trust-aware-context-pack-copy-pack.md`

---

## Topics posture

Keep topics aligned to positioning first, implementation second.

Current preferred set:
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

Backend-specific topics like `vector-search`, `hybrid-search`, `embeddings`, and `lancedb` are true, but should not dominate first impression unless search-discovery data proves they matter more.
