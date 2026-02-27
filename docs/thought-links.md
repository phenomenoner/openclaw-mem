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

## 6) Zvec (Alibaba Proxima) → embedded vector engine candidate (future watch)

Source (external, medium trust):
- `alibaba/zvec`: <https://github.com/alibaba/zvec>

**Why it’s interesting:**
- **In-process vector DB** (no separate server) matches our local-first, owner-operated bias.
- Mentions **dense + sparse + hybrid search + filters**, which lines up with our “hybrid retrieval” direction.
- Apache-2.0.

**Caveats / why it’s not an immediate dependency:**
- Python support is advertised as **3.10–3.12**; our stack is moving on **Python 3.13 + uv**, so we’d need either a compatibility plan or isolate it behind an adapter.
- Platform/packaging constraints likely matter more than raw speed for our use.

**How we might use it later (if at all):**
- As an optional backend behind a stable adapter interface (so swapping engines is cheap).
- As a performance baseline to compare against LanceDB/FAISS/etc. in `openclaw-memory-bench`.

## 7) “Skill as a book” (progressive disclosure) → pilot surface: Diary/Meeting Refinery

Source (external, high-level idea): CabLate Agent Skill talk notes (skills as 3 layers).

**What we take:**
- Skills should be designed as **progressive disclosure**:
  1) router metadata (name/description)
  2) workflow body (principles + stable steps)
  3) appendices/tools (scripts/templates)
- This keeps the **default context lean**, while allowing deterministic reliability via scripts when needed.

**Where this lands (current pilot):**
- Decision: `lyria-working-ledger/DECISIONS/2026-02-18.md`
- Pilot contract: `openclaw-async-coding-playbook/projects/openclaw-mem/TECH_NOTES/2026-02-18_refinery_pilot_diary_meeting_extraction.md`

**Why we pilot on diary/meeting notes:** high value density (decisions/people/money/tasks), stable schema, and measurable noise reduction without risky always-on capture.

## 8) memory-lancedb-pro → hybrid retrieval “kitchen sink” (feature scout)

Source (external, medium trust; not audited):
- `win4r/memory-lancedb-pro`: <https://github.com/win4r/memory-lancedb-pro>

### What it is (in one line)
A drop-in replacement for OpenClaw’s built-in `memory-lancedb` that adds **BM25 FTS + hybrid fusion + cross-encoder rerank + multi-scope isolation + management CLI**.

### Wedge / positioning (what it optimizes for)
- **Retrieval quality + ops tooling** inside a single memory plugin.
- It’s deliberately “feature-rich memory backend”, not a sidecar governance layer.

### Killer demo flow (we can steal)
1) Store a few similar memories (some noisy, some important).
2) Show **vector-only** misses keyword-ish queries (names/paths/ids).
3) Turn on **hybrid (vector+BM25)** → results immediately improve.
4) Turn on **rerank + recency + MMR** → top-3 becomes cleaner, less duplicate.
5) Show `memory stats` / `export` / `reembed` as an operator loop.

### Before/after metrics we can actually claim (today)
- The repo itself mostly lists features; it doesn’t ship a reproducible benchmark we can cite as “proved”.
- For us: translate this into a **golden set + hit@k + wrong-scope rate + latency** (already in our mem-engine acceptance criteria).

### Packaging / distribution notes (practical ops)
- NPM-style plugin w/ Node deps (`@lancedb/lancedb`, `@sinclair/typebox`, OpenAI-compatible embedding endpoints).
- Heavy use of env vars for keys; service processes can miss env → needs explicit config discipline.

### Engineering takeaways (actionable for openclaw-mem)
1) **Rerank must be optional + fail-open** (timeout + fallback to fused score).
2) **Adaptive retrieval + noise filter** matter as much as better scoring (skip greetings/acks; filter low-quality capture/store).
3) **Scope is the real guardrail**: multi-scope isolation + per-agent access control prevents “wrong-project” recall even when similarity is high.

### How we fold this into *our* design (without becoming a black box)
- Put scoring layers (hybrid → RRF → optional rerank/MMR/recency) in **`openclaw-mem-engine`**, with receipts for each stage.
- Keep governance (trust tiers/provenance/citations + promotion policy) in **`openclaw-mem` sidecar**.
- Treat every “smart” feature as a **toggleable policy** with deterministic receipts.
