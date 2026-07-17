# P1 integration completion receipt

Date: 2026-06-12
Version target: `1.9.27`

## Scope

Completed P1 local implementation for:

- P1-1 MCP server v1
- P1-2 ContextPack v1 compatibility
- P1-3 lifecycle hooks
- P1-4 quickstart integration routes
- P1-5 progressive reveal / token visibility
- P1-6 private marker skipping
- P1-7 CLI UX integration pass
- P1-8 Channel A file contract producer
- P1-9 shared fixtures

## New entrypoints

- `openclaw-mem-mcp`
- `openclaw-mem-channel-a`
- `openclaw-mem-hooks`

## Public docs

- `docs/mcp-integration.md`
- `docs/channel-a-file-contract.md`
- `docs/lifecycle-hooks.md`
- `docs/context-pack.md`
- `docs/quickstart.md`
- `README.md`

## Verification

Focused P1 and contract tests:

```powershell
uv run --python 3.13 --frozen pytest tests/test_mcp_server.py tests/test_channel_a.py tests/test_hooks.py tests/test_context_pack_v1_compat_fixtures.py tests/test_context_pack_golden.py tests/test_json_contracts.py
```

Result:

```text
25 passed
```

Docs build:

```powershell
uv run --python 3.13 --frozen --extra docs mkdocs build --strict
```

Result:

```text
Documentation built
```

Version smoke:

```powershell
uv run --python 3.13 --frozen python -c "import openclaw_mem; print(openclaw_mem.__version__)"
```

Result:

```text
1.9.27
```

CLI smoke:

```powershell
uv run --python 3.13 --frozen openclaw-mem --db :memory: status --json
uv run --python 3.13 --frozen openclaw-mem-mcp --tool-descriptions
uv run --python 3.13 --frozen openclaw-mem-channel-a --db <temp> --input-jsonl docs\fixtures\context-pack-v1-compat\ingest-idempotency.jsonl --packs-dir <temp> --agent main --query "context pack compatibility"
```

Result:

- status reports `openclaw_mem = 1.9.27`
- MCP tool-description manifest emits `openclaw-mem.mcp.tools.v1`
- Channel A writes `openclaw-mem.context-pack.v1`

## Full pytest note

Command:

```powershell
uv run --python 3.13 --frozen pytest
```

Result on this Windows host:

```text
696 passed, 28 failed, 2 skipped
```

Observed failures are existing Windows portability/test-environment surfaces outside the new P1 integration paths, including chmod/mode expectations, symlink privilege, Windows-invalid colon filenames, `killpg`/subprocess timeout behavior, and self-curator/self-model assumptions. The P1-focused surfaces listed above are green.

## Remaining downstream work

- Import `docs/fixtures/context-pack-v1-compat/` into the Rust harness CI/validator so host-side fixture pinning is also green.
- Consider a separate Windows-portability hardening pass for the full-suite residual failures.

## Publication receipt

- main push: `ed22b9d Complete P1 integration surfaces`
- release receipt sync: this commit records the final checklist/backlog publication state
- tag: `v1.9.27`
- GitHub release: <https://github.com/phenomenoner/openclaw-mem/releases/tag/v1.9.27>
