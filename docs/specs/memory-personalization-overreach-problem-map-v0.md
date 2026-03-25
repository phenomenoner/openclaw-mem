# Memory personalization overreach — problem map v0

## Status
- State: working tech note
- Scope: framing + design guidance for long-horizon personalization / memory behavior
- Audience: `openclaw-mem` operators, designers, and contributors
- Topology impact: none

## Trigger
Andrej Karpathy's 2026-03-25 post names a failure pattern many users have felt but few product surfaces describe well:

> A single question from 2 months ago about some topic can keep coming up as some kind of a deep interest of mine with undue mentions in perpetuity. Some kind of trying too hard.

The important detail is not merely that a system **remembers** old context.
It is that the system keeps **applying** and **surfacing** that context long after it stopped being proportionate.

## Reframe: the problem is not only forgetting
The popular framing for LLM memory is usually:
- models forget too much,
- context windows are too small,
- long-term memory needs better recall.

That framing is incomplete.

A second failure mode is now equally important:
- models and products can **over-remember**, **over-apply**, and **over-surface** stale signal.

This is especially visible in personalized assistants, cross-session agents, and any product with persistent memory.

## Four-part failure model
The cleanest working diagnosis is:

1. **Write too much into memory**
   - one-off questions, temporary curiosities, or weakly inferred preferences get stored as if they were durable facts
2. **Classify too crudely**
   - systems blur stable profile, temporary task state, episodic traces, docs knowledge, and raw artifacts into one bucket
3. **Retrieve too eagerly**
   - retrieval or auto-recall drags old signal back into scope whenever there is loose semantic overlap
4. **Surface too aggressively**
   - once a memory is retrieved, the assistant treats it as something it should mention, often as a performance of "I remember you"

Karpathy's "trying too hard" is mostly about step 4, but step 4 is usually caused upstream by steps 1–3.

## Why this shows up now
This problem becomes more visible when all of the following rise together:
- longer-running chat sessions
- persistent user profiles / memory stores
- cross-session personalization features
- agent products that try to preserve continuity across many tasks
- product pressure to make assistants feel personal and sticky

In other words, the issue is less about the base model suddenly becoming sentimental, and more about the surrounding product stack getting bold enough to keep context alive.

## Known solution patterns — what each one actually solves

### 1) Decay / lifecycle
**What it helps:**
- removes stale records from long-term dominance
- bounds DB growth and reduces repeated winners
- better reflects that many user interests are temporary

**What it does not solve alone:**
- one-off items that were misclassified as durable in the first place
- retrieval that is still too eager while the record remains alive
- response generation that still mentions recalled memory unnecessarily

Practical note for `openclaw-mem`:
- `docs/architecture.md` already frames lifecycle as **use-based retention** rather than naive age-only deletion
- `docs/specs/episodic-auto-capture-v0.md` already applies typed retention defaults by event kind

### 2) Memory typing / tiering
**What it helps:**
- separates stable profile from episodic traces and task-local state
- prevents everything from competing for the same recall budget
- creates room for different retention and visibility rules by type

**What it does not solve alone:**
- bad recall ranking inside each tier
- poor surfacing rules after retrieval

Practical note for `openclaw-mem`:
- `docs/agent-memory-skill.md` already enforces a useful hard boundary: L1 durable memory vs L2 docs vs L3 topology
- this is not just repo hygiene; it is memory-governance hygiene

### 3) Selective retrieval / activation gating
**What it helps:**
- reduces prompt pollution
- lets relevant but non-durable signal win when appropriate
- makes room for turn-specific information instead of static prefixes

**What it does not solve alone:**
- low-quality writes into durable storage
- hallucinated or low-trust memories entering selection

Practical note for `openclaw-mem`:
- `docs/specs/auto-recall-activation-vs-retention-v1.md` is already pointed in the right direction:
  - retention != activation
  - Working Set as backbone lane
  - quota-mixed hot recall
  - repeat penalty to stop the same durable winners from appearing every turn

