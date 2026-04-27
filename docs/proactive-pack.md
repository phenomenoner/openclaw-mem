# Proactive Pack

`Proactive Pack` is the public-facing name for `openclaw-mem-engine`'s **bounded pre-reply recall orchestration**.

It answers one product question:

> before the model replies, can we surface the smallest useful memory/context bundle without creating a second hidden memory kingdom?

## Verdict

In `openclaw-mem`, the answer is **yes, but only if Pack stays the truth owner for prompt assembly**.

That means Proactive Pack is:

- **pre-reply**: runs during prompt build for eligible live turns
- **bounded**: capped by item count, scope policy, and final context budget
- **receipt-backed**: lifecycle/debug receipts stay visible to operators
- **fail-open**: weak or empty matches inject nothing
- **optional**: enabled only when the mem-engine role is active and configured

It is **not**:

- a parallel durable-memory system
- a transcript dump lane
- an always-on hidden personalization layer for every runtime
- a reason to bypass `ContextPack` or pack receipts

## Where it fits in Store / Pack / Observe

- **Store** owns durable records and retrieval candidates.
- **Pack** owns prompt-ready assembly.
- **Observe** owns receipts, traces, and offloaded raw payload visibility.

Proactive Pack is therefore a **Pack runtime mode**, not a fourth product plane.

## Current implementation surface

Today this capability is powered by mem-engine controls such as:

- `autoRecall`
- `autoRecall.routeAuto`
- `before_prompt_build` prompt mutation (with `before_agent_start` legacy fallback)
- scope policy
- context budget
- optional docs cold-lane consultation
- bounded receipts

Those knobs exist to keep runtime recall useful without letting it become opaque.

Operationally, `autoRecall.routeAuto` uses the compact route-auto payload path for prompt hooks. Timeout or subprocess failures are fail-open and recorded in receipts, including explicit timeout fields for diagnosis.

## Eligibility posture

Use Proactive Pack when all of these are true:

- the session is interactive and user-facing
- continuity matters more than strict one-shot determinism
- a bounded recall block is helpful before the reply
- operators want rollbackable controls and receipts

Avoid it for:

- background workers
- one-shot tasks
- cron/heartbeat lanes
- any lane where hidden personalization would be surprising

## Product boundary

`openclaw-mem` deliberately does **not** treat proactive recall as a second truth owner.

If the mem-engine hook is active:

- prompt injection should stay **small, bounded, and policy-shaped**
- receipts should explain why it ran, what it selected, and what got cut
- durable writes still go through the canonical write path
- graph/docs/synthesis can enrich selection, but do not become new truth owners

## Recommended operator language

When explaining this lane publicly, prefer:

- **Proactive Pack**
- **pre-reply bounded recall**
- **receipt-backed personalization**
- **fail-open runtime pack mode**

Avoid framing it as:

- autonomous hidden personalization
- magic memory injection
- a separate memory product inside the product

## Related docs

- [About openclaw-mem](about.md)
- [Choose an install path](install-modes.md)
- [Mem Engine reference](mem-engine.md)
- [Ecosystem fit](ecosystem-fit.md)
- [Context pack](context-pack.md)
