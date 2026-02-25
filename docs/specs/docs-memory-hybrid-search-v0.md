# Docs memory (decisions/roadmaps/specs) — Hybrid search v0 (no local LLM)

Goal: make operator-authored repo docs (especially **DECISIONS**, roadmaps, and specs) **reliably retrievable without prompt-hints**, using **hybrid retrieval** (FTS/BM25 + embeddings) and auditable receipts.

This spec is intentionally *LLM-minimal*: **no local query-expansion models** and no local rerank models. If reranking is needed later, we use a **remote API** over a bounded candidate set.

---

## Problem

We frequently “do the right thing” operationally (write decisions, commit & push), but recall still fails:

- The agent’s memory backend often can’t retrieve a decision unless CK supplies a specific keyword.
- Pushing to git does **not** automatically mean it becomes searchable to the agent.
- Vector-only recall is brittle on:
  - dates / commit SHAs / paths
  - short identifiers / error codes
  - partial quotes

---

## Non-goals

- Running any local LLM (query expansion, rerank, summarization).
- Replacing OpenClaw’s canonical memory slot by default.
- Automatically treating *all* repo text as trusted (we will tag trust by source).

---

## Corpus (initial)

We treat these as the high-value “docs memory” sources:

1) `lyria-working-ledger/DECISIONS/**`
2) `lyria-working-ledger/REPORTS/captain-log/**`
3) `openclaw-async-coding-playbook` project docs:
   - `projects/**` (roadmaps/specs/TECH_NOTES)
   - `**/ROADMAP*.md`, `**/*SPEC*.md`, `**/*PRD*.md`, `**/TECH_NOTES/**`

Notes:
- We start narrow to keep index cost + risk low.
- Expand later via an explicit allowlist (paths/globs).

---

## Storage model (v0)

### SQLite ledger (sidecar)

Add a new modality to the sidecar DB:

- `docs_chunks` table (canonical chunk store)
- `docs_chunks_fts` (FTS5) for lexical search
- `docs_embeddings` (optional) for vector search

Chunk identity must be stable:

- `doc_id` = stable file identity (e.g., repo + relpath)
- `chunk_id` = stable within a file (e.g., heading anchor + ordinal)
- `recordRef` should be derivable (e.g., `doc:<repo>:<path>#<chunk_id>`)

### Embeddings provider

Use the configured OpenAI embeddings model (default: `text-embedding-3-small`).

Constraints:
- Embeddings are **optional**; v0 must work with FTS-only.
- Embedding failures are **fail-open** (do not break ingest/search).

---

## Chunking (v0)

- Prefer Markdown structure:
  - split on headings; keep short sections together up to a token/char cap
- Store both:
  - `text` (the chunk)
  - `title` / `heading_path` (context)
  - `path`, `repo`, `doc_kind` (decision/roadmap/spec/log)
  - `ts_hint` (best-effort parse of dates from filename/frontmatter)

Keep a strict upper bound per chunk (so retrieval snippets stay safe).

---

## Retrieval pipeline (v0)

### 1) Lexical retrieval (FTS/BM25)

- `docs_search_fts(query, top_k)` → candidates with bm25 rank.

### 2) Vector retrieval (optional)

- `docs_search_vec(query, top_k, model)` → candidates by cosine similarity.

### 3) Fusion

- Deterministic **RRF** fusion of the two ranked lists.
- Keep a bounded final candidate set (e.g., top 20).

### 4) Optional remote rerank (later)

If needed for quality, rerank only the fused top-N using a remote model.

---

## Trust & provenance

Default trust policy for this corpus:
- `DECISIONS/**` and operator-authored roadmaps/specs: `trusted`
- Anything imported from tools/web: `untrusted` unless explicitly promoted

All docs chunks must carry:
- `source_kind` (`operator|tool|web|import|system`)
- `source_ref` (repo/path at minimum)

---

## Receipts & trace (non-negotiable)

Every docs query should be debuggable.

A docs recall/pack trace should include:
- query text
- fts top-k (ids + scores)
- vec top-k (ids + scores)
- fused ranking (ids + score components)
- final selected chunks (bounded text + recordRef)

---

## Benchmark / measurable acceptance

Define a fixed query set (20–30) where each query has an expected target doc.

Metrics:
- Hit@5
- Hit@1
- Hint-rate (fraction needing follow-up keyword hints)

Acceptance:
- For decision-style queries (e.g., “neoapitest 現股當沖 status code”), Hit@5 should materially improve vs current.

---

## Slow-cook lanes (recommended)

Add a slow-cook lane to:
1) refresh docs index (incremental)
2) run the benchmark query set
3) emit a single aggregate receipt + top failure cases

Notify only on regression or when new high-importance missing-coverage cases appear.
