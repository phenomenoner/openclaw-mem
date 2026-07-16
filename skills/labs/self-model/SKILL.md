---
name: openclaw-mem-self-model
description: >-
  Inspect and govern the experimental derived self-model sidecar. Use for
  continuity snapshots, attachment maps, drift, threats, public-safe wording,
  release receipts, or migration comparisons.
metadata:
  ring: 2
  surface: [cli]
  version: 1.9.32
  requires: [openclaw-mem-memory]
---

# Self-model Lab

The sidecar is derived, editable, and rebuildable. It is not consciousness, identity truth, or a second memory owner. Never write its claims back into Store truth automatically.

## Workflow

1. Build `current` for a scoped audit point.
2. Inspect attachment and adjudication before release decisions.
3. Check threat feed, explanation, and sensitivity before stronger wording.
4. Run wording lint before continuity-facing copy.
5. Use release only with a concrete operator reason; rebuild current to verify effect.

```bash
openclaw-mem continuity current --scope <scope> --session-id <session> --json
openclaw-mem continuity attachment-map --snapshot <snapshot> --json
openclaw-mem continuity adjudication --snapshot <snapshot> --json
openclaw-mem continuity threat-feed --snapshot <snapshot> --json
openclaw-mem continuity public-summary --snapshot <snapshot> --json
openclaw-mem continuity wording-lint --snapshot <snapshot> --json
openclaw-mem continuity release-history --scope <scope> --session-id <session> --json
```

Persona priors are hints, not sovereignty. If evidence is thin or prior-dominated, report instability instead of inventing certainty. Enable autonomous receipts only when explicitly requested; use the governed soak controller under `<workspace>` for long gates.

## Verify

```bash
openclaw-mem continuity status --json
python -m pytest tests/test_self_model_sidecar.py -q
git diff --check
```
