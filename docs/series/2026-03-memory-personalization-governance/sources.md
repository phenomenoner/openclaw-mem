# Source log

## Primary trigger
1. Andrej Karpathy, X post (2026-03-25)
   - https://x.com/karpathy/status/2036836816654147718
   - Trigger quote: current LLM personalization often feels like memory is "trying too hard" and keeps resurfacing stale interests.

## External references
2. BenchPreS — *A Benchmark for Context-Aware Personalized Preference Selectivity of Persistent-Memory LLMs* (arXiv:2603.16557)
   - https://arxiv.org/abs/2603.16557
   - Useful for the claim that personalized preferences are often over-applied as if they were globally valid rules.

3. LongMemEval — *Benchmarking Chat Assistants on Long-Term Interactive Memory* (ICLR 2025 / OpenReview via DBLP)
   - https://openreview.net/forum?id=pZiyCaVuti
   - https://dblp.org/rec/conf/iclr/WuWYZCY25.html
   - Useful for framing why multi-session memory needs realistic evaluation beyond toy retrieval.

## openclaw-mem local references
4. `docs/specs/auto-recall-activation-vs-retention-v1.md`
   - Split retention from activation; Working Set as backbone lane; quota-mixed hot recall; repeat penalty.

5. `docs/architecture.md`
   - Lifecycle manager roadmap, use-based decay, and context pack framing.

6. `docs/openclaw-user-improvement-roadmap.md`
   - Immediate/P1 roadmap around scope isolation, better ranking, explainability, and lifecycle MVP.

7. `docs/agent-memory-skill.md`
   - Strong routing contract: durable memory is not for raw docs/transcripts; docs/topology/memory are separate lanes.

8. `docs/showcase/trust-aware-context-pack-proof.md`
   - Canonical proof that selection quality and trust policy matter; smaller/safer pack can outperform naive inclusion.

9. `docs/specs/episodic-auto-capture-v0.md`
   - Existing retention defaults by event type, useful when discussing typed retention instead of flat memory.

## Advisory lanes
10. Standalone Claude CLI attempts (2026-03-26)
   - Old bad path: `--permission-mode bypassPermissions` on this root-host lane
   - That path reproduced the dangerous-permissions rejection and confirmed the guidance bug
   - Latest corrected one-shot posture: `claude --print --model opus --bare --no-session-persistence --tools ""`
   - Latest blocker is no longer permission posture but auth state: `Not logged in · Please run /login`
   - Operationally relevant: the guidance bug is fixed; current unusability is an auth/login issue, not the old permission bug.

11. Standalone Gemini CLI review (Gemini 2.5 Flash)
   - Main useful pushback:
     - strengthen cost/complexity tradeoffs
     - explicitly discuss user control + explainability
     - call out adaptive personalization as a missing angle
   - Strong thesis reinforcement: strategic silence matters more than raw recall volume.
