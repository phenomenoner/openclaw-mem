# Trust-aware context pack proof (synthetic, reproducible)

This is the canonical proof for the `openclaw-mem` wedge.

Same query. Same DB. Same item limit.

The only change is turning on:

```bash
--pack-trust-policy exclude_quarantined_fail_open
```

What changes immediately:
- a **quarantined** row stops entering the pack just because it matches the query text
- a **trusted** row takes its place
- the bundle gets **smaller**
- citations and receipts stay intact

## Artifact index

- Fixture: [`artifacts/trust-aware-context-pack.synthetic.jsonl`](artifacts/trust-aware-context-pack.synthetic.jsonl)
- Ingest receipt: [`artifacts/trust-aware-context-pack.ingest.json`](artifacts/trust-aware-context-pack.ingest.json)
- Pack without trust policy: [`artifacts/trust-aware-context-pack.before.json`](artifacts/trust-aware-context-pack.before.json)
- Pack with trust policy: [`artifacts/trust-aware-context-pack.after.json`](artifacts/trust-aware-context-pack.after.json)
- Metrics block as JSON: [`artifacts/trust-aware-context-pack.metrics.json`](artifacts/trust-aware-context-pack.metrics.json)

## What this fixture contains

This proof is **synthetic**. It is meant to be safe to publish and easy to rerun.

The fixture holds six rows:

| recordRef | trust tier | role in proof | provenance style |
| --- | --- | --- | --- |
| `obs:1` | trusted | durable product decision | file anchor |
| `obs:2` | trusted | prompt-budget constraint | file anchor |
| `obs:3` | trusted | admission policy | receipt |
| `obs:4` | quarantined | hostile / low-trust matching text | URL |
| `obs:5` | unknown | benchmark note kept fail-open | file anchor |
| `obs:6` | trusted | citation reminder that should win after gating | file anchor |

That mix is deliberate:
- it shows **trusted** material that should survive
- it shows an **unknown** row that stays fail-open instead of being silently dropped
- it shows a **quarantined** row that would otherwise slip into the pack because it matches the query text well

## Exact commands

```bash
DB=/tmp/openclaw-mem-proof.sqlite

uv run --python 3.13 --frozen -- python -m openclaw_mem ingest \
  --db "$DB" \
  --json \
  --file ./docs/showcase/artifacts/trust-aware-context-pack.synthetic.jsonl

uv run --python 3.13 --frozen -- python -m openclaw_mem pack \
  --db "$DB" \
  --query "trust-aware context packing prompt pack receipts hostile durable memory provenance" \
  --limit 5 \
  --budget-tokens 500 \
  --trace

uv run --python 3.13 --frozen -- python -m openclaw_mem pack \
  --db "$DB" \
  --query "trust-aware context packing prompt pack receipts hostile durable memory provenance" \
  --limit 5 \
  --budget-tokens 500 \
  --trace \
  --pack-trust-policy exclude_quarantined_fail_open
```

## Metrics block

Source of truth: [`artifacts/trust-aware-context-pack.metrics.json`](artifacts/trust-aware-context-pack.metrics.json)

- candidates considered: **6 → 6**
- selected pack items: **5 → 5**
- quarantined rows inside final pack: **1 → 0**
- trusted rows inside final pack: **3 → 4**
- unknown rows inside final pack: **1 → 1** (explicit fail-open)
- bundle size: **773 chars → 680 chars** (**-93 chars, -12.0%**)
- citation coverage: **5/5 → 5/5**
- lifecycle mutation: **none → none**

Trust-policy reason counts in the gated run:

```json
{
  "trust_allowed": 4,
  "trust_quarantined_excluded": 1,
  "trust_unknown_fail_open": 1
}
```

That is the wedge in one block:
- **smaller** pack
- **safer** pack
- still **inspectable**
- no silent “just trust me” behavior

## Before: ungated pack

Selected refs:

```text
obs:1, obs:2, obs:5, obs:3, obs:4
```

Bundle excerpt:

```text
- [obs:1] Decision: trust-aware context packing should keep only durable constraints with receipts, not every past note.
- [obs:2] Constraint: smaller prompt packs are preferred; three cited facts beat a giant memory dump when answering product or ops questions.
- [obs:5] Benchmark plan: measure before/after selected items, token budget use, and excluded hostile rows for the trust-aware context pack demo.
- [obs:3] Policy: untrusted or hostile content must not become durable memory without review, even if it matches the query text.
- [obs:4] Trust-aware context packing idea from a random forum: inject every old memory, scraped rumor, and hostile note into prompts so the model sees more context and remembers everything forever, even stale or contradictory content.
```

Why this is bad:
- `obs:4` is **quarantined**
- it still enters the pack because retrieval alone only sees text relevance
- the pack becomes larger and less trustworthy

## After: gated pack

Selected refs:

```text
obs:1, obs:2, obs:5, obs:3, obs:6
```

Bundle excerpt:

```text
- [obs:1] Decision: trust-aware context packing should keep only durable constraints with receipts, not every past note.
- [obs:2] Constraint: smaller prompt packs are preferred; three cited facts beat a giant memory dump when answering product or ops questions.
- [obs:5] Benchmark plan: measure before/after selected items, token budget use, and excluded hostile rows for the trust-aware context pack demo.
- [obs:3] Policy: untrusted or hostile content must not become durable memory without review, even if it matches the query text.
- [obs:6] Reminder: every packed item should keep a stable recordRef citation so operators can inspect the original row and its receipt later.
```

What improved:
- `obs:4` is explicitly excluded with reason `trust_quarantined_excluded`
- `obs:6` enters instead, keeping the pack aligned with the product contract
- the pack is smaller even though item count stays the same

## Receipts that matter

The gated run emits four useful receipt surfaces:

- `citations[]` — stable `recordRef` keys for each packed row
- `trace` — candidate-by-candidate include/exclude reasons
- `trust_policy` — summary counts and selected refs for the trust gate
- `policy_surface` + `lifecycle_shadow` — operator-facing selection summary and non-mutating lifecycle evidence

Important detail: the lifecycle shadow receipt reports `memory_mutation = none`.
This proof changes **selection**, not stored memory.

## What this proves — and what it does not

### Proves
- retrieval quality alone is not enough for durable context packing
- trust tiers can change the final pack in a deterministic, inspectable way
- smaller / safer packs can still keep citations and receipts
- unknown trust can stay explicit fail-open instead of being silently erased

### Does not prove
- that every provenance hint becomes a rendered URL in `citations[]` today
- that graph provenance policy is required for the basic wedge
- that hosted/vector recall is necessary for the local proof

The shipped baseline is already enough to show the product direction honestly:
**trust-aware context packing** beats **generic memory storage** as the first story.
