# Context engineering lessons (local-first)

This note captures practical **context engineering** patterns for long-running agents, based on public write-ups (e.g. Manus) and our own OpenClaw/openclaw-mem experience.

The goal is not to “over-engineer context”, but to make an agent:
- faster (latency)
- cheaper (token/caching efficiency)
- safer (auditability, privacy)
- more consistent (less drift)

## 1) Design for KV-cache / stable prefixes
In production agent loops, input tokens can dwarf output tokens. Small prefix changes can destroy cache reuse.

Practical rules:
- Keep system/instructions **stable** (avoid inserting per-turn timestamps at the top).
- Prefer **deterministic serialization** for structured data (stable key ordering, stable formatting).
- Treat “protocol docs” as the stable prefix and keep volatile content append-only.

How we apply this:
- Slow-cook playbooks keep stable templates (`PROJECT/STATUS/DECISIONS` + digest template).
- `openclaw-mem` stores a stable, auditable record in SQLite rather than re-sending everything each turn.

## 1.5) Structured bundles (hybrid text + JSON) beat prose for “relevant state”
When the agent needs to reliably *use* facts/constraints (not just read a story), structured key/value blocks reduce ambiguity and speed up “where is the thing?” scanning.

Practical rules:
- Prefer a **hybrid**: a short natural-language preface + a shallow JSON object.
- Keep JSON **shallow** (flat objects + arrays); deep nesting wastes tokens and becomes brittle.
- Serialize deterministically (stable key ordering/formatting) to preserve cache behavior and enable diff/bench comparisons.
- Every packed item must carry a stable provenance key (e.g., `recordRef`).

How we apply this:
- `openclaw-mem pack` already emits structured JSON (`items[]`, `citations[]`) and can emit a redaction-safe trace receipt.
- Roadmap direction: formalize a `ContextPack.v1` schema so structure remains stable and injection-friendly.

See: `docs/context-pack.md`.

## 2) Mask, don’t remove (avoid dynamic tool sets)
Dynamically adding/removing tool definitions mid-loop can:
- break prefix stability (cache hit rate drops)
- confuse the model when history references tools that are no longer defined

Prefer:
- keep a stable tool set
- use **gating** (policy, allowlists, state-machine constraints) to restrict what is available

How we apply this:
- `openclaw-mem` is intentionally a **sidecar**: it doesn’t try to own the canonical memory slot.
- We keep operational control through deterministic triage + feature flags, rather than swapping tool schemas per turn.

## 3) Filesystem as “ultimate context” (externalize, keep references)
Large observations (web pages, PDFs, logs) don’t belong in the live context window.

Prefer:
- write large artifacts to files
- keep a small reference in context: path/url + a short summary
- ensure the reference is **recoverable** (so the agent can re-load later)

How we apply this:
- openclaw-async-coding-playbook uses file-based truth.
- `openclaw-mem` maintains a local ledger that can be searched/timelined on demand.

## 4) Recitation to manage attention (keep goals near the end)
Long loops drift. A simple technique is to repeatedly restate the goal/plan near the end of the context:
- update `STATUS.md`
- keep a `todo.md`-style checklist

How we apply this:
- each slow-cook cycle updates `STATUS.md` and produces a digest.
- Persona Lab uses fixed prompts + prompt IDs to reduce confounds.

## 5) Keep failures visible (don’t hide errors)
Hiding errors removes evidence. Evidence helps the model (and humans) avoid repeating mistakes.

How we apply this:
- `openclaw-mem triage --mode cron-errors` surfaces recurring failures.
- importance grading can up-rank incidents/runbooks while down-ranking chatter.

## 6) Controlled diversity (avoid few-shot lock-in)
Models imitate patterns. Too much repeated structure can create brittle behavior.

Prefer controlled diversity:
- rotate prompts (with IDs)
- vary task types intentionally
- periodically calibrate scoring/reviews

How we apply this:
- Persona Lab rotates prompts and uses a rubric + peer review to manage drift.

## Where this connects to openclaw-mem importance grading
Importance grading is a **context engineering tool**:
- it decides what deserves durable recall and what can stay as low-signal noise
- it enables selective retrieval, keeping live context smaller and more relevant

See also:
- `docs/importance-grading.md`
- `docs/ecosystem-fit.md`

## References
- Manus (context engineering lessons):
  - https://manus.im/zh-tw/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
- Additional summary (Chinese):
  - https://blog.csdn.net/HUANGXIN9898/article/details/154076091
