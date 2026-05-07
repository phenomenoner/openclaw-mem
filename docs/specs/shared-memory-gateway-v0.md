# Shared Memory Gateway v0

Status: implementation slice
Owner: openclaw-mem
Date: 2026-05-04

## Goal
Expose a local-first authenticated HTTP gateway for `openclaw-mem` so agents/harnesses in Docker, WSL, and parent Windows can read and append/propose memory through one governed surface.

## Non-goals
- No unauthenticated network service.
- No direct raw SQLite access for external agents.
- No default mutation of authority files (`MEMORY.md`, `AGENTS.md`, `SOUL.md`, `USER.md`).
- No live Gateway/OpenClaw runtime restart in this slice.
- No cross-store migration beyond the existing canonical capsule/export contract.

## API contract
Base path: `/v1`.

Read endpoints:
- `GET /health` — minimal liveness, no memory details.
- `GET /v1/status` — authenticated compact gateway status, including public-safe corpus parity state when configured.
- `POST /v1/search` — authenticated search over observations, with workspace/docs-memory fallback when enabled.
- `POST /v1/pack` — authenticated ContextPack build, with docs-memory fallback when the observation pack is empty.
- `POST /v1/episodes/query` — authenticated scoped episodic query.

Write endpoints:
- `POST /v1/episodes/append` — write-token append-only scoped event.
- `POST /v1/store/propose` — write-token memory proposal as observation; does not mutate authority files.
- `POST /v1/store` — admin-token direct durable store; disabled unless `OPENCLAW_MEM_GATEWAY_ALLOW_DIRECT_STORE=1`.

Portable endpoints:
- `POST /v1/archive/export-canonical` — admin-token wrapper around `openclaw-mem capsule export-canonical`; dry-run default.

## Security invariants
- Default bind host is `127.0.0.1`.
- Service refuses to start without a token unless an explicit insecure dev flag is set.
- Auth uses `Authorization: Bearer <token>`.
- Token roles: `read`, `write`, `admin`.
- Tokens must be long random secrets; weak tokens are rejected at startup and bearer comparison uses constant-time comparison.
- Request body size is capped and JSON `Content-Type` is enforced.
- Shell execution must use argv lists, never shell interpolation.
- Error responses must not print token values or CLI stderr details.
- Status responses expose configuration booleans, not literal DB/workspace paths.
- Corpus status must not claim `healthy` until the configured corpus has been refreshed/indexed successfully; otherwise clients should treat no-result answers as partial.
- API-visible workspace/docs memory excludes chunks tagged `[SECRET]`, `[PRIVATE]`, `[NOEXPORT]`, or `[NOMEM]`, and secret-like chunks.
- Admin export targets are contained under an allowlisted export root.
- Append/proposal writes support `Idempotency-Key` for retry-safe clients, reject same-key/different-payload reuse, and apply a bounded replay TTL.

## Scope and write authority
- Search and pack are read-only and may accept scope hints where the underlying CLI supports them.
- Episodic writes require `scope`, `session_id`, `agent_id`, `type`, `summary`.
- Store proposals require `scope`, `agent_id`, `text`; proposals are audit records, not promoted facts.
- Direct store is admin-only and opt-in because it appends daily memory markdown.

## Verifier plan
1. Start gateway with token on localhost and isolated temp DB.
2. `GET /health` returns ok.
3. Missing auth on `/v1/status` returns 401.
4. Read token can search/status but cannot append/propose.
5. Write token can append episode and create proposal.
6. Direct store is blocked unless explicit allow flag is set.
7. Archive export dry-run returns canonical manifest preview.
8. Negative probes cover flag-like search strings, export path traversal, oversized bodies, direct-store default denial, corpus-status honesty, and token redaction.
9. Unit/smoke artifacts are written under `.state/openclaw-mem-gateway-smoke/`.

## Rollback
- Remove `openclaw_mem/gateway.py`, script entry, docs, and tests.
- No runtime topology or OpenClaw gateway restart is required for rollback.

## Topology/config impact
- Repo behavior changed: new optional HTTP gateway script.
- Live OpenClaw runtime topology unchanged unless operator manually starts this service.
