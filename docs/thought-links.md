# Thought-links — Observational Memory × LongMemEval

This page connects two design/benchmark references to concrete constraints in `openclaw-mem`.

Sources (trusted by CK):
- Mastra — *Announcing Observational Memory*: <https://mastra.ai/blog/observational-memory>
- LongMemEval (ICLR 2025): <https://github.com/xiaowu0162/LongMemEval>

Additional trusted references (for lifecycle/decay):
- Cepeda et al. (2006) — *Distributed Practice in Verbal Recall Tasks: A Review and Quantitative Synthesis* (Psychological Bulletin)
  - <https://doi.org/10.1037/0033-2909.132.3.354>
- Megiddo & Modha (2003) — *ARC: A Self-Tuning, Low Overhead Replacement Cache*
  - <https://www.usenix.org/legacy/publications/library/proceedings/fast03/tech/full_papers/megiddo/megiddo.pdf>
  (Used as an engineering analogy: retention should be driven by **recency + frequency**, not timestamps alone.)

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

## 8) Reference-based decay ("forgetting curve") → lifecycle governance hook

Key takeaway:
- Retention should be governed by **use** (recency/frequency), not a fixed “delete after N days since write” rule.

How this maps to openclaw-mem:
- Track `last_used_at` (ref) for durable records.
- Update ref only when a record is **actually used** (default: included in the final `pack` bundle with a citation), not when it’s merely preloaded.
- Apply **archive-first** lifecycle management (soft delete) so mistakes are reversible.

Trusted references:
- Cepeda et al. (2006) distributed practice / spaced repetition: <https://doi.org/10.1037/0033-2909.132.3.354>
- ARC cache replacement (engineering analogy: recency+frequency beats timestamps): <https://www.usenix.org/legacy/publications/library/proceedings/fast03/tech/full_papers/megiddo/megiddo.pdf>

Untrusted inspiration (idea source; treat as a field note):
- X thread (xiyu): <https://x.com/ohxiyu/status/2022924956594806821>

## 9) MCP Tool Search (Claude Code) → dynamic discovery + “Skill Card / Manual” split

Source (external; concept clarity high):
- 好豪：*MCP Tool Search：Claude Code 如何終結 Token 消耗大爆炸* <https://haosquare.com/mcp-tool-search-claude-code/>

**Core idea (portable pattern):**
- Don’t preload the whole “tool dictionary” (all schemas) into context.
- Keep a **small always-on core set**.
- Everything else is **discover → inspect → execute** (search first; load details only when needed).

**Why it matters to openclaw-mem (and our workflow design):**
- SOP/skills behave like *tools*: when the library grows, “stuff all SOPs into prompt” becomes a self-inflicted context bomb.
- This complements our layered-loading references (e.g., OpenViking L0/L1/L2):
  - **Skill Card = L0/L1** (tiny, searchable): when to use, outputs, risks, keywords.
  - **Skill Manual/Templates = L2** (heavy, deferred): step-by-step SOP, checklists, examples.

**Actionable roadmap hooks (candidates):**
- Add a **lexical index lane** (FTS5/BM25) for *skill cards / SOP cards* so agents can search first and only load the manual they need.
- Add a minimal “skill discovery” contract:
  - naming conventions (regex-friendly)
  - `keywords`/`anti-keywords`
  - explicit `outputs` + receipt rules
- Provide a small helper surface (CLI or adapter) that returns top-N card matches as JSON, then fetches the chosen manual on demand.

## 10) Trait / interface-first (systems kernel mindset) → contracts over vibes

Source (external; concept clarity high):
- `theonlyhennygod/zeroclaw`: <https://github.com/theonlyhennygod/zeroclaw>

**What we take (portable pattern):**
- Treat core subsystems (provider/channel/memory/tools) as **interfaces** with explicit contracts.
- Prefer **fail-fast** validation for configs and outputs (surface misconfig early).
- Keep operator surfaces **machine-readable** (stable JSON) so cron/receipts don’t depend on prompt parsing.

**How this maps to openclaw-mem:**
- “Memory governance” is our control-plane; backends remain swappable behind adapters.
- Roadmap candidates: strict config (`additionalProperties:false`), stable JSON schemas for receipts, and a `profile`/stats surface.

## 11) PAI (continuous learning + self-upgrade loop) → "learning records" as a first-class memory type

Source (external; concept clarity high):
- Daniel Miessler — *Personal AI Infrastructure (PAI)*: <https://github.com/danielmiessler/Personal_AI_Infrastructure>
  - v3.0 notes (self-upgrade loop, constraint extraction, drift prevention):
    <https://raw.githubusercontent.com/danielmiessler/Personal_AI_Infrastructure/main/Releases/v3.0/README.md>

**What we take (portable patterns, not code):**
- **Structured reflections** (not just free-form notes): mistakes → fixes → recurring themes.
- **Mining the loop outputs**: cluster repeated failure modes and turn them into targeted upgrades.
- **Constraint extraction + drift prevention**: treat “rules” as extractable artifacts and re-check them before/after producing outputs.

**How we go beyond it (openclaw-mem flavor):**
- **Governance-first**: every learning record gets provenance + trust tier + redaction rules by default.
- **Importance-aware learnings**: learning records can be auto-labeled (`must_remember`/`nice_to_have`/`ignore`) using our importance pipeline.
- **Receipts**: the learning loop must emit aggregate, diffable receipts (counts, top recurring error patterns, and what changed).

**Concrete integration plan (scope-safe):**
- Keep runtime hooks/handlers (e.g. `.learnings/` writing) *outside* openclaw-mem core.
- Add a **learning-record ingestion + query surface** inside openclaw-mem:
  - ingest `.learnings/{LEARNINGS,ERRORS,FEATURE_REQUESTS}.md` (or JSONL) into the warm SQLite ledger
  - make them searchable + packable with citations

**Risk to watch (and mitigation):**
- Infinite self-ingest loops (context blocks re-captured as learnings).
  - Mitigate with explicit injected-context markers + ignore-lists (see SuperMemory takeaways above).

## 12) Lossless Context Management (LCM) / lossless-claw → fresh-tail protection + provenance + “expand” tooling reference

Source (external; concept clarity high):
- `martian-engineering/lossless-claw`: <https://github.com/martian-engineering/lossless-claw>
- LCM paper: <https://voltropy.com/LCM>

**What it is (in one line):**
A pluggable context engine for OpenClaw that stores all session messages in SQLite, compacts via a **summary DAG**, and provides tools to **grep/describe/expand** compacted history.

**What we take (portable patterns):**
- **Protected “fresh tail”**: always keep the last N raw messages un-compacted for continuity.
- **Evictable prefix**: fill remaining budget with older summaries; drop oldest first.
- **Provenance by construction**: summaries link back to source messages; expansion is possible.
- **Ops safety belts**: best-effort compaction with deterministic fallback so the loop doesn’t stall.

**How it maps to openclaw-mem (without adopting an engine fork):**
- Our **Context Packer** can adopt the same *assembly policy* (fresh tail + evictable prefix) even if we don’t own compaction.
- We should treat a pack as a **hybrid text + JSON object** (stable anchors) with explicit provenance (`recordRef`) and trace receipts.

See also:
- `docs/context-pack.md` (ContextPack v1 direction)
- `docs/architecture.md` (Context Packer)
