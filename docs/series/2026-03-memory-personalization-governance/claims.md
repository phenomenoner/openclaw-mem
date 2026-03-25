# Claims table

## Core claims
1. Claim
   - Karpathy's complaint is not mainly about forgetting; it is about stale memory being repeatedly over-applied and over-mentioned.
   - Status: sourced
   - Source: Karpathy X post, 2026-03-25

2. Claim
   - Personalization failures are often product-stack failures in write/classify/retrieve/surface policy, not only base-model memory limitations.
   - Status: synthesis
   - Source: series analysis + `docs/agent-memory-skill.md` + `docs/specs/auto-recall-activation-vs-retention-v1.md`

3. Claim
   - Decay is necessary but insufficient; it cannot by itself fix misclassification, over-retrieval, or over-surfacing.
   - Status: synthesis
   - Source: series analysis + `docs/architecture.md` + `docs/specs/episodic-auto-capture-v0.md`

4. Claim
   - Persistent user preferences can be over-applied as though they were globally valid rules rather than context-sensitive signals.
   - Status: sourced
   - Source: BenchPreS (`arXiv:2603.16557`)

5. Claim
   - Long-term interactive memory should be evaluated in realistic multi-session settings, not only toy retrieval tests.
   - Status: sourced
   - Source: LongMemEval (ICLR 2025 / OpenReview)

## openclaw-mem-specific claims
6. Claim
   - `openclaw-mem` already distinguishes durable memory, docs knowledge, and topology knowledge as separate lanes.
   - Status: sourced
   - Source: `docs/agent-memory-skill.md`

7. Claim
   - `openclaw-mem` roadmap direction explicitly separates retention from activation in auto-recall policy.
   - Status: sourced
   - Source: `docs/specs/auto-recall-activation-vs-retention-v1.md`

8. Claim
   - `openclaw-mem` lifecycle direction is use-based rather than simple age-only deletion.
   - Status: sourced
   - Source: `docs/architecture.md`, `docs/openclaw-user-improvement-roadmap.md`

9. Claim
   - `openclaw-mem` already has a concrete proof that trust-aware pack selection can exclude quarantined rows while preserving citations and receipts.
   - Status: sourced
   - Source: `docs/showcase/trust-aware-context-pack-proof.md`

10. Claim
   - `openclaw-mem` already applies typed retention defaults to episodic event classes.
   - Status: sourced
   - Source: `docs/specs/episodic-auto-capture-v0.md`

## Forward-looking claims
11. Claim
   - Mention policy should become a first-class contract, not an implicit side effect of retrieval.
   - Status: recommendation
   - Source: series synthesis

12. Claim
   - Consolidation / dream-style mechanisms should generate candidates rather than silently rewrite canonical memory.
   - Status: recommendation
   - Source: series synthesis

13. Claim
   - Future memory benchmarks should measure suppression, abstention, drift handling, and context-appropriate application, not only recall accuracy.
   - Status: recommendation
   - Source: series synthesis + BenchPreS + LongMemEval framing
