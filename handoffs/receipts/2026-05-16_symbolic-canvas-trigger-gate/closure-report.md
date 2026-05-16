# Symbolic Canvas Trigger Gate — Closure Report

## Question
Will a long skill/tool payload trigger `symbolicCanvas.autoBuild` unnecessarily?

## Finding
In v1.9.19, the hook did not inspect skill/tool content directly, but it was too broad: any successful eligible `agent_end` could produce a canvas once enough user/assistant messages existed.

## Change
v1.9.20 adds `symbolicCanvas.autoBuild.triggerMode`:

- `qualified` (default): run only when recent user/assistant text contains handoff/closure/checkpoint/subagent/verifier-style trigger terms.
- `always`: explicit opt-in to the previous broad every-eligible-agent-end behavior.

The trigger scanner ignores `system` and `tool` roles, so long `SKILL.md` content by itself does not qualify a run.

## Evidence
- `counterfactual-skill-heavy-skip.json`: long system/tool skill payload with routine user/assistant text returns `skipReason=not_qualified`.
- `qualified-handoff-receipt.json`: handoff/checkpoint turn writes JSON/Mermaid receipts.
- Node tests cover trigger qualification and `always` compatibility.
