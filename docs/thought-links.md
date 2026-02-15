# Thought-links — Observational Memory × LongMemEval

This page connects two design/benchmark references to concrete constraints in `openclaw-mem`.

Sources (trusted by CK):
- Mastra — *Announcing Observational Memory*: <https://mastra.ai/blog/observational-memory>
- LongMemEval (ICLR 2025): <https://github.com/xiaowu0162/LongMemEval>

## 1) Observational Memory → design constraints we adopt

**What we take (pattern, not branding):**
- **Text-first derived memory layer**: a compact “observation log” that’s easy to diff/debug.
- **Stable two-block context**:
  1) OBSERVATIONS (stable prefix)
  2) RAW BUFFER (recent turns)
- **Scheduled compression** (observer) + **infrequent garbage-collection** (reflector).
- **Explicit priority levels** (“log levels”) to make governance obvious.

**Why it fits openclaw-mem:**
- We already treat memory as a *designed interface* (provenance + trust tiers + citations + receipts). A derived observation log can be another auditable artifact — not a magical hidden embedding blob.
- It aligns with local-first ops: deterministic storage + optional LLM assist.

**Non-negotiables (openclaw-mem flavor):**
- Derived artifacts must be reproducible and bounded.
- Compression must be **fail-open** (a bad compressor cannot break ingest/recall).
- Anything committed/shared must remain **redaction-safe** (aggregate-only receipts by default).

## 2) LongMemEval → benchmark strategy constraints we adopt

LongMemEval tests long-term interactive memory across categories that map well to our roadmap:
- **Information Extraction** → capture + recall stability
- **Multi-Session Reasoning** → context packing and cross-session continuity
- **Knowledge Updates** → overwrite / correction handling
- **Temporal Reasoning** → timestamps, “what was true when?”
- **Abstention** → don’t hallucinate when memory isn’t present

**What changes in our benchmarking because of this:**
- Report metrics **overall and by `question_type`** (category breakdown is not optional).
- Prefer ablation-style arms that isolate mechanisms:
  - importance-gated ingest (our current Phase A/B proxy)
  - observational compression (stable log text)
  - (later) live adapter chaining: openclaw-mem → memory backend

## 3) Concrete implementation hooks (where this lands)

- `docs/architecture.md`:
  - Context Packer includes an **observational-memory mode** variant (two-block window).
- `openclaw-memory-bench` (tooling repo):
  - retrieval reports should include **per-question-type breakdown**
  - the compare runner should support an **observational compression arm** (derived dataset) as a cheap, reproducible proxy.

## 4) What we deliberately do *not* claim (yet)

- We do not claim SoTA LongMemEval scores.
- We do not claim observational compression beats retrieval.
- We only claim what we can reproduce with artifacts (manifests + receipts + compare reports).

## 5) OpenClaw SuperMemory (SQLite FTS) → ops + safety takeaways

Source (external, medium trust; small repo, concept clear):
- `openclaw-supermemory`: <https://github.com/yedanyagamiai/openclaw-supermemory>

**What we take:**
- **Local-first lexical fallback**: SQLite + **FTS5/BM25** is a solid “zero-embedding / zero-provider” baseline for recall + debugging.
- **Strict config contract**: `additionalProperties: false` in plugin schema reduces silent misconfig during cron/long-run ops.
- **Anti-echo hygiene**: explicitly tag injected context blocks (e.g. `<supermemory-context>…</supermemory-context>`) and strip them during capture to avoid infinite self-ingest loops.
- **Ops-first tools**: a `memory_profile`-style command (counts, categories, size, recent) is disproportionately useful for diagnosing drift.

**What to watch:**
- Pure FTS is weaker for multilingual/semantic recall (esp. Chinese) unless tokenization is addressed.
- Auto-capture heuristics must be fail-open and deduped to prevent spammy memory growth.

**Actionable roadmap hooks for openclaw-mem:**
- Add a `profile`/stats surface (similar to our label-distribution receipts, but queryable on demand).
- Add an explicit injected-context marker + ignore-list in capture/harvest.
- Add an optional FTS5 lexical fallback lane for `--no-embed` runs.

## 6) QMD (hybrid local search engine) → retrieval router + benchmark hooks

Source (external; high concept clarity):
- `tobi/qmd`: <https://github.com/tobi/qmd>

**What it is (in one line):**
A local “docs-first” search engine for markdown/transcripts that does **FTS5/BM25 + vector + (optional) query expansion + LLM reranking**, with agent-friendly `--json/--files` outputs and an MCP surface.

**How it relates to us:**
- As a retrieval backend, QMD is best seen as an **alternative** to a pure vector store like `memory-lancedb`.
- As a system component, it can be a **supplement** to `openclaw-mem` (we still need capture/governance/receipts/importance; QMD doesn’t replace that).

**What we take (replicable modules):**
- **Hybrid candidate generation**: lexical anchors first (FTS/BM25), then semantic recall.
- **Fusion**: RRF-style merging is a pragmatic default.
- **Budgeting**: keep a small candidate set (top-N) before reranking.
- **Agent I/O contract**: stable JSON/file outputs + multi-get for “fetch the actual evidence”.

**Quality-first hybrid design we adopt (for openclaw-mem + memory backends):**
- Stage 1: QMD/FTS5 for exact anchors (names, APIs, error strings, dates)
- Stage 2: LanceDB vector search for paraphrase recall
- Stage 3: rerank **only when needed** (ambiguity/close scores) + cap budgets (`must` first, then `nice` with a cap)

**Benchmarking hooks (where this lands):**
- `openclaw-memory-bench`: add a QMD adapter and a “hybrid router” arm so we can compare:
  - QMD-only vs LanceDB-only vs Hybrid (QMD→LanceDB fallback)
  - metrics: hit/recall + p95 latency + must-coverage gate

**What to watch (risks):**
- Local GGUF model downloads + rerank latency can be heavy; quality-first is fine, but we need hard caps and a clear “disable rerank” path.
- “Docs-first” indexing is great for markdown, but we must ensure redaction-safe exports when sourcing from private session transcripts.

## 7) OpenViking (context database / filesystem paradigm) → observability + layered loading reference

Source (external; concept clarity high):
- `volcengine/OpenViking`: <https://github.com/volcengine/OpenViking>

**What it is (in one line):**
A “context database” for agents that models **resources + memory + skills** as a **virtual filesystem** (URI + directories), with **layered context loading (L0/L1/L2)** and **observable retrieval trajectories**.

**What we take (design patterns, not adoption commitment):**
- **Filesystem-as-context mental model**: context should be *browsable and targetable* (by scope/path), not just a flat embedding blob.
- **Layer contract (L0/L1/L2)**:
  - L0: ultra-short abstract for fast filtering
  - L1: overview + navigation ("how to get details")
  - L2: original detail, loaded only when necessary
- **Retrieval observability**: a first-class “trajectory/trace” for *why* something was retrieved (debuggable receipts).
- **Typed lanes**: distinguishing **Resource / Memory / Skill** as separate context types aligns with our governance goals.

**How it relates to openclaw-mem:**
- `openclaw-mem` remains the **governance/control-plane** (importance, trust tiers, redaction, receipts, packing policy).
- OpenViking is a strong reference for how to make context **structured, layered, and observable**.

**Scope note (CK decision):**
- Treat OpenViking as **thought-link only** for now (we are not committing to it as a backend/adapter arm yet).
