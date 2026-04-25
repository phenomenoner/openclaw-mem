# Recall accuracy investigation case, 2026-04-25

## Trigger
CK reported that memory recall feels less accurate than before and asked to open a case rather than treating the misses as isolated incidents.

## Symptom
- Recall sometimes returns stale or adjacent context when the active workstream has shifted.
- Recent example: the assistant continued an `openclaw-mem` landing-page path after CK intended the `KeepClose` project.
- Injected recall snippets may include route hints and transcript hits, but they do not always resolve the canonical active repo/project without additional grounding.

## Initial hypotheses
1. **Project disambiguation weakness**: recall returns plausible adjacent artifacts, but the runtime does not force a canonical repo check before acting.
2. **Graph/transcript skew**: route hints suggest transcript recall is compensating for graph-unready or sparse graph state, which can overweight old summaries.
3. **Recency vs authority mismatch**: compacted summaries and memory hits can carry older branch/repo assumptions unless verified against current filesystem/git truth.
4. **Missing evaluation harness**: there is no small regression set for recall prompts like project routing, branch strategy, and active deployment surface.

## Investigation plan
- Build a minimal recall regression table with prompts, expected canonical project/repo, and acceptable evidence.
- Compare `memory_recall` hits against local repo truth and compacted-session summaries.
- Add a pre-action grounding rule for ambiguous project names: resolve repo path + branch + remote before editing.
- Capture false positives and stale recalls as fixtures for future evals.

## Acceptance criteria
- At least 10 representative recall/routing probes are recorded.
- Each probe has expected answer, observed recall, and failure mode.
- A small operator-facing guardrail is added so ambiguous repo/project work starts with a canonical path check.
- Findings are summarized with whether the issue is recall index quality, prompt/routing behavior, or stale memory hygiene.

## Status
Opened. No memory-store mutation performed by this case file itself.
