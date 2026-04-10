# Advisory brief — memory personalization overreach

## Trigger
Andrej Karpathy X post (2026-03-25):
> One common issue with personalization in all LLMs is how distracting memory seems to be for the models. A single question from 2 months ago about some topic can keep coming up as some kind of a deep interest of mine with undue mentions in perpetuity. Some kind of trying too hard.

## Working thesis
The real problem is not just "memory decay is missing".
It is a four-part failure:
1. write too much into memory
2. classify memory too crudely
3. retrieve too eagerly
4. surface memory too aggressively in the final response

"Trying too hard" is especially about the last step: even correct memory can be disruptive if the system keeps showing off that it remembers.

## User/market discussion points to evaluate
A Chinese discussion thread summarized the problem as:
- memory weights do not decay
- one-off questions get treated like core interests
- editable text memory (e.g. MEMORY.md + daily notes) is more controllable than opaque auto-memory
- possible directions: decay, memory tiers, user-controlled memory, selective retrieval, turn memory off by default, and maybe "auto dream" / sleep-style consolidation

My current view:
- decay matters, but is not the whole thing
- the deeper product problem is salience estimation + memory typing + retrieval gating + mention policy
- good memory systems should know when to stay quiet
- dream/consolidation could help compression and linking, but should produce candidates rather than silently rewriting canonical memory

## Relevant openclaw-mem local evidence
1. `docs/specs/auto-recall-activation-vs-retention-v1.md`
   - split retention from activation
   - working set as backbone lane
   - quota-mixed hot recall
   - repeat penalty to reduce same durable winners every turn
2. `docs/architecture.md`
   - lifecycle manager / use-based decay is roadmap
   - context pack should be small, auditable, and cheap
3. `docs/openclaw-user-improvement-roadmap.md`
   - harder scope isolation
   - ranking that matches operator expectations
   - explainability for why recall happened
   - lifecycle MVP based on actual inclusion, not retrieval
4. `docs/agent-memory-skill.md`
   - durable memory is not for raw docs/code/transcripts
   - route docs/topology/memory separately
5. `docs/showcase/trust-aware-context-pack-proof.md`
   - selection quality matters, not just storage quantity
   - smaller/safer packs can outperform naive retrieval
6. `docs/specs/episodic-auto-capture-v0.md`
   - episodic lanes already have retention defaults by event type

## What I want from you
Please act as a sharp critical reviewer.
Give me:
1. what is strongest or weakest in the thesis above
2. what important angle is missing
3. what you would emphasize for a technical-but-readable long-form series
4. a recommended 4-part article arc covering:
   - the problem and why it appears now
   - known solution patterns and their tradeoffs
   - openclaw-mem practical lessons
   - unsolved questions / future directions
5. 5-10 bullets of critique, not fluff
6. one concise thesis sentence I could use as the series spine

## Constraints
- Audience: smart non-programmers plus technical operators
- Tone: precise, reality-first, not hype
- Avoid generic AI-blog filler
- Prefer disagreement and compression over praise
