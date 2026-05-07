# Memory API Parity Roadmap v0

Date: 2026-05-08
Line: `openclaw-mem` canonical API parity
Trigger: operators need authorized `openclaw-mem` API readers to find the same non-secret configured memory that local agents can find, without learning internal storage surfaces.

## Product invariant

Authorized `openclaw-mem` API readers MUST be able to retrieve all non-secret, non-excluded configured OpenClaw memory that local agents can retrieve, without needing to understand internal memory surfaces.

Plain-language contract:

> `openclaw-mem API` is the canonical read bridge for shareable OpenClaw memory. A no-result response is only authoritative when `/v1/status` reports `corpus_status.parity_state = "healthy"` for the requested scope.

## Non-goals

- No public network exposure.
- No direct credential/token disclosure.
- No automatic permission expansion for remote harnesses.
- No requirement that every private/local file becomes globally readable.
- No live gateway restart in this implementation slice unless the operator performs it.

## Canonical corpus map

Default API-readable corpus, subject to redaction and scope controls:

1. `MEMORY.md` — curated durable memory.
2. `memory/YYYY-MM-DD.md` — daily append-only memory logs.
3. selected bootstrap authority files by default for owner/workspace-local API surfaces: `AGENTS.md`, `SOUL.md`, `USER.md`. Remote/shared read tokens may receive a narrower configured corpus, but status must then report `partial`, not `healthy`.
4. `openclaw-mem` observations, episodes, proposals, and existing docs chunks.
5. Optional configured docs/project notes.

Explicitly excluded from v0 parity unless separately configured: raw session transcripts, tool stdout/stderr artifacts, `.state/` scratch receipts, repo internals, and project notes outside the configured corpus roots. Reason: these are not stable memory surfaces, may contain secrets or incidental private content, and need their own redaction/retention policy before being part of the canonical API bridge.

Conflict precedence when multiple sources disagree:

1. workspace authority files (`AGENTS.md`, `SOUL.md`, `USER.md`, `MEMORY.md`);
2. daily memory logs (`memory/YYYY-MM-DD.md`), newest relevant entry wins unless an authority file overrides;
3. curated observations/proposals;
4. episodes and docs chunks.

Default exclusions:

- files/directories outside configured workspace/corpus roots;
- paths or chunks marked `[SECRET]`, `[PRIVATE]`, `[NOEXPORT]`, `[NOMEM]`;
- detected secret-like chunks are skipped in v0; future redaction may preserve non-secret surrounding text only after a dedicated verifier proves it safe;
- scopes not authorized for the caller/token.

Authorization model for v0: token-bound, localhost/private-route only, role/capability gated by the existing gateway token model. `read` tokens can search/pack the configured shareable corpus; private/scoped corpus expansion requires an explicit higher-scope configuration and must be visible in `/v1/status`.

## Phase roadmap

### Phase 0 — Contract

- Document the API parity invariant.
- Document no-result semantics: `result_count=0` means no match only inside the reported corpus/scope.
- Gateway diagnostics/status must expose corpus completeness without leaking literal private paths. Phase 5 owns the detailed status schema; Phase 0 owns the contract that no-result semantics depend on that status.

### Phase 1 — Canonical corpus map

- Add a deterministic default list for workspace memory files/directories.
- Preserve source metadata: path label, repo/path, line/chunk identity, source kind, redaction status.

### Phase 2 — Ingestion/index bridge

- Reuse docs-memory markdown indexing as the bridge for workspace memory Markdown.
- Gateway may auto-refresh configured memory corpus before read requests when enabled.
- Reads must be idempotent and safe: no authority-file mutation, no external writes.

### Phase 3 — Redaction / permission layer

- Apply deny tags and secret-like scanners before API exposure.
- Default remote tokens to read-only.
- Future extension: token capability gates for private/scoped corpora.

### Phase 4 — Search parity tests

Golden query fixture set:

- `alpha memory alias`
- `project steward`
- `operator timezone`
- `handoff decision`
- `non-stop`
- `automation trigger`
- `Store Pack Observe`

Verifier rule: if local corpus contains a golden fact and API `/v1/search` or `/v1/pack` misses it while `corpus_status.parity_state = "healthy"`, the parity smoke fails.

Corpus discovery verifier: compare the configured workspace Markdown source set (`MEMORY.md`, `memory/*.md`, default authority files) against indexed `docs_chunks` source paths. If any configured readable source is absent and not explicitly skipped/redacted, status must be `partial` or the smoke fails.

### Phase 5 — Honest gateway status

`/v1/status` should report:

- surface identity / DB fingerprint / workspace fingerprint;
- corpus sources enabled;
- corpus last refresh result;
- indexed/missing/skipped/redacted counts;
- parity health state: `healthy`, `partial`, or `unknown`.

### Phase 6 — External harness contract

Codex/Claude/Windows-side clients should follow this rule:

- Ask `openclaw-mem` API first for memory questions.
- If status says corpus parity is not healthy, say the answer is partial rather than saying memory is absent.
- Treat `/v1/search` and `/v1/pack` source receipts as the user-facing evidence.

## Verifier plan

Minimum verifier commands for this line:

```bash
uv run pytest tests/test_gateway.py tests/test_docs_memory.py tests/test_cli.py
uv run python tools/gateway_smoke.py
```

Additional parity fixture smoke:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/ws/memory"
printf '# Memory\n\nOperator timezone: UTC.\n' > "$tmp/ws/MEMORY.md"
printf 'alpha memory alias = project steward.\n' > "$tmp/ws/memory/2026-05-07.md"
printf '[NOEXPORT] hidden fixture.\n' > "$tmp/ws/memory/2026-05-06.md"
uv run openclaw-mem docs ingest --db "$tmp/mem.sqlite" --path "$tmp/ws/MEMORY.md" --path "$tmp/ws/memory" --no-embed --json
uv run openclaw-mem docs search --db "$tmp/mem.sqlite" "alpha memory alias" --json
```

Expected acceptance:

- `alpha memory alias` resolves through the API-visible corpus with a source receipt.
- Gateway no-result diagnostics identify corpus/surface rather than implying global absence.
- Status exposes corpus state without literal private paths.
- No secrets or `[NOEXPORT]` chunks appear in API search results.

## Rollback posture

- Docs-only rollback: revert this spec file.
- Code rollback: revert gateway/CLI/tests changes in this line; no DB migration should be destructive.
- Live rollback: stop/restart the gateway with previous package/config only after operator approval.

## Topology/config impact

Planned source behavior changes: yes, gateway read path may include a configured workspace-memory docs corpus.

Live topology change in this slice: unchanged unless the operator restarts or redeploys gateway.
