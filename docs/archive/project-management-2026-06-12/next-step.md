# Next step control file

Updated: 2026-06-12

## Verdict

P1 implementation is complete in this repo. Next step is full verification, public-facing hygiene review, then commit/push/tag.

## Current focus

| Order | Item | Status | Why now |
|---:|---|---|---|
| 1 | Full P1 verification | active | Run focused tests, broader pytest, docs build, and CLI smoke. |
| 2 | Public-facing hygiene review | ready | README/quickstart/docs surfaces should describe the new integration entrypoints without internal project-management leakage. |
| 3 | Commit, push, tag | ready-after-verification | Use gh/git workflow after validation is green. |

## Resolved decisions

- P1-2 schema id: keep `openclaw-mem.context-pack.v1` as canonical for v1. Harness compatibility should be proven with shared fixtures/adapters, not by renaming the shipped schema.
- P1-2 field casing: preserve the shipped v1 field names and casing. Any strict cleanup belongs in additive fields or a future v2.
- P0-3 PyPI/package naming: keep `openclaw-context-pack` as the distribution name because `openclaw-mem` is already taken. Continue using `openclaw-mem` as the CLI/import-facing product name where currently shipped.

## Completed local slices

P1-1/P1-3/P1-8 integration entrypoints:

- `openclaw-mem-mcp`
- `openclaw-mem-hooks`
- `openclaw-mem-channel-a`

Tests:

- `tests/test_mcp_server.py`
- `tests/test_hooks.py`
- `tests/test_channel_a.py`

P1-9 producer-side fixture lane:

- legal pack fixture added
- oversized pack fixture added
- missing-required-field fixture added
- ingest idempotency fixture added
- local validator notes added
- local producer-side tests added

Files:

- `docs/fixtures/context-pack-v1-compat/README.md`
- `docs/fixtures/context-pack-v1-compat/legal-pack.json`
- `docs/fixtures/context-pack-v1-compat/oversized-pack.json`
- `docs/fixtures/context-pack-v1-compat/missing-field-pack.json`
- `docs/fixtures/context-pack-v1-compat/ingest-idempotency.jsonl`
- `tests/test_context_pack_v1_compat_fixtures.py`

Verification:

- `uv run --python 3.13 --frozen pytest tests/test_context_pack_v1_compat_fixtures.py tests/test_context_pack_golden.py`
- Result: 8 passed.

Receipt:

- `docs/archive/project-management-2026-06-12/receipts/2026-06-12-p1-9-context-pack-fixtures.md`

External follow-up:

- Import these fixtures into harness-side CI/validator so the host project also pins the same contract.

## HTML checklist

Human-readable progress mirror:

- `docs/archive/project-management-2026-06-12/progress-checklist.html`

Whenever `phase-backlog.md` or this file changes status, update the HTML checklist in the same slice.

## Parking lot

- P0-1 labs freeze and legacy gateway retirement is important, but it should not precede the ContextPack compatibility gate.
- P2/P3 benchmark and governance work should wait until P0/P1 contract risk is reduced.
