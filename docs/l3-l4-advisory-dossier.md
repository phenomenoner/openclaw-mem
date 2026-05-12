# L3/L4 advisory dossier

`openclaw-mem governed advisory-dossier` turns a mutation plan into an operator-facing approval dossier.

It is advisory-only. It does not apply mutations, publish, tag, push, merge, change OpenClaw core, alter gateway/plugin/cron/model routing, or make L3/L4 auto-applyable.

## Example

```bash
openclaw-mem governed advisory-dossier \
  --plan-file plan.json \
  --allowed-root .state/mutation-framework/sandbox \
  --why-now "The protected surface needs an operator decision" \
  --recommendation "Approve only by opening a separate execution line" \
  --markdown-out dossier.md \
  --json
```

## Policy

- L3 requires human/operator approval before any separate execution line.
- L4 requires explicit CK approval before any separate execution line.
- Approval flags on this command are review context only; they do not approve execution.
- Message delivery or dossier rendering is not approval.
- Any approved execution must be a separate line with rollback and verifier receipts.

## Output

The JSON receipt includes:

- `ok` following the nested apply-review gate result
- `dossier_generated` to distinguish successful report generation from approval
- `risk_class`
- `affected_surfaces`
- `proposed_changes`
- `approval.status`
- `rollback_plan`
- `verifier_plan`
- `artifact_outputs` for optional JSON/Markdown dossier files
- nested `apply_review` receipt

`writes_performed=false` means no target mutation/application occurred; writing the dossier artifact itself is not treated as governed apply.

For L3/L4, the nested apply review remains blocked with `l3_l4_not_auto_applyable`.
