# Temporal Facts

Temporal facts are a source-linked materialized view over Store evidence.
They answer a narrow operator question:

> What is currently true about this subject, how did that truth change, and which receipts support it?

The view is derived and rebuildable. It is not a new memory owner, not a wiki as truth, and not hidden prompt stuffing.

```text
Store sources -> temporal fact view -> ContextPack output -> Observe receipts
```

## What ships in v0

- Controlled predicate registry: `owns`, `uses`, `depends_on`, `replaces`, `status`, `configured_as`, `decision`, `source_of_truth`, `retired_by`.
- Explicit assertions only. A fact without a resolvable source is rejected.
- Current-truth and timeline queries for one subject.
- Deterministic lint for dangling sources, unknown predicates, interval conflicts, stale sources, and over-confident source tiers.
- ContextPack-compatible fact packs with visible include/exclude trace.
- Review-only extraction proposals and fixture precision measurement. No extraction apply lane is enabled.

## CLI quickstart

Create a tiny sourced fact:

```bash
openclaw-mem --db /tmp/openclaw-facts.sqlite graph fact assert \
  --subject entity:openclaw-mem \
  --predicate source_of_truth \
  --object "Store records" \
  --valid-from 2026-06-03T00:00:00Z \
  --source-ref doc:docs/temporal-facts.md \
  --assertion-ref receipt:demo-temporal-facts \
  --source-root .
```

Read current truth:

```bash
openclaw-mem --db /tmp/openclaw-facts.sqlite graph fact current \
  --subject entity:openclaw-mem \
  --source-root .
```

Read the timeline:

```bash
openclaw-mem --db /tmp/openclaw-facts.sqlite graph fact timeline \
  --subject entity:openclaw-mem \
  --source-root .
```

Build a pack:

```bash
openclaw-mem --db /tmp/openclaw-facts.sqlite graph fact pack \
  --subject entity:openclaw-mem \
  --budget-tokens 1200 \
  --source-root .
```

Lint:

```bash
openclaw-mem --db /tmp/openclaw-facts.sqlite graph fact lint --source-root .
```

Check source drift:

```bash
openclaw-mem --db /tmp/openclaw-facts.sqlite graph fact stale --source-root .
```

## Supersession and invalidation

Single-valued predicates, such as `status` and `source_of_truth`, must not have overlapping active facts.
Use `--supersedes <fact_id>` when a new assertion replaces an older one:

```bash
openclaw-mem --db /tmp/openclaw-facts.sqlite graph fact assert \
  --subject entity:openclaw-mem \
  --predicate status \
  --object "implemented" \
  --valid-from 2026-06-04T00:00:00Z \
  --source-ref doc:docs/temporal-facts.md \
  --assertion-ref receipt:status-implemented \
  --supersedes fact_...
```

Use invalidation when the old fact should simply stop being current:

```bash
openclaw-mem --db /tmp/openclaw-facts.sqlite graph fact invalidate \
  --fact-id fact_... \
  --invalidated-at 2026-06-06T00:00:00Z \
  --source-ref doc:docs/temporal-facts.md \
  --assertion-ref receipt:status-invalidated
```

## Extraction assist stays review-only

The extractor is a pilot surface for measuring whether source text can propose useful fact drafts:

```bash
openclaw-mem graph fact propose \
  --text "entity:openclaw-mem source_of_truth Store records" \
  --source-ref doc:docs/temporal-facts.md
```

The output always has `writes_performed=false`.
Use fixture measurement before considering any future apply lane:

```bash
openclaw-mem graph fact measure-extraction \
  --corpus corpus.jsonl \
  --golden golden.jsonl
```

## Safety contract

- Store remains the durable evidence owner.
- Pack remains the context assembly owner.
- Observe remains the receipt and audit owner.
- Stale facts are excluded from current truth unless `--include-stale` is explicit.
- `graph fact route` emits a visible fact-pack receipt when the fact view is used.
- `graph fact rebuild --allow-dangling-source` is only a fixture/backfill escape hatch. Normal assertions still reject unresolved sources.
- No Gateway config, cron topology, memory backend, or prompt injection path is changed by this feature.
