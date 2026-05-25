# Memory Strata WS3 Episodic Posture Review — 2026-05-25

Status: **completed / isolated fixture**  
Companion: `docs/specs/memory-strata-todo-v0.md#ws3--episodic-memory-posture-review`  
Topology impact: **unchanged** — no live OpenClaw config, cron, slot, session store, production DB, push, or tag changes were made.

## Goal

Verify episodic memory posture on a tiny isolated fixture before evaluating episodic semantic retrieval or pack traces.

## Fixture

- SQLite DB: `.tmp/memory-strata-ws3/episodes-fixture.sqlite`
- Scope: `memory-strata-ws3-fixture`
- Session: `ws3-fixture-session-001`
- Durable artifact: `docs/receipts/artifacts/memory-strata-ws3-episodic-fixture-2026-05-25.json`

## Commands exercised

- `episodes append` for user and assistant fixture rows.
- `episodes query` without payload.
- `episodes query --include-payload`.
- `episodes replay` without payload.
- `episodes search --mode lexical --trace`.
- `episodes redact --session-id --scope`.
- `episodes gc --scope` with fixture-only zero-day policy.
- Counterfactual `episodes append` with explicit fake secret-like payload.

## Checks

| Check | Result |
|---|---:|
| query_no_payload_hides_secret_marker | PASS |
| query_with_payload_contains_secret_marker | PASS |
| redact_clears_secret_marker | PASS |
| search_lexical_ok | PASS |
| gc_ok | PASS |
| explicit_secret_like_payload_rejected | PASS |

## Key findings

- Summary-only query hides raw payload content by default.
- Explicit `--include-payload` reveals fixture payload, proving the counterfactual is meaningful.
- Redaction removes the fixture payload marker from subsequent include-payload query output.
- Lexical episodic search works on the isolated scope.
- Fixture-scoped GC executes successfully.
- Explicit secret-like payload is rejected without `--allow-tool-output`.

## Safety / boundary notes

- This review used an isolated SQLite DB under `.tmp`, not the production OpenClaw memory DB.
- Fixture scope was explicit; no global/live session queries were mutated.
- Redact and GC were scoped to the fixture DB and fixture scope only.
- The first fake marker string used for payload-gate testing was intentionally not a detector-shaped secret; the separate `access_token=sk-...` counterfactual proved the secret-like rejection path.

## Closure

WS3 is complete for Milestone 2. Its fixture pattern is safe to reuse for WS4 episodic semantic evaluation and WS8 pack trace checks.
