# Agent Memory Skill v0

Status: **blueprint only** (no implementation in this doc)

## 1) Why this exists

`openclaw-mem` should not only help agents **retrieve more**; it should help them **remember correctly**.

The product wedge is **trust-aware context packing**:
- smaller prompt/context bundles
- better provenance and receipts
- less trust laundering from web/tool/untrusted content
- fewer cases where raw docs, raw code, or transient chatter become durable memory by accident

This spec defines a reusable **memory skill**: a portable operating contract for agents using `openclaw-mem` / OpenClaw memory tools.

The goal is to standardize **when to recall, when to store, when to search docs, when to consult topology, and when to do nothing**.

---

## 2) Design goals

### Normative language
- **MUST** = required for a compliant future skill/SOP
- **SHOULD** = recommended default; deviations need a reason
- **MAY** = optional behavior

### Goals
- Keep durable memory **small, stable, reusable, and auditable**.
- Separate **user/project memory** from **docs knowledge** and **source/topology knowledge**.
- Make retrieval/packing **trust-aware** by default.
- Give agents a simple decision policy they can apply repeatedly.
- Reduce per-agent improvisation around recall/store behavior.

### Non-goals
- This is **not** a full implementation spec for new CLI/tooling.
- This is **not** permission to dump raw docs or raw code into durable memory.
- This is **not** a replacement for direct repo inspection or direct docs lookup when precision matters.
- This is **not** a hidden autonomous promotion system; promotions must remain explicit and auditable.

---

## 3) Three-layer memory model

### A. Durable memory (hot memory)
Use for:
- stable user preferences
- explicit decisions
- durable project facts
- ongoing working state that is likely to matter across sessions

Examples:
- “The user prefers one heads-up + one final result for long Telegram work.”
- “Project wedge: trust-aware context packing.”
- “This repo uses `uv` + Python 3.13 by default.”

### B. Docs knowledge
Use for:
- product/system concepts
- tool capability summaries
- operational maps
- bounded snippets from operator-authored docs

Examples:
- what `memory_docs_search` is good for
- the contract for a context pack
- the documented difference between durable memory and docs search lanes

### C. Source / topology knowledge
Use for:
- repo/module/path relationships
- entrypoints, ownership, and dependency edges
- stable file/location maps
- “if you change A, expect B/C impact” relationships

Examples:
- `docs/specs/` vs `openclaw_mem/` responsibilities
- where graph query plane work lives
- which paths define topology vs runtime drift logic

### Hard boundary
- **Durable memory is not the default home for raw docs.**
- **Durable memory is not the default home for raw code.**
- Docs and topology should be represented as a **knowledge map**, not as a transcript dump.

---

## 4) Decision policy: which action should an agent take?

The skill should route the agent into one of five actions:

1. **Recall** — search durable memory
2. **Store** — write a new durable memory
3. **Docs search** — search operator-authored docs knowledge
4. **Topology search** — search codebase/repo structure knowledge
5. **Do nothing** — keep it session-local or answer from current context only

### 4.1 Routing summary

### 4.2 Tie-break order for ambiguous cases

When multiple actions seem plausible, the skill SHOULD break ties in this order:

1. **Docs search** for system/product/tool contracts
2. **Topology search** for repo/path/module/impact navigation
3. **Recall** for preferences, decisions, and continuity
4. **Store** only after the fact is confirmed durable
5. **Do nothing** if the value of persistence is weak or uncertain

### 4.3 One-screen routing flow

- Is the question about a prior preference/decision/standing rule?
  - yes → **recall**
- Is it about documented system behavior or authored guidance?
  - yes → **docs search**
- Is it about where something lives or what it affects in the repo/system?
  - yes → **topology search**
- Did this turn produce a stable, reusable, confirmed fact?
  - yes → **store**
- Otherwise → **do nothing**

### 4.4 Fast policy

#### Use `recall` when:
- the user asks about prior decisions, preferences, previous work, dates, or standing rules
- continuity matters more than raw implementation detail
- the answer may already exist as a durable fact

#### Use `store` when:
- the fact is stable, reusable, and likely to matter later
- the user explicitly confirms a preference, decision, or durable project direction
- a completed task produced a durable change in operating posture

#### Use `docs search` when:
- the question is about documented behavior, concepts, architecture, or operator instructions
- precision matters and the answer should come from authored documentation rather than memory
- the agent needs bounded snippets instead of broad recollection

