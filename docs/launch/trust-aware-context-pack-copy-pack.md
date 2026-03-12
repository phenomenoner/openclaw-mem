# Trust-aware context pack copy pack

Use this file as the durable outward-facing copy source for `openclaw-mem`.

## Positioning spine

`openclaw-mem` is not trying to remember everything.
It is a **trust-aware context packing layer for OpenClaw** that keeps prompt packs smaller, keeps trust tiers visible, and gives operators receipts for why a memory was included, excluded, or left fail-open.

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

## Release-ready snippet

`openclaw-mem` is now positioned around **trust-aware context packing** instead of generic memory storage.

The point is simple: long-running agents do not just forget — they also admit stale, untrusted, or hostile context and quietly drag it into future prompts. `openclaw-mem` gives OpenClaw a local-first way to build **smaller, cited prompt packs** with **explicit trust tiers** and **trace receipts** for why something was included, excluded, or left fail-open. The canonical proof artifact shows the same query before/after trust policy: a quarantined row drops out, a trusted row takes its place, the pack gets smaller, and the receipts stay intact.

Proof:
- `docs/showcase/trust-aware-context-pack-proof.md`
- `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`

## Short release blurb

Trust-aware context packing for OpenClaw: smaller prompt packs, explicit trust tiers, and receipts for why memory entered the pack.

## X / thread-ready copy

### Single-post version

`openclaw-mem`'s wedge is now much cleaner:

**trust-aware context packing for OpenClaw**
- smaller prompt packs
- explicit trust tiers
- recordRef citations + trace receipts
- less chance that stale / hostile context quietly becomes durable memory

The proof artifact is the fun part: same query, same DB, different trust policy — the quarantined row drops out, a trusted row takes its place, and the bundle gets smaller.

### Thread version

1. Most “AI memory” products pitch storage.
   The nastier production problem is **admission**: stale, untrusted, or hostile content quietly makes it into future prompts.

2. `openclaw-mem` is narrowing hard around that problem:
   **trust-aware context packing for OpenClaw**.

3. The baseline is local-first and inspectable:
   SQLite + JSON receipts + `search → timeline → get → pack`.

4. The useful bit is the pack surface:
   `--trace`
   `--pack-trust-policy exclude_quarantined_fail_open`
   `policy_surface`
   `lifecycle_shadow`

5. Canonical proof:
   same query, same DB, same limit.
   Turn on trust policy and the quarantined row is excluded, a trusted row replaces it, and the pack shrinks.

6. That is the whole wedge:
   **smaller / safer prompt packs with receipts** — not “store everything and pray.”

## Demo-thread / one-pager script

### 30-second opener

`openclaw-mem` is about **trust-aware context packing**, not generic memory storage.
The problem is not only forgetting. It is letting stale or hostile text become durable memory and then quietly re-enter prompts later.

### 3-beat demo flow

1. **Show the ungated pack**
   - run the proof fixture without trust policy
   - point out that a quarantined row still enters the pack because it matches the query text

2. **Turn on trust policy**
   - rerun with `--pack-trust-policy exclude_quarantined_fail_open`
   - show that the quarantined row is now excluded with an explicit reason

3. **Close on receipts**
   - show `trace`, `trust_policy`, `policy_surface`, and `lifecycle_shadow`
   - emphasize that the system did not silently mutate memory; it changed **selection** and logged why

### Closing line

The product promise is not “more memory.”
It is **smaller, safer prompt packs with trust tiers and receipts**.

## Demo links to keep handy

- Proof doc: `docs/showcase/trust-aware-context-pack-proof.md`
- Metrics JSON: `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`
- Raw fixture: `docs/showcase/artifacts/trust-aware-context-pack.synthetic.jsonl`
- Companion demo: `docs/showcase/inside-out-demo.md`
