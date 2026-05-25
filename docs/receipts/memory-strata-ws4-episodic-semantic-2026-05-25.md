# Memory Strata WS4 Episodic Semantic Lane Evaluation — 2026-05-25

Status: **completed / isolated fixture; mechanics pass, overclaim policy needed**  
Companion: `docs/specs/memory-strata-todo-v0.md#ws4--episodic-semantic-lane-evaluation`  
Topology impact: **unchanged** — no live OpenClaw config, cron, slot, session store, production DB, push, or tag changes were made.

## Goal

Evaluate `episodes embed` + `episodes search --mode hybrid` as the episodic semantic lane, explicitly distinct from durable engine hybrid recall.

## Fixture

- SQLite DB: `.tmp/memory-strata-ws4/episodes-semantic-fixture.sqlite`
- Scope: `memory-strata-ws4-fixture`
- Durable artifact: `docs/receipts/artifacts/memory-strata-ws4-episodic-semantic-2026-05-25.json`

## Commands exercised

- `episodes append` for two relevant alpha events and one unrelated beta control.
- `episodes embed --scope` on fixture DB.
- `episodes search --mode lexical --trace` positive query.
- `episodes search --mode hybrid --trace` positive query.
- `episodes search --mode hybrid --trace` negative/counterfactual query.

## Checks

| Check | Result |
|---|---:|
| embed_ok | PASS |
| lexical_positive_finds_alpha | PASS |
| hybrid_positive_finds_alpha | PASS |
| negative_does_not_rank_only_alpha_as_confident | PASS |
| negative_returns_low_score_results_needs_threshold_policy | PASS |

## Key findings

- Embedding worked on isolated fixture rows: embedded `3` rows with model `text-embedding-3-small`.
- Lexical positive query found the intended alpha session.
- Hybrid positive query found alpha, but also returned unrelated beta as a lower-ranked vector candidate.
- Hybrid negative query still returned results with low vector scores. This is not a command failure, but it proves WS4 needs an overclaim/threshold policy before semantic results are treated as strong evidence.

## Score notes

- Positive top vector score: `0.6267191344257868`; RRF: `0.03278688524590164`; lanes: `['fts', 'vector']`.
- Negative top vector score: `0.17757844674300424`; RRF: `0.01639344262295082`; lanes: `['vector']`.

## Boundary notes

- This lane indexes bounded/redacted episodic search text; it is not a new memory type.
- This lane must not auto-promote durable memory.
- Search results are evidence candidates; low-score vector-only hits require policy handling before they influence Pack or Working Set.

## Follow-up for WS8 / WS10

- Add expected-evidence fields and a negative expected-empty/low-confidence probe to the regression fixture.
- Pack traces should expose low-confidence or vector-only episodic candidates as excluded/deprioritized unless explicit policy allows them.

## Closure

WS4 mechanics are complete. Product quality is **not** ready for default behavior changes until a threshold/overclaim policy is defined and reviewed.
