# Claims

1. Claim
- The most painful failures in persistent LLM memory are often over-application and over-surfacing failures, not just forgetting failures.
- Status: synthesis
- Support: Karpathy trigger + series analysis

2. Claim
- The four-part model (write / classify / retrieve / surface) is a more useful diagnosis than "just add decay."
- Status: synthesis
- Support: series argument + local specs

3. Claim
- Persistent preferences can be misapplied as if they were globally valid rules instead of context-sensitive signals.
- Status: sourced
- Support: BenchPreS

4. Claim
- Long-term interactive memory should be evaluated in realistic multi-session settings, not only toy recall tasks.
- Status: sourced
- Support: LongMemEval

5. Claim
- `openclaw-mem` is stronger as a trust-aware context packing and governance story than as a generic memory-storage story.
- Status: synthesis with local evidence
- Support: architecture docs, trust-aware pack proof, agent memory skill, roadmap

6. Claim
- A correct recall that the user did not ask for can be functionally indistinguishable from a wrong recall in the user experience.
- Status: advisory synthesis
- Support: Claude critique + series framing

7. Claim
- Future memory systems need first-class policies for retrieval and surfacing, not just storage and search.
- Status: recommendation
- Support: series analysis
