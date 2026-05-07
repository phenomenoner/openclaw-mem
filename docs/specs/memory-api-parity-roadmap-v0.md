# Memory API Parity Roadmap v0

Date: 2026-05-08
Line: `openclaw-mem` canonical API parity
Trigger: CK requested that authorized `openclaw-mem` API readers can find the same non-secret information Lyria can find locally.

## Product invariant

Authorized `openclaw-mem` API readers MUST be able to retrieve all non-secret, non-excluded OpenClaw memory that the local Lyria/OpenClaw workspace can retrieve, without needing to understand internal memory surfaces.

Plain-language contract:

> `openclaw-mem API` is the canonical read bridge for shareable OpenClaw memory. A no-result response is only authoritative when the API reports the corpus as parity-healthy for the requested scope.

## Non-goals

- No public network exposure.
- No direct credential/token disclosure.
- No automatic permission expansion for remote harnesses.
- No requirement that every private/local file becomes globally readable.
- No live gateway restart in this implementation slice unless CK/operator performs it.

## Canonical corpus map

Default API-readable corpus, subject to redaction and scope controls:

1. `MEMORY.md` — curated durable memory.
2. `memory/YYYY-MM-DD.md` — daily append-only memory logs.
3. selected bootstrap authority files when configured: `AGENTS.md`, `SOUL.md`, `USER.md`.
4. `openclaw-mem` observations, episodes, proposals, and existing docs chunks.
5. Optional configured docs/project notes.

Default exclusions:

- files/directories outside configured workspace/corpus roots;
- paths or chunks marked `[SECRET]`, `[PRIVATE]`, `[NOEXPORT]`, `[NOMEM]`;
- detected secret-like values unless redacted safely;
- scopes not authorized for the caller/token.

## Phase roadmap

### Phase 0 — Contract

- Document the API parity invariant.
- Document no-result semantics: `result_count=0` means no match only inside the reported corpus/scope.
- Gateway diagnostics/status must expose corpus completeness without leaking literal private paths.

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

- `曦曦`
- `Lady H`
- `Lyria`
- `CK timezone`
- `non-stop`
- `櫻花刀舞`
- `Store Pack Observe`

Verifier rule: if local corpus contains a golden fact and API `/v1/search` or `/v1/pack` misses it while corpus is parity-enabled, the parity smoke fails.

### Phase 5 — Honest gateway status

`/v1/status` should report:

- surface identity / DB fingerprint / workspace fingerprint;
- corpus sources enabled;
- corpus last refresh result;
- indexed/missing/skipped/redacted counts;
- parity health state: `healthy`, `partial`, `disabled`, or `unknown`.

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
uv run openclaw-mem docs ingest --db <temp-db> --path <fixture-workspace>/MEMORY.md --path <fixture-workspace>/memory --no-embed --json
uv run openclaw-mem docs search --db <temp-db> 曦曦 --json
```

Expected acceptance:

- `曦曦` resolves through the API-visible corpus with a source receipt.
- Gateway no-result diagnostics identify corpus/surface rather than implying global absence.
- Status exposes corpus state without literal private paths.
- No secrets or `[NOEXPORT]` chunks appear in API search results.

## Rollback posture

- Docs-only rollback: revert this spec file.
- Code rollback: revert gateway/CLI/tests changes in this line; no DB migration should be destructive.
- Live rollback: stop/restart the gateway with previous package/config only after CK/operator approval.

## Topology/config impact

Planned source behavior changes: yes, gateway read path may include a configured workspace-memory docs corpus.

Live topology change in this slice: unchanged unless CK/operator restarts or redeploys gateway.
