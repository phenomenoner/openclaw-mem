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