### 4) Mention policy / strategic silence
**What it helps:**
- stops the assistant from showing off remembered context merely because it can
- creates a second gate after retrieval: "should I say this now?"
- directly targets the UX failure Karpathy described

**What it does not solve alone:**
- bloated stores and bad ranking

This area is still under-specified in many systems. It deserves to become a first-class contract surface, not an implicit side effect of the generation prompt.

### 5) Trust / provenance gating
**What it helps:**
- prevents stale, hostile, or low-trust material from quietly re-entering prompts
- keeps operators able to inspect why memory was selected

Practical note for `openclaw-mem`:
- `docs/showcase/trust-aware-context-pack-proof.md` already demonstrates the important wedge:
  - same query
  - same DB
  - different trust policy
  - quarantined row drops out
  - trusted row takes its place
  - pack gets smaller while receipts remain intact

This matters here because personalization failures are not only about time. They are also about **which memories deserve re-entry at all**.

### 6) User control + explainability
Editable memory is better than opaque auto-memory, but that alone is not enough.
A strong system should be able to answer:
- why was this memory written?
- why was it recalled now?
- why was it surfaced instead of silently influencing selection?
- what would make it expire, archive, or stop being mentioned?

`openclaw-mem` already leans toward receipts and inspectability. The next gap is not the existence of receipts, but making them answer the human operator's question in one screen.

### 7) Consolidation / "dream" style rewriting
This direction is attractive because it promises compression, linking, and de-duplication.
It also carries a major risk:
- noisy episodes become overconfident summaries
- weak signal turns into stable profile
- wrong memory becomes a higher-level wrong belief

Practical stance:
- consolidation should generate **candidates**
- it should not silently rewrite canonical memory without review or bounded policy

## External benchmarks worth watching
Two external references help anchor this area:

1. **BenchPreS** (`arXiv:2603.16557`)
   - relevant because it evaluates whether persistent user preferences are applied or suppressed appropriately across contexts
   - useful warning: stronger preference adherence can raise over-application risk

2. **LongMemEval** (ICLR 2025)
   - relevant because it treats long-term interactive memory as a realistic multi-session problem rather than a toy retrieval demo
   - useful warning: "can retrieve something" is not the same as "uses memory well over time"

## What `openclaw-mem` should keep emphasizing
This note strengthens an existing product instinct:

`openclaw-mem` should not sell itself as "more memory".
It is stronger when framed as:
- **memory governance**
- **trust-aware context packing**
- **retention/activation separation**
- **auditable selection and suppression**

Why:
- the most painful failure mode is not lack of storage
- it is low-quality selection plus low-quality surfacing

## Design implications for future work
1. Make **retention**, **retrieval**, and **mention** separate policy surfaces.
2. Treat **strategic silence** as a feature, not as accidental omission.
3. Keep lifecycle **use-based** when possible; retrieval alone should not count as proof of value.
4. Expand operator-facing receipts so they explain not just inclusion, but also suppression.
5. Keep consolidation candidate-based and reviewable.
6. Preserve hard boundaries between durable memory, docs knowledge, and topology knowledge.
7. Continue favoring **smaller, cited, bounded context packs** over "more memory in prompt".

## Advisory lane receipts
- Standalone Claude CLI was attempted and failed due a host/root dangerous-permissions posture issue before content generation.
- Standalone Gemini CLI completed successfully on `gemini-2.5-flash` after the default Pro lane hit capacity errors.
- Gemini's most useful pushback:
  - be explicit about cost/complexity tradeoffs
  - strengthen user control + explainability
  - treat adaptive personalization over time as a first-class open problem

## Bottom line
The next generation of memory systems will not win by remembering more.
They will win by being better at deciding:
- what to store,
- what to retrieve,
- what to suppress,
- and what to leave unsaid.