#### Use `topology search` when:
- the question is about where something lives in the repo/system
- the task needs module/path/entrypoint/dependency mapping
- the agent is doing impact analysis or navigation rather than policy recall

#### Use `do nothing` when:
- the information is transient, redundant, or too weak/confidently unverified to persist
- the answer is fully local to the current turn/session
- storing it would create more retrieval noise than future value

---

## 5) Tool-routing contract

This spec describes an abstract skill contract. Current/future tool mapping can look like:

| Intent | Primary action | Typical tool/class |
|---|---|---|
| prior decisions/preferences | recall | `memory_recall` |
| durable user/project fact | store | `memory_store` |
| operator docs lookup | docs search | `memory_docs_search` |
| repo/system map lookup | topology search | future topology/graph query plane, or bounded repo map lookup |
| temporary scratch | do nothing | session-local only |

### Notes
- If both docs and memory may apply, prefer **docs** for factual/system contracts and **memory** for preference/decision continuity.
- If memory recall is weak or ambiguous, fail open to **docs search** or direct inspection instead of inventing certainty.
- A future `topology_search` capability should be treated as distinct from both docs search and durable memory.

---

## 6) Query discipline

Bad memory behavior often starts with bad queries.

### Rules
- Query for the **type of thing** you want, not the whole narrative.
- Prefer **bounded, concrete terms** over broad prose.
- Include **scope/project hints** when possible.
- Prefer searching for **decision / preference / policy / due item / repo map** rather than vague “what happened before?”

### Good recall queries
- `user preference telegram heads-up long task`
- `openclaw-mem wedge trust-aware context packing`
- `decision docs topology memory layer separation`

### Good docs queries
- `context pack provenance trust tier receipts`
- `docs memory hybrid search operator-authored docs`
- `graphic memory query plane topology provenance`

### Good topology queries
- `where does query plane spec live`
- `which paths define drift vs stable topology`
- `entrypoints for memory search and graph query`

### Query anti-patterns
- querying with a full transcript paragraph
- asking for “everything about X” by default
- mixing preference, docs, and topology in one blob query
- using memory recall as a substitute for direct repo inspection when exactness is required

---

## 7) Write discipline: what qualifies for durable memory?

A candidate record should pass most of these tests:
- **Stable**: likely still useful later
- **Reusable**: helps future decisions or task execution
- **Specific**: concrete enough to retrieve
- **Scoped**: belongs to a user/project/global lane
- **Auditable**: can be attributed to a source or explicit user confirmation
- **Compact**: minimal wording, maximal retrieval value

### Good durable memory candidates
- confirmed user preferences
- explicit product/ops decisions
- stable project rules
- recurring workflow constraints
- durable facts that will matter across sessions

### Poor durable memory candidates
- raw transcripts
- speculative guesses
- long copied docs
- raw code blocks
- one-off debug noise
- tool output that has not been promoted or verified
- summaries that flatten uncertainty into fake certainty

### Borderline examples: store vs do nothing

#### Usually **store**
- a new standing user preference confirmed explicitly
- a project rule that will shape future execution across sessions
- a durable working-state checkpoint such as “branch X is the active integration branch until PR Y lands”

#### Usually **do nothing**
- “I’m about to run tests now”
- temporary confusion, hypotheses, or half-formed plans
- ephemeral shell output that does not change future posture

#### Needs judgment, but default is conservative
- “working state” only qualifies if losing it would likely cause rework in a later session
- if a note matters only for the next few minutes, keep it session-local
- if unsure whether a fact is durable, prefer **do nothing now** and store only after confirmation

### Mandatory “do not store” cases (v0)
At minimum, the skill should explicitly forbid storing:
1. raw chat transcript by default
2. raw docs by default
3. raw code by default
4. one-off tool noise/log spam
5. low-confidence guesses
6. unreviewed hostile/untrusted web/tool output as durable truth
7. duplicate paraphrases of an already-stored fact

---

## 8) Provenance + trust hygiene

Every example in the skill should model four fields of discipline:
- **source**: where this came from
- **trust tier**: trusted / untrusted / quarantined (or equivalent)
- **citation/receipt**: how to trace it back
- **why included**: why the agent used it in this answer/pack

