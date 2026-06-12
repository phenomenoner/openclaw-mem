# Remote Memory Gateway deployment

Status: **LEGACY / RETIRED deployment path**

This Docker/HTTP gateway route is retained for historical compatibility and
rollback reference only. New agent-host integration should use the active P1
surfaces instead:

- stdio MCP: `docs/mcp-integration.md`
- fail-open ContextPack files: `docs/channel-a-file-contract.md`
- lifecycle hooks: `docs/lifecycle-hooks.md`

Do not treat this page as the current install or enablement path unless an
operator explicitly asks for a legacy gateway recovery.

This guide exposes `openclaw-mem` to remote agents without starting a second full OpenClaw instance and without direct SQLite/file access.

## Recommended topology

```text
remote agent/tool
  -> SSH tunnel or Tailscale/WireGuard private route
  -> host 127.0.0.1:18765
  -> openclaw-mem-gateway sidecar container:8765
  -> openclaw-mem Store / Pack / Observe
```

Do **not** expose the gateway directly on a public interface. Keep Docker host publishing as `127.0.0.1:18765:8765` and route remote clients through an operator-controlled tunnel/private mesh.

## What to run

Use the sidecar deployment files under `deploy/docker/`:

- `openclaw-mem-gateway.Dockerfile`
- `compose.gateway.localhost.yml`
- `gateway.env.example`

The compose file is localhost-only by default:

```yaml
ports:
  - "127.0.0.1:18765:8765"
```

The container runs only the `openclaw-mem-gateway` process; it is not a full OpenClaw runtime.

## Token model

`OPENCLAW_MEM_GATEWAY_TOKENS` uses comma-separated `token:role-or-capability` pairs:

```text
read-token:read,write-token:write,admin-token:admin,owner-token:owner
```

Capability-shaped tokens are also supported:

```text
codex-token:read+episodes.append+store.propose,watchdog-token:read
```

Rules:

- use at least 24 characters of entropy per token; 32+ random URL-safe bytes is preferred;
- default remote clients to `read`;
- grant `write` or explicit `episodes.append` / `store.propose` only to selected harnesses that need scoped episodes/proposals;
- keep `admin` and especially `owner` host-local/operator-only;
- `owner` is the only built-in role with `store.direct`; the legacy single-token env remains `admin`, not owner;
- never bake tokens into Docker images or committed files;
- rotate tokens by updating the runtime secret/env and restarting the sidecar.

See [Harness-persistent memory install](harness-persistent-memory.md) for the capability matrix and harness install posture.

Generate example tokens:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32)+':read,'+secrets.token_urlsafe(32)+':write')
PY
```

## Start locally

From the repo root:

```bash
cp deploy/docker/gateway.env.example .env.gateway
# edit .env.gateway with real long tokens
# choose/mount the correct OPENCLAW_MEM_DB path for your installation

docker compose --env-file .env.gateway -f deploy/docker/compose.gateway.localhost.yml up -d --build
```

Health check from the host:

```bash
curl -sS http://127.0.0.1:18765/health
```

Authenticated status:

```bash
curl -sS http://127.0.0.1:18765/v1/status \
  -H "Authorization: Bearer $OPENCLAW_MEM_GATEWAY_TOKEN"
```

`/v1/status` intentionally reports booleans, not literal DB/workspace paths.

For parity-aware deployments, status also includes a public-safe `corpus_status` block. Treat `parity_state=healthy` as the only state where a no-result response is authoritative for the configured corpus. If status reports `partial` or `unknown`, remote clients should say the result is partial rather than claiming the memory is absent.

## Remote access: SSH tunnel

On the remote client:

```bash
ssh -L 18765:127.0.0.1:18765 <operator-host>
export OPENCLAW_MEM_GATEWAY_URL=http://127.0.0.1:18765
export OPENCLAW_MEM_GATEWAY_TOKEN=<read-or-write-token>
```

Then call the API normally:

```bash
curl -sS "$OPENCLAW_MEM_GATEWAY_URL/v1/pack" \
  -H "Authorization: Bearer $OPENCLAW_MEM_GATEWAY_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"current openclaw-mem gateway deployment", "limit":8, "budget_tokens":1200}'
