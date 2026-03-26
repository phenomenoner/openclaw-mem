# Advisory lane status

## Standalone Claude CLI
- Earlier bad path:
  - `claude --permission-mode bypassPermissions --print ...`
  - result: rejected under root/sudo because Claude mapped it to the dangerous-permissions path
- Additional trap discovered:
  - `--bare` disables normal claude.ai login reuse, so a bare one-shot run can look falsely auth-broken on this host
- Working posture:
  - `claude --print --model opus --no-session-persistence --tools ""`
- Latest result:
  - smoke test succeeded (`CLAUDE_OK`)
  - advisory run completed successfully after re-login and after removing the old bad flags/posture
- Interpretation:
  - the original permission-guidance bug is materially cleared
  - the lane is usable again when invoked with the non-bypass, non-bare posture
- Operational note:
  - for this host, prefer non-bypass one-shot Claude and avoid treating `--bare` + login-backed auth as a neutral flag combination

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
