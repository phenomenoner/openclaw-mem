# Self Curator v0 implementation receipt

Date: 2026-05-02

## Changed truth

`openclaw-mem` now has a manual, review-only Self Curator sidecar surface:

```bash
openclaw-mem self-curator skill-review --skill-root <skills-root> --out-root <run-root> --json
```

It scans skill `SKILL.md` files and emits a lifecycle review packet plus a human report. It does **not** mutate scanned skills, memory rows, authority files, runtime config, cron, or gateway topology.

## Artifacts added

- `openclaw_mem/self_curator.py` — deterministic v0 scanner, packet builder, report renderer, artifact writer.
- `tests/test_self_curator.py` — zero-write, artifact, report-citation, and unsafe run-id tests.
- `docs/specs/self-curator-sidecar-v0.md` — blade map / contract.
- `docs/hermes-curator-adoption-review.md` — reviewed Hermes Curator design interpretation.
- README / Advanced Labs docs updated to expose the manual sidecar surface.

## Safety and rollback posture

- Rollback snapshot root: `/root/.openclaw/workspace/.state/self-curator/snapshots/20260502-1907-self-curator/`
- `--run-id` is constrained to a single safe slug component; path traversal is rejected before artifact writes.
- `writes_performed` is fixed at `0` for v0 packets.
- Generated run artifacts are not source-of-truth and are disposable.
- Topology/config impact: **unchanged**. No cron or runtime wiring was enabled.

## Verification receipts

```text
uv run -- python -m py_compile openclaw_mem/self_curator.py openclaw_mem/cli.py
uv run -- python -m unittest tests.test_self_curator -q
```

Result:

```text
Ran 3 tests in 0.004s
OK
```

Counterfactual CLI smoke:

- Synthetic stub skill emitted a `refresh` candidate.
- `review.json` and `REPORT.md` were written under the requested temp out-root.
- `REPORT.md` cites `review.json`.
- Source `SKILL.md` SHA-256 before/after matched.
- Malicious run id `../escape` failed closed.

Source hash receipt:

```text
source_sha256_before=20362aeb5abafc339bae9b1b263ea8c90858b53926bf6c4e55e3c424f1098c90
source_sha256_after=20362aeb5abafc339bae9b1b263ea8c90858b53926bf6c4e55e3c424f1098c90
```

Independent review found one must-fix (`--run-id` traversal), resolved before this receipt.

## Stale-rule sweep

No active rule was found that contradicts the new behavior. Existing advanced-lab posture remains canonical: sidecars may recommend and emit receipts; writer-of-record/apply lanes remain separately governed.

## Clarification after CK correction

CK clarified that the intended product direction is not permanent review-only. Self Curator should be able to directly apply Hermes-curator-like file/config hygiene changes, provided every apply is preceded by a rollback checkpoint and followed by diff/readback/rollback receipts.

Durable correction recorded in `docs/specs/self-curator-apply-capable-v1.md`.

## Follow-up

- Implement checkpointed apply-capable v1: plan → checkpoint → apply → verify → rollback.
- Usage/staleness signals are intentionally deferred until there are first-party usage receipts.
- Cron enablement is intentionally deferred until manual/apply safety is reviewed.
- Memory/dream/authority lifecycle reviews remain future gated expansions, not v0 behavior.
