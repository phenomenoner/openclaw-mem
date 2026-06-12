# ContextPack v1 compatibility fixtures

Purpose: shared producer/consumer fixtures for `openclaw-mem` and external hosts such as the Rust harness.

Decision:

- Canonical v1 schema id stays `openclaw-mem.context-pack.v1`.
- v1 field names and casing stay as shipped.
- Consumers may use adapters, but the producer contract should not be renamed in v1.

Fixtures:

- `legal-pack.json`: minimal valid pack that consumers must accept.
- `oversized-pack.json`: structurally valid pack that violates a simple budget guard; consumers should reject or degrade safely.
- `missing-field-pack.json`: invalid pack missing required fields; consumers should fail open.
- `ingest-idempotency.jsonl`: duplicate observation ids for validating idempotent ingest semantics.

Compatibility expectations:

- Missing or invalid pack files must not break the agent turn.
- Oversized packs must not be injected blindly.
- Duplicate ingest ids must not create duplicate effective observations.
- Additive optional fields are allowed; removal or renaming of required v1 fields is not.
