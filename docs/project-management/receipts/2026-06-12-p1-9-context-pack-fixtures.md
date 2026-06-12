# P1-9 ContextPack fixture lane receipt

Date: 2026-06-12

## Change

Added producer-side shared compatibility fixtures for ContextPack v1 and ingest idempotency.

Files:

- `docs/fixtures/context-pack-v1-compat/README.md`
- `docs/fixtures/context-pack-v1-compat/legal-pack.json`
- `docs/fixtures/context-pack-v1-compat/oversized-pack.json`
- `docs/fixtures/context-pack-v1-compat/missing-field-pack.json`
- `docs/fixtures/context-pack-v1-compat/ingest-idempotency.jsonl`
- `tests/test_context_pack_v1_compat_fixtures.py`

## Decisions encoded

- `openclaw-mem.context-pack.v1` remains the canonical v1 schema id.
- v1 field names and casing remain as shipped.
- Invalid, missing, or oversized packs should fail open or degrade safely in consumers.
- Duplicate observation ids should not create duplicate effective observations.

## Verification

Command:

```powershell
uv run --python 3.13 --frozen pytest tests/test_context_pack_v1_compat_fixtures.py tests/test_context_pack_golden.py
```

Result:

```text
8 passed in 2.39s
```

## Remaining work

P1-9 is `partial-local`, not fully closed. Harness-side CI/validator still needs to import or mirror these fixtures before the cross-project gate is `done`.
