---
name: openclaw-mem-temporal-facts
description: >-
  Govern source-linked temporal facts in openclaw-mem. Use for current truth,
  timelines, stale detection, fact packs, and review-only fact extraction.
metadata:
  ring: 1
  surface: [cli]
  version: 2.0.0
  requires: [openclaw-mem-memory]
---

# Temporal Facts

Treat facts as a derived view over source evidence, not a new truth owner.

## Rules

- Require at least one resolvable source ref for every assertion.
- Keep assertion receipts separate from evidence refs.
- Use controlled predicates; unknown predicates fail lint.
- Supersede or invalidate overlapping single-valued facts.
- Treat stale facts as evidence unless stale inclusion is explicit.
- Keep extraction proposals review-only with `writes_performed=false`.

## Operate

```bash
openclaw-mem graph fact registry --json
openclaw-mem graph fact current --subject <subject> --source-root <workspace> --json
openclaw-mem graph fact timeline --subject <subject> --source-root <workspace> --json
openclaw-mem graph fact pack --subject <subject> --source-root <workspace> --json
openclaw-mem graph fact lint --source-root <workspace> --json
openclaw-mem graph fact stale --source-root <workspace> --json
```

For assertions, supply subject, predicate, object, validity time, source ref, assertion ref, and source root. Use `rebuild --allow-dangling-source` only for fixture or backfill inspection.

## Verify

```bash
openclaw-mem graph fact registry --json
python -m pytest tests/test_graph_facts.py -q
git diff --check
```
