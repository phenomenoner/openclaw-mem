# Verbatim semantic lane v0

Status: **DONE (v1.4.0 first production slice)**

This note records the bounded contract for the first shipped **verbatim semantic lane** inside `openclaw-mem`.

The feature exists to improve **episodic evidence recall** without disturbing the existing memory-role taxonomy.

---

## Core contract

The verbatim semantic lane is:
- a **retrieval lane**
- additive
- read-only
- scope-aware
- redaction-safe (inherits episodic substrate safety)
- evidence-oriented

It is **not**:
- a new memory type
- a durable write path
- a working-set source-of-truth
- a replacement for docs cold lane

---

## Why this slice exists

`openclaw-mem` is optimized around:
- governance
- receipts
- trust posture
- bounded context assembly

That gives it a stronger ops/control plane than many generic memory products.

But it also means raw conversation/project-style semantic retrieval is **not** the natural center of gravity.

This slice adds a narrow correction:
- semantically retrieve **raw episodic evidence**
- keep the rest of the system’s governance center intact

---

## Memory-role × retrieval-lane matrix

| memory role | canonical purpose | lexical / FTS | hybrid | verbatim semantic | dual-language assist | write-path note |
|---|---|---:|---:|---:|---:|---|
| durable (L1) | stable facts / preferences / decisions | yes | yes | evidence-only | yes | durable discipline stays unchanged |
| episodic | event/session trace / replay substrate | yes | yes | **yes** | limited query assist | no auto-promotion |
| working set | current activation / constraints / next actions | derived consumer | derived consumer | derived consumer | n/a | never index working set back into verbatim lane |
| docs cold lane | operator-authored docs / runbooks / specs | yes | yes | separate docs substrate | yes | docs flow remains independent |

Interpretation:
- episodic is the correct first corpus for verbatim semantic retrieval
- durable may cite the lane, but may not silently absorb it as truth
- working set may consume lane output, but is not a canonical corpus for the lane
- docs already have their own retrieval plane and stay separate in this slice

---

## Shipped CLI surfaces

### 1) Build / refresh episodic verbatim embeddings

```bash
openclaw-mem episodes embed \
  --scope openclaw-mem \
  --limit 200 \
  --json
```

Behavior:
- computes embeddings over `episodic_events.search_text`
- stores them in `episodic_event_embeddings`
- skips rows whose `search_text` hash already matches the stored embedding hash
- remains additive and local-first

### 2) Search episodic evidence

```bash
openclaw-mem episodes search "semantic recall" \
  --scope openclaw-mem \
  --mode hybrid \
  --trace \
  --json
```

Modes:
- `lexical` = existing FTS path
- `hybrid` = FTS + vector fusion via RRF
- `vector` = vector-only semantic probe

Receipts:
- `--trace` emits FTS/vector/fused ranking views
- response includes `vector_status` when vector/hybrid is requested

---

## Storage and migration posture

This first slice is intentionally small.

### Added table
- `episodic_event_embeddings`
  - `event_row_id`
  - `model`
  - `dim`
  - `vector`
  - `norm`
  - `search_text_hash`
  - `created_at`

### Why hash the search text?
Because the episodic search substrate can change after:
- redaction
- bounded payload updates
- ingest logic changes

The stored hash keeps embedding refresh deterministic and avoids trusting stale vector rows after the text changes.

### Non-goals in v0
- no episodic `text_en` storage column
- no docs-cold-lane schema rewrite
- no route-auto default behavior change
- no pack auto-injection change

---

## Dual-language positioning

Dual-language and verbatim semantic are **related but orthogonal**.

### Dual-language solves
- zh/en mismatch
- original-language vs English-query misses
- operator-provided English companion lookup

### Verbatim semantic solves
- semantic retrieval over raw episodic evidence
- finding the relevant session/turn cluster when lexical overlap is weak

Current v0 posture:
- keep episodic corpus canonical as the redacted `search_text`
- allow optional `--query-en` as a query-side assist
- defer any dedicated episodic `text_en` storage plane until a later slice proves the need

---

## Tradeoffs

### Gains
- better semantic recall over raw session evidence
- safer than turning all memory classes into one blended corpus
- auditable because the lane stays separate and traceable

### Costs
- embedding maintenance step (`episodes embed`)
- more candidate noise than strict lexical search
- vector freshness/model consistency now matter on episodic recall

### Guardrails
- bounded `search_limit`
- scope isolation preserved
- redaction-first substrate preserved
- no automatic durable writeback
- explicit trace surface available

---

## Rollout recommendation

1. Compare `episodes search --mode lexical` vs `--mode hybrid` on a fixed small query set.
2. Keep route/pack defaults unchanged until the lane shows consistent hit-quality gain.
3. Only after that, consider a later slice where:
   - route auto may optionally consult hybrid episodic search
   - working set may consume the lane as evidence
   - cross-language assist is deepened

---

## Verifier pack for this slice

Required proof points:
- parser coverage for `episodes embed` and `episodes search --mode ...`
- episodic embedding refresh works on changed `search_text`
- hybrid search returns grouped sessions with vector-lane receipts
- hybrid search fails open to lexical when embeddings are unavailable
- broader CLI/docs regressions remain green
