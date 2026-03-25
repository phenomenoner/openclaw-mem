# Trust-aware context pack copy pack

Use this file as the durable outward-facing copy source for `openclaw-mem`.

## Positioning spine

`openclaw-mem` is not trying to remember everything.
It is a **trust-aware context packing layer for OpenClaw** that keeps prompt packs smaller, trust tiers visible, and receipts explicit for why a memory was included, excluded, or left fail-open.

## Narrative lock (dream → concept → demo → how-to)

### Dream
OpenClaw memory should stay trustworthy under pressure, not quietly import stale or hostile context.

### Concept
Trust-aware context packing: smaller cited packs, visible trust tiers, and inspectable selection receipts.

### Use case / demo
Run the synthetic before/after proof and show that a trust policy can exclude quarantined rows while keeping receipts intact.

### How-to
Adopt sidecar-first; promote to mem-engine only when hybrid recall/policy controls are needed.

## Claims guardrails

Keep these claims true:
- `pack` exists today
- `--trace` exists today
- `--pack-trust-policy exclude_quarantined_fail_open` exists today
- `policy_surface` and `lifecycle_shadow` receipts exist today
- the proof artifact is synthetic and reproducible
- graph provenance policy exists as a compatible extra surface, but it is not required for the basic proof

Avoid these claims:
- “solves memory forever”
- “fully blocks all bad memory automatically”
- “ships full provenance URLs for every citation today”
- “replaces all native OpenClaw memory by default”
- “graph/reference is the universal schema for everything”

Boundary rules for outward copy:
- KOL/GTM is linked but separately governed; never merge control-lane authority into product copy.
- Query-plane default and action-plane write-gated posture must remain explicit.

## Release-ready snippet

`openclaw-mem` is positioned around **trust-aware context packing**, not generic memory storage.

Long-running agents do not only forget. They also admit stale, untrusted, or hostile context and quietly drag it into future prompts. `openclaw-mem` gives OpenClaw a local-first way to build **smaller, cited prompt packs** with **explicit trust tiers** and **trace receipts** for inclusion/exclusion/fail-open decisions.

The canonical proof uses the same query against the same DB before/after trust policy: a quarantined row drops out, a trusted row takes its place, the pack gets smaller, and the receipts stay intact.

Proof:
- `docs/showcase/trust-aware-context-pack-proof.md`
- `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`

## Short release blurb

Trust-aware context packing for OpenClaw: smaller prompt packs, explicit trust tiers, and receipts for why memory entered the pack.

## GitHub-facing surfaces

### Repo description / pin-safe line

Trust-aware context packing for OpenClaw — pack only what the agent should trust, with provenance, receipts, and local-first recall.

### Ultra-short line

Trust-aware context packing for OpenClaw.

### Social preview headline

Trust-aware context packing for OpenClaw

### Social preview subhead

Pack only what the agent should trust

## X / thread-ready copy

### Single-post version

`openclaw-mem`'s wedge is now much cleaner:

**trust-aware context packing for OpenClaw**
- smaller prompt packs
- explicit trust tiers
- recordRef citations + trace receipts
- lower chance that stale / hostile context quietly re-enters future prompts

The proof artifact is the key: same query, same DB, different trust policy — quarantined row drops out, trusted row takes its place, bundle gets smaller.

### Thread version

1. Most “AI memory” products pitch storage.
   The nastier production problem is **admission**: stale, untrusted, or hostile content quietly enters future prompts.

2. `openclaw-mem` narrows around that:
   **trust-aware context packing for OpenClaw**.

3. Baseline is local-first and inspectable:
   SQLite + JSON receipts + `search → timeline → get → pack`.

4. The packing surface:
   `--trace`
   `--pack-trust-policy exclude_quarantined_fail_open`
   `policy_surface`
   `lifecycle_shadow`

5. Canonical proof:
   same query, same DB, same limit.
   Turn on trust policy and the quarantined row is excluded, a trusted row replaces it, and the pack shrinks.

6. Whole wedge:
   **smaller / safer prompt packs with receipts** — not “store everything and pray.”

## Demo-thread / one-pager script

### 30-second opener

`openclaw-mem` is about **trust-aware context packing**, not generic memory storage.
The problem is not only forgetting. It is letting stale or hostile text become durable memory and then quietly re-enter prompts later.

### 3-beat demo flow

1. **Show the ungated pack**
   - run the proof fixture without trust policy
   - point out that a quarantined row still enters the pack because it text-matches

2. **Turn on trust policy**
   - rerun with `--pack-trust-policy exclude_quarantined_fail_open`
   - show that the quarantined row is excluded with an explicit reason

3. **Close on receipts**
   - show `trace`, `trust_policy`, `policy_surface`, and `lifecycle_shadow`
   - emphasize selection changed with logs; memory was not silently mutated

### Closing line

The product promise is not “more memory.”
It is **smaller, safer prompt packs with trust tiers and receipts**.

## Demo links to keep handy

- Proof doc: `docs/showcase/trust-aware-context-pack-proof.md`
- Metrics JSON: `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`
- Raw fixture: `docs/showcase/artifacts/trust-aware-context-pack.synthetic.jsonl`
- Companion demo: `docs/showcase/inside-out-demo.md`
- Operator lock checklist: `docs/launch/proof-first-relaunch-checklist.md`
