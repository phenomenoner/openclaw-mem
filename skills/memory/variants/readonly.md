# Read-only variant

Inherit `skills/memory/SKILL.md`, then apply these overrides for watchdog, healthcheck, lint, smoke, and high-volume cron lanes:

- Allow recall, docs search, graph/topology lookup, Pack, and status checks.
- Deny durable store by default.
- Store only when an incident produced a standing rule and the operator explicitly asks to persist that rule.
- Never store routine OK output or raw incident logs.
- Use read-role gateway tokens only; do not request write, admin, or owner authority.
- Inspect Dream Lite plans and receipts only; do not run apply or rollback.
- Prefer protected Pack tails for long task continuity rather than routine status writes.
- Enforce runtime read-only mode when available, or withhold mutation tools.

If everything is healthy, follow the caller's no-op response contract (for example `NO_REPLY`).
