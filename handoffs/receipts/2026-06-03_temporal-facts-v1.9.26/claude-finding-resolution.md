# Claude finding resolution - temporal facts v1.9.26

Claude review receipt: `handoffs/receipts/2026-06-03_temporal-facts-v1.9.26/claude-phase-review.md`

## Resolved

1. `source_confidence_cap` duplicate/inversion risk
   - Resolution: source refs are de-duped by token before cap calculation.
   - Resolution: any resolved receipt source keeps the strongest `operator_asserted` cap; two distinct non-receipt sources can cap at `corroborated`.
   - Counterfactual test: duplicate `doc:source.md` refs cannot inflate a fact to `corroborated`.

2. Single-value conflicts only linted after assertion
   - Resolution: `assert_fact` now rejects overlapping active facts for single-valued predicates unless the new fact explicitly `--supersedes` the old one.
   - Counterfactual test: overlapping `status` assertion fails with `single_value_interval_conflict`; the same assertion succeeds with `--supersedes`.

3. ContextPack citations omitted evidence source refs
   - Resolution: emitted ContextPack items now include `assertionRef` and `evidenceSourceRefs` extension fields in addition to the existing v1 citation field.
   - Counterfactual test: fact pack output exposes `context_pack.items[0].evidenceSourceRefs`.

4. Empty `graph fact propose` input
   - Resolution: CLI returns structured error `missing_proposal_input` with exit code 2 when neither `--text` nor `--file` supplies text.
   - Counterfactual test: empty propose smoke asserts code 2 and structured issue.

5. `rebuild --allow-dangling-source` doc exception
   - Resolution: public docs and ops skill now state this is fixture/backfill-only, not normal operator assertion behavior.

## Verifier after resolution

- `uv run pytest tests/test_graph_facts.py` -> 7 passed
- `uv run pytest tests/test_graph_facts.py tests/test_graph_query_cli.py tests/test_context_pack_golden.py tests/test_graph_match_cli.py` -> 28 passed
- `uv run python -m py_compile openclaw_mem/graph/facts.py openclaw_mem/cli.py tests/test_graph_facts.py` -> passed
- `git diff --check` -> passed
- `uv run --extra docs mkdocs build --strict` -> passed

## Remaining known v0 limits

- Extraction proposals are intentionally heuristic and review-only.
- `ContextPackV1` has only one native citation slot, so `evidenceSourceRefs` is emitted as a forward-compatible extension field.
- No Gateway, cron, backend, prompt-injection, or runtime topology change.
