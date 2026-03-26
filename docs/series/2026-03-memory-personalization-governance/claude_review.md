# Claude CLI review (compressed receipt)

Source lane:
- standalone `claude` CLI
- model: `opus`
- mode: one-shot advisory / tools disabled / no session persistence
- working posture: `claude --print --model opus --no-session-persistence --tools ""`

## Strongest points
- The four-part failure model (write / classify / retrieve / surface) is the real contribution.
- The retention vs activation distinction is the strongest unique angle.
- Consolidation producing candidates instead of silently rewriting canonical memory is a careful and defensible design position.

## Weakest points
- Karpathy's quote is a good hook but too ambiguous to carry the whole mechanism alone.
- `salience estimation` needs operational meaning; otherwise it reads as hand-waving.
- The `openclaw-mem` evidence section can drift into feature inventory rather than proof.

## Missing angles
- context-window / attention competition is architectural, not metaphorical
- privacy / adversarial spillover from overeager memory surfacing
- operator memory vs end-user memory need different policies
- the baseline counterfactual: what do we lose if persistent memory is simply off?
- explicit forgetting / deletion / right-to-forget

## Most useful series changes
- open with a concrete failure, then use Karpathy as confirmation rather than as the sole premise
- make Part 2 more explicitly organized by failure mode addressed
- make Part 3 more honest about where concrete before/after evidence is still missing
- lead Part 4 with the evaluation problem: how do we know memory helped, given the user never sees the counterfactual?

## Sharpest line from Claude
- `A correct recall that the user didn't ask for is indistinguishable from a wrong recall.`

## Thesis sentence
Persistent memory in LLMs fails not because systems remember too much, but because they lack the restraint to stay silent when remembering is irrelevant — and fixing this requires treating retrieval gating and surfacing policy as first-class design problems, not afterthoughts to storage.
