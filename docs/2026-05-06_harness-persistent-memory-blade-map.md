# Harness-persistent openclaw-mem implementation plan

Status: implementation line started 2026-05-06

## Goal

Make `openclaw-mem` usable by external AI harnesses (Codex, Claude Code, Gemini CLI, Cursor/OpenCode-style agents) as a persistent installed posture instead of a one-off readable skill card.

The harness should start each new session knowing when and how to use the memory gateway, and gateway tokens should express the exact read/write authority the operator chose.

## Non-goals for this slice

- No public Internet exposure of the gateway.
- No marketplace publication for every harness in this first patch.
- No autonomous rewrite of curated authority files by default.
- No second memory owner: Store / Pack / Observe remain the product split.

## Design decisions

1. Add capability-scoped gateway tokens while preserving legacy `read` / `write` / `admin` role tokens.
2. Add harness-persistent install artifacts that can be copied or installed into Codex/Claude/Gemini-style persistent instruction surfaces.
3. Default harness cards to read-first, proposal/append-safe write posture.
4. Direct durable store remains explicit high-authority behavior; operators may mint owner-equivalent tokens, but docs must separate safe defaults from owner tokens.

## Inputs

- Gateway env: `OPENCLAW_MEM_GATEWAY_URL`, `OPENCLAW_MEM_GATEWAY_TOKEN`, `OPENCLAW_MEM_GATEWAY_TOKENS`.
- Existing endpoints: `/v1/status`, `/v1/search`, `/v1/pack`, `/v1/episodes/query`, `/v1/episodes/append`, `/v1/store/propose`, `/v1/store`, `/v1/archive/export-canonical`.
- Existing skill cards under `skills/` and generated docs/snippets.

## Outputs / artifacts

- Gateway token capability parser and status readback.
- Capability-level authorization gates and tests.
- Harness install/contract docs and generated persistent prompt cards.
- Smoke receipt under `.state/openclaw-mem-gateway-smoke/`.

## Invariants

- Token literals never appear in status/smoke/audit receipts.
- Legacy `token:read`, `token:write`, `token:admin`, and single `OPENCLAW_MEM_GATEWAY_TOKEN` keep working.
- Read tokens cannot write.
- Write tokens can append scoped episodes and create proposals, not direct durable store or admin exports.
- Curated durable mutation remains gated by explicit high-authority token and direct-store enablement for this slice.
- Gateway status reports capabilities as safe names only, never filesystem paths or token values.

## Verifier plan

Run:

```bash
uv run pytest tests/test_gateway.py tests/test_agent_memory_skill_assets.py
uv run python scripts/generate_agent_memory_skill_assets.py --check
uv run python tools/gateway_smoke.py
```

Counterfactual checks:

- short/weak tokens fail startup;
- read token append fails;
- capability token with `episodes.append` can append but cannot propose unless granted;
- owner/admin export works, path traversal fails;
- direct store remains blocked unless the explicit direct-store gate is enabled;
- generated skill docs are up to date.

## Rollback

Revert this commit. Runtime rollback is token/config only: rotate/revoke any distributed gateway tokens and restart the sidecar. No OpenClaw gateway restart is required unless an operator separately wired these cards into a live harness.

## Topology/config impact

Changed: remote memory gateway authorization contract and harness-install documentation surfaces.

Unchanged: OpenClaw core gateway topology; no cron/controller activation in this slice.
