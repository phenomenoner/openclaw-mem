# Evaluator path

Use this page when you want the shortest honest route through `openclaw-mem`.

## If you have 5 minutes

Goal: prove the core mechanism on synthetic memory only.

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked
uv run --python 3.13 --frozen -- \
  python benchmarks/trust_policy_synthetic_proof.py --json
```

Expected result:

- `passed: true`
- one quarantined row selected by vanilla packing is excluded by trust-aware packing
- selected rows keep citation coverage
- the trust policy explains the exclusion reason

Read next: [Trust-policy synthetic proof](showcase/trust-policy-synthetic-proof.md).

## If you have 30 minutes

Goal: decide whether the sidecar-first adoption path fits your operator workflow.

1. Run the [trust-policy synthetic proof](showcase/trust-policy-synthetic-proof.md).
2. Run the [60-second reality proof](reality-check.md).
3. Read [Core vs Advanced Labs](core-vs-advanced-labs.md).
4. Read [Choose an install path](install-modes.md).
5. Skim [Automation status](automation-status.md) so you know what is automatic, opt-in, partial, or roadmap.

Decision point:

- If you only need a short chat memory, stop here.
- If you need inspectable agent memory with citations and rollback posture, try the sidecar path.
- If you need live-turn recall orchestration, evaluate the optional mem engine after sidecar proof.

## If you have one afternoon

Goal: evaluate whether `openclaw-mem` belongs in a real OpenClaw operator stack.

1. Run the 5-minute proof and save the JSON receipt.
2. Install the sidecar using [Quickstart](quickstart.md) and [Install modes](install-modes.md).
3. Ingest a small sanitized test memory file, not production memory.
4. Run `search`, `timeline`, `get`, and `pack` on 3–5 realistic questions.
5. Inspect citations and trace receipts for at least one expected include and one expected exclude.
6. Only then consider optional mem-engine promotion.

Keep Advanced Labs out of the first evaluation unless your use case explicitly needs them.