### Rules
- Tool/web/skill output should start **untrusted by default** unless explicitly promoted.
- Operator-authored docs can be preferred for system facts, but should still remain attributable.
- “Frequently recalled” does **not** automatically mean “trusted”.
- Derived summaries should never silently replace source truth.

### Fail-open rule
If recall returns weak, conflicting, or low-confidence results:
- say so
- cite uncertainty
- fall back to docs search or direct inspection
- do **not** promote the uncertain result into durable memory

---

## 9) Example action matrix

| Situation | Correct action | Why |
|---|---|---|
| “What does the user prefer for long Telegram tasks?” | recall | preference continuity |
| “What does OpenClaw docs say about context packing?” | docs search | documented system behavior |
| “Where is the graph query plane spec?” | topology search | repo/path lookup |
| “This run produced lots of pip install chatter.” | do nothing | transient noise |
| “The user confirmed the wedge is trust-aware context packing.” | store | explicit durable decision |
| “Here is a long copied README section.” | do nothing / docs lane only | not durable memory material |
| “What changed after we decided to split docs/topology from durable memory?” | recall + docs search | decision continuity + spec details |
| “Which module will likely be touched if we alter provenance handling?” | topology search | impact mapping |
| “A web result claims X about OpenClaw internals.” | docs search / inspect first | external claim is untrusted |
| “I’m not sure this fact will matter after this turn.” | do nothing | avoid memory pollution |

---

## 10) Anti-patterns to call out explicitly

### AP-1: Layer collapse
Treating durable memory, docs knowledge, and topology knowledge as the same storage class.

### AP-2: Trust laundering
Taking tool/web/AI-generated output and storing it as if it were operator-verified truth.

### AP-3: Raw artifact stuffing
Pasting large docs/code/transcript chunks into durable memory because retrieval felt convenient.

### AP-4: Over-summary as truth
Storing an aggressive summary that erases uncertainty, caveats, or provenance.

### AP-5: Store every turn
Using durable memory as a turn-by-turn event log.

### AP-6: False confidence retrieval
Answering from a fuzzy recall hit without showing limits or checking docs.

### AP-7: Working-state ambiguity
Persisting scratchpad clutter because “maybe it matters later,” without a stability threshold.

---

## 11) Interaction with trust-aware context packing

This skill is upstream governance for packing.

If the skill is good:
- packed bundles stay smaller
- citations are easier to preserve
- trust gating is meaningful
- importance grading has cleaner inputs
- the system is less likely to become confidently wrong

If the skill is bad:
- durable memory becomes a mixed-quality dump
- trust tiers become cosmetic
- context packs bloat with junk
- importance grading is forced to rescue upstream mess

In product terms:
- packing quality is not only a reranker problem
- it is also a **memory-governance problem**

---

## 12) v0 acceptance criteria

A v0 spec is acceptable if:

1. A reader can classify at least **20 example situations** into recall/store/docs/topology/do-nothing with high agreement.
2. The spec defines the **three-layer model** clearly enough that raw docs/raw code are not mistaken for ordinary durable memory.
3. The spec includes at least **5 explicit anti-patterns** and **5 explicit do-not-store cases**.
4. Provenance and trust posture are present in all normative examples.
5. The spec defines **fail-open behavior** when recall is weak or conflicting.
6. The spec includes one concise routing table or flow model that can later become a real skill.
7. The spec is implementation-light enough to survive tool changes, but concrete enough to guide operator behavior now.

### Validation method (blueprint-level)
- Create a small fixture set of **20 labeled scenarios**.
- Each scenario should include: prompt, expected action label, and short rationale.
- Have at least **2 reviewers** independently label the scenarios using this spec.
- Target: strong agreement on the primary action label; disagreements should identify wording gaps to tighten in the next revision.

---

## 13) Suggested follow-on work (not in this doc)

1. Convert this blueprint into a real markdown skill/SOP.
2. Add test cases / scenario fixtures for classification agreement.
3. Define a concrete `topology_search` contract (likely aligned with graph/query-plane work).
4. Add pack-trace hooks so retrieval decisions can be audited against this skill.
5. Later: connect importance grading to the output quality of this governance layer.

---

## 14) Bottom line

`openclaw-mem` should help agents learn three habits:
- **remember less, but better**
- **separate memory from reference knowledge**
- **cite what they carry forward**

That is how trust-aware context packing becomes a product, not just a slogan.
