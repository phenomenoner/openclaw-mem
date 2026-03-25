# Advisory lane status

## Standalone Claude CLI
- Intended posture:
  - `claude --print --model opus --permission-mode bypassPermissions --bare --no-session-persistence --tools ""`
- Result:
  - failed before content generation
  - host returned: `--dangerously-skip-permissions cannot be used with root/sudo privileges for security reasons`
- Interpretation:
  - this local Claude lane still has a host/config posture issue that injects or implies dangerous-permissions behavior even in a read-only advisory call
- Operational note:
  - do not pretend this lane is healthy until the host-side permission posture is actually repaired

## Standalone Gemini CLI
- First attempt:
  - default Pro lane hit repeated `429 RESOURCE_EXHAUSTED` / `MODEL_CAPACITY_EXHAUSTED`
- Fallback:
  - switched to `gemini-2.5-flash`
  - advisory call completed successfully
- Main useful takeaways:
  1. the four-part failure model is the strongest framing
  2. cost/complexity tradeoffs should be made explicit
  3. user control + explainability need more emphasis
  4. adaptive personalization over time is a missing angle
  5. series spine should revolve around **strategic silence**, not raw recall
