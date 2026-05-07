# Memory API Parity Closure — 2026-05-08

## Changed truth

`openclaw-mem` gateway is now parity-aware for configured workspace Markdown memory: authorized read clients can use `/v1/search` and `/v1/pack` without knowing whether a fact lives in observations or local Markdown memory. A no-result answer is only authoritative when `/v1/status` reports a healthy corpus for that scope.

## What changed

- Added roadmap/spec: `docs/specs/memory-api-parity-roadmap-v0.md`.
- Gateway status now includes `corpus_status` and expanded `surface_identity`.
- Gateway read path can refresh configured workspace memory Markdown (`MEMORY.md`, `memory/`, `AGENTS.md`, `SOUL.md`, `USER.md`) into docs-memory before read requests.
- `/v1/search` falls back from observation search to docs-memory search.
- `/v1/pack` falls back from observation pack to a docs-memory context-pack wrapper.
- Docs-memory ingest skips chunks tagged `[SECRET]`, `[PRIVATE]`, `[NOEXPORT]`, or `[NOMEM]`, and skips secret-like chunks.
- Docs-memory search has a CJK literal fallback, verified with `曦曦`.
- Harness/Codex docs now instruct clients to check `/v1/status` before treating no-result as authoritative.

## Reviews

- Claude M0 roadmap review produced must-fixes around date, authority-file default, corpus exclusions, terminology, precedence, and fixture specificity. These were addressed in the roadmap spec.
- QA minion attempts for roadmap/implementation timed out without usable findings; not counted as approval.
- Claude implementation review attempts timed out without output; not counted as approval.
- Final independent QA retry was launched after implementation closure; incorporate findings if it returns actionable must-fix items.

## Verification receipts

Commands run:

```bash
uv run pytest tests/test_gateway.py tests/test_docs_memory.py tests/test_cli.py tests/test_codex_install.py tests/test_harness.py -q
# 177 passed, 25 subtests passed

uv run python tools/gateway_smoke.py
# gateway_smoke_ok True, failures []
```

Parity fixture receipts:

- `.state/memory-api-parity/fixture-ingest.json`
- `.state/memory-api-parity/fixture-search.json`

Fixture proved:

- `曦曦` is retrievable through docs-memory search.
- `[NOEXPORT]` fixture chunk is skipped.

Gateway smoke receipt:

- `/root/.openclaw/workspace/.state/openclaw-mem-gateway-smoke/gateway_smoke_receipt.json`

## Topology/config impact

- Source behavior changed.
- Live topology unchanged.
- Existing running gateway sidecar will need operator restart/redeploy to pick up this code.

## Rollback

- Revert commits on this line:
  - `1b65217 docs: add memory API parity roadmap`
  - `4b9e0c1 feat: add workspace memory parity bridge`
  - `7a5ed35 docs: clarify gateway memory parity contract`
  - `1a173f0 docs: update harness no-result parity guidance`
- Restart/redeploy gateway with previous package/config if this has already been deployed live.

## Remaining follow-up

- Need CK/operator action to restart/redeploy the actual gateway sidecar when ready.
- Optional future hardening: TTL/change-detection around workspace-memory auto-refresh to avoid scanning large corpora every read request.
