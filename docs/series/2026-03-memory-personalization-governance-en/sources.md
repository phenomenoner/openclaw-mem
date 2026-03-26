# Sources

## Trigger and public discussion
1. Andrej Karpathy, X post (2026-03-25)
   - https://x.com/karpathy/status/2036836816654147718
   - Core trigger: personalization memory often feels distracting because stale interests keep resurfacing.

## External research anchors
2. BenchPreS — *A Benchmark for Context-Aware Personalized Preference Selectivity of Persistent-Memory LLMs*
   - https://arxiv.org/abs/2603.16557
   - Useful for the claim that persistent preferences can be over-applied as if they were globally valid rules.

3. LongMemEval — *Benchmarking Chat Assistants on Long-Term Interactive Memory*
   - https://openreview.net/forum?id=pZiyCaVuti
   - https://dblp.org/rec/conf/iclr/WuWYZCY25.html
   - Useful for framing long-term memory as a realistic, multi-session problem rather than a toy recall task.

## openclaw-mem references
4. `docs/specs/auto-recall-activation-vs-retention-v1.md`
   - Retention vs activation split, Working Set backbone, quota mixing, repeat penalty.

5. `docs/architecture.md`
   - Lifecycle manager roadmap, use-based retention, and context pack framing.

6. `docs/openclaw-user-improvement-roadmap.md`
   - Scope isolation, ranking, explainability, and lifecycle MVP direction.

7. `docs/agent-memory-skill.md`
   - Durable memory vs docs vs topology separation.

8. `docs/showcase/trust-aware-context-pack-proof.md`
   - Concrete proof that trust-aware selection matters.

9. `docs/specs/episodic-auto-capture-v0.md`
   - Typed retention defaults by event class.

## Advisory receipts
10. `claude_review.md`
   - Standalone Claude critique used to sharpen the English series structure and argument.
   - Most useful pushes: make attention competition explicit, justify memory against the no-memory baseline, be more honest about current proof surfaces, and lead future-work with evaluation.