```

Read endpoints search observations first. When workspace memory indexing is enabled but the DB/docs index is empty, stale, or cannot be refreshed from a read-only deployment, `/v1/search` can fall back to a read-only scan of the configured workspace Markdown memory (`MEMORY.md`, `memory/*.md`, `AGENTS.md`, `SOUL.md`, `USER.md`). The fallback is intentionally lexical and deterministic; it is a source-of-truth safety net, not a replacement for the indexed/vector search path.

The Markdown read-through fallback does not write to SQLite. It skips chunks tagged with `[SECRET]`, `[PRIVATE]`, `[NOEXPORT]`, or `[NOMEM]` case-insensitively, and it refuses symlinked Markdown files that resolve outside the configured source roots. Remote clients can detect this path through `diagnostic.searched_routes` / `fallback_attempts` containing `workspace_markdown_readthrough`.

For read-mostly sidecars, the CLI connection path treats SQLite WAL enablement as best-effort and can open read endpoints with a read-only SQLite URI. The gateway should not fail a read request merely because the mounted database or volume refuses a journal-mode switch at request time. Writable deployments still prefer WAL for concurrency; read-only failures during actual schema migration or writes remain real errors.

## Remote access: Tailscale/WireGuard

Preferred for recurring trusted machines:

1. Keep Docker publishing host-local or bind the reverse-proxy side only to the private mesh interface.
2. Restrict firewall/ACLs to known devices.
3. Use role-specific tokens even on the private mesh.
4. Keep admin token off remote clients.

## Write posture

Safe remote write defaults:

- `/v1/episodes/append` for scoped working-memory events;
- `/v1/store/propose` for auditable memory proposals;
- `/v1/store` requires both `OPENCLAW_MEM_GATEWAY_ALLOW_DIRECT_STORE=1` and a token with `store.direct` capability, normally `owner`.

For retrying clients, send `Idempotency-Key` on append/propose requests. Reusing the same key with a different payload is rejected. Idempotency records are bounded by `OPENCLAW_MEM_GATEWAY_IDEMPOTENCY_TTL_SEC` and are stored beside the audit log when configured, otherwise under the configured gateway export/state root.

Audit records are JSONL and written to the configured audit log with token IDs, payload digests, endpoint/action, and result — never raw token values. `OPENCLAW_MEM_GATEWAY_AUDIT_MAX_BYTES` controls simple log rotation.

## Security gates before live remote use

Run the local smoke first:

```bash
uv run python tools/gateway_smoke.py
cat ~/.openclaw/workspace/.state/openclaw-mem-gateway-smoke/gateway_smoke_receipt.json
```

Expected counterfactual checks include:

- health ok;
- missing auth returns 401;
- read token cannot write;
- direct store disabled by default;
- search flag-injection probe does not become CLI help/flag execution;
- export path traversal is blocked;
- oversized payload is rejected;
- status does not disclose literal DB/workspace paths;
- status does not overstate corpus parity before a successful refresh;
- token literals are absent from smoke receipts.

## Public HTTPS / WSS

Public HTTPS reverse proxy and WSS/SSE are deferred surfaces.

Use HTTPS only after the localhost/private-mesh path is proven, and add reverse-proxy request-size limits, IP allowlists, HSTS, structured logs, and a separate security review.

Use WSS/SSE only if a concrete streaming requirement appears. Search, pack, episodes query, append, and proposal flows work over plain HTTPS REST.

## Rollback

```bash
docker compose --env-file .env.gateway -f deploy/docker/compose.gateway.localhost.yml down
```

Then rotate/revoke any tokens that were distributed. No OpenClaw gateway restart is required by this sidecar rollback.
