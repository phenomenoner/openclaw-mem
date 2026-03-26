# Advisory lane status

## Standalone Claude CLI
- Earlier bad path:
  - `claude --permission-mode bypassPermissions --print ...`
  - result: rejected under root/sudo because Claude mapped it to the dangerous-permissions path
- Current corrected posture:
  - `claude --print --model opus --bare --no-session-persistence --tools ""`
- Latest result:
  - permission posture no longer blocked the run first
  - current blocker is now auth state: `Not logged in · Please run /login`
- Interpretation:
  - the original permission-guidance bug is materially cleared
  - standalone Claude CLI is still **not presently usable** for this lane until login/auth is restored
- Operational note:
  - stop here and report; do not keep retrying standalone Claude until auth is fixed

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
