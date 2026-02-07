# Dual-language memory strategy (original + optional English)

## Goal

Support multilingual memory (especially mixed Chinese/English) without forcing translation at write-time.

This strategy stores:
- original text (always)
- optional English companion text (when available or useful)

The objective is better recall reliability across language-mismatched queries while keeping ingestion predictable.

---

## Rationale

In mixed-language agent workflows, failures usually come from query/document language mismatch:
- memory stored in Chinese, query in English (or vice versa)
- technical terms preserved in English while surrounding context is Chinese
- inconsistent manual translation quality

Keeping both original + optional English improves recall coverage while preserving source fidelity.

---

## Architecture

Write path:
1. Client submits original memory text (`text`).
2. Client may also submit English text (`text_en`).
3. System stores both in the memory record.
4. Indexing can include one or both fields depending on retrieval mode (FTS/vector/semantic).

Read path:
1. Query arrives in original language (`query`) and optionally English (`query_en`).
2. Retrieval attempts primary query mode first.
3. If hits are weak/empty, fallback uses cross-language query path.
4. Results return canonical record with both language fields when present.

---

## Data fields (recommended)

Minimum dual-language fields per memory item:
- `text` (string, required): source/original text
- `text_en` (string, optional): English companion text
- `lang` (string, optional): detected/declared primary language (e.g., `zh`, `en`)
- `translation_source` (string, optional): `human`, `llm`, `none`
- `translation_status` (string, optional): `missing`, `draft`, `verified`

Operational metadata (recommended):
- `created_at`, `updated_at`
- `category`, `importance`
- `embedding_version` (if embeddings are used)

Notes:
- `text` remains the source of truth.
- `text_en` is an assistive retrieval field, not a replacement.

---

## Query flow

Recommended retrieval order for mixed zh/en usage:

1. **Primary-language query**
   - Run retrieval on `query` against main index.
2. **English-assisted query (if provided)**
   - Run retrieval on `query_en` against English-enabled index.
3. **Merge + deduplicate**
   - Combine candidates (stable ranking rule, e.g., weighted score or RRF).
4. **Threshold check**
   - If confidence below threshold, return low-confidence flag and top candidates.
5. **Record-level return**
   - Return full record including `text` and `text_en` when available.

---

## Fallback behavior

When one language side is missing:
- `text_en` missing: continue with `text`-only retrieval.
- `query_en` missing: continue with `query`-only retrieval.
- both present but poor match: fallback to broader recall (larger limit, relaxed threshold) before returning empty.

When translation quality is uncertain:
- prioritize exact/keyword matches from original language
- use English side as a recall booster, not authoritative truth

---

## Drawbacks and tradeoffs

1. **Storage overhead**
   - Dual text fields increase record size and index footprint.
2. **Write-time complexity**
   - Need optional translation generation/validation policy.
3. **Latency impact**
   - Cross-language fallback and multi-pass retrieval add query latency.
4. **Quality variance**
   - Machine-generated English can introduce semantic drift.
5. **Ranking complexity**
   - Multi-source candidate merge needs consistent scoring.

Mitigation:
- keep `text_en` optional
- add explicit status/source fields
- monitor KPIs and tune fallback thresholds

---

## Recommended default policy (mixed zh/en)

Default policy for production:

- **On write**
  - Always store original text in `text`.
  - Accept `text_en` when caller provides it.
  - If no `text_en`, do not block write.

- **On read**
  - Accept both `query` and optional `query_en`.
  - Execute single-language retrieval first.
  - Trigger cross-language fallback only when top score/hit count is below threshold.

- **On display**
  - Show original text first.
  - Show English companion only when available.

- **On governance**
  - Treat `text` as canonical.
  - Mark translation provenance and verification state.

This keeps the baseline simple while improving recall for cross-language prompts.

---

## KPIs (measurable)

Track at least weekly, split by query language (`zh`, `en`, `mixed`):

1. **Usage**
   - `% memories with text_en` = records with non-empty `text_en` / total records
   - `% queries with query_en` = queries with non-empty `query_en` / total queries

2. **Latency**
   - `p50`/`p95` recall latency (ms), with and without fallback
   - fallback-trigger rate = fallback queries / total queries

3. **Effectiveness**
   - top-k hit rate on labeled eval set (k=1,3,5)
   - cross-language recovery rate = failures in primary path recovered by fallback / primary-path failures

4. **Failure rate**
   - empty-result rate
   - low-confidence-result rate (below score threshold)
   - translation-mismatch incident rate (manual QA sample)

Suggested initial targets (first rollout window):
- fallback-trigger rate: < 30%
- p95 latency increase from fallback: < 40%
- cross-language recovery rate: > 25%
- empty-result rate reduction vs single-language baseline: > 15%

Adjust thresholds after collecting 1–2 weeks of production traces.
