# Outline

## Thesis
Persistent memory in LLMs fails not because systems remember too much, but because they lack the restraint to stay silent when remembering is irrelevant.

## Part 1 — The problem: when memory stops helping and starts performing
- Start from a concrete failure mode, not theory
- Use Karpathy as confirmation, not sole proof
- Introduce the four-part failure model:
  - write
  - classify
  - retrieve
  - surface
- Explain why correct recall can still produce bad UX
- Bring in attention competition: memory injected into context competes with the current task

## Part 2 — Known solution patterns, and what each one actually fixes
- Decay / lifecycle
- Typed memory / tiering
- Retrieval gating / activation policy
- Mention policy / surfacing discipline
- User controls / explainability
- Trust and provenance gating
- Offline compaction / consolidation and its risks
- Cost, latency, and operational complexity tradeoffs
- The no-memory baseline as a real counterfactual

## Part 3 — What `openclaw-mem` gets right, and what it still has not proved
- Why the strongest story is trust-aware context packing, not generic memory storage
- Durable memory vs docs vs topology
- Retention vs activation split
- Working Set backbone, quota mixing, repeat penalty
- Trust-aware pack proof
- Typed episodic retention
- Evidence limits: more proof surfaces than before/after casebook

## Part 4 — The unsolved problem: memory governance, not just memory retrieval
- Evaluation and the missing counterfactual
- Updating and retiring stale interests
- Splitting should-retrieve from should-mention
- Receipts humans can actually use
- Forgetting, deletion, and right-to-forget
- Benchmarks for suppression, abstention, drift handling, and context-appropriate application
- Why the winning systems will look more like governance layers than bigger memory backpacks
