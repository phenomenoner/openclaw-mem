# LongMemEval_s retrieval slice

This is a small retrieval-only proof using the public [`LongMemEval`](https://github.com/xiaowu0162/LongMemEval) `longmemeval_s.json` split.

It is not a leaderboard claim. It is a product-facing sanity check for one question:

> Can openclaw-mem retrieve the right source sessions from a long conversational haystack when scored against session-level gold labels?

## Setup

- Dataset variant: `longmemeval_s.json`
- Sample size: 20 examples
- Sampling goal: mixed `question_type` coverage
- Ingestion unit: one haystack session per retrievable episodic event
- Query: question text only
- Gold labels: `answer_session_ids`
- Metrics: session recall@1 / recall@3 / recall@5 and MRR

Question-type distribution:

| question_type | examples |
| --- | ---: |
| knowledge-update | 4 |
| multi-session | 4 |
| single-session-assistant | 3 |
| single-session-preference | 3 |
| single-session-user | 3 |
| temporal-reasoning | 3 |

## Results

| lane | recall@1 | recall@3 | recall@5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| lexical session baseline | 0.80 | 0.85 | 0.85 | 0.8375 |
| openclaw-mem raw FTS | 0.70 | 0.85 | 0.95 | 0.7950 |
| openclaw-mem vector | 0.65 | 0.90 | 0.90 | 0.7583 |
| openclaw-mem hybrid | **0.80** | **0.95** | **1.00** | **0.8767** |

The useful signal is the shape, not the headline number: raw FTS is a reasonable negative/control lane, vector helps at recall@3, and hybrid gives the best overall recall and MRR on this slice.

## What this proves

- The `longmemeval_s.json` schema is usable for session-level retrieval testing because it exposes `answer_session_ids`.
- openclaw-mem can run a local retrieval-only harness over a bounded LongMemEval_s slice.
- The hybrid retrieval path beats a simple lexical session baseline on recall@3, recall@5, and MRR for this slice.

## What this does not prove

- It does not prove full LongMemEval performance.
- It does not score answer generation or QA correctness.
- It does not claim the 20-example slice is statistically representative.
- It does not compare against tuned external retrieval systems.

## Artifact

Machine-readable metrics:

- [LongMemEval_s 20-example retrieval comparison](artifacts/longmemeval-s-20-retrieval-comparison.json)

## Harness safety note

During harness development, a CLI provenance issue was found: for nested `episodes` commands, `--db` must be passed after the final action subcommand, for example:

```bash
openclaw-mem episodes embed --db ./isolated.sqlite --json
```

The unsafe shape below can be overwritten by nested parser defaults and should not be used for isolated benchmark harnesses:

```bash
openclaw-mem episodes --db ./isolated.sqlite embed --json
```

The final harness used action-local `--db` arguments and checked every embedding receipt against the persisted row delta in the same SQLite file.
