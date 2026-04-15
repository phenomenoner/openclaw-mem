# openclaw-mem v1.6.0

Release date: 2026-04-15
Compare: `v1.5.1...v1.6.0`

## Headline

This release strengthens the **Store / Pack / Observe** product surface in two ways:
- it reframes live-turn bounded recall as **Proactive Pack** on the public surface,
- it ships the first **command-aware compaction** lane with bounded raw recovery and auditable pack behavior.

## What changed since v1.5.1

### 1. Proactive Pack is now the public runtime story
- mem-engine live-turn recall is framed consistently as **Proactive Pack**
- plugin metadata, docs, and skill-card surfaces now tell the same story
- the write-authority boundary is clearer: mem-engine remains the canonical active-slot durable-memory owner when enabled

### 2. Command-aware compaction is now a shipped Observe lane
- new `openclaw-mem artifact compact-receipt`
- new `openclaw-mem artifact rehydrate`
- `pack` can prefer compact command text while preserving raw recovery through artifact handles
- `pack` and trace outputs now expose:
  - `compaction_sideband`
  - `compaction_policy_hints`
- lightweight family tags are now attached advisory-only:
  - `git_diff`
  - `test_failures`
  - `long_logs`
  - `generic`

### 3. Public proof surface is stronger
- new command-aware compaction proof
- synthetic showcase artifacts for `git_diff`
- synthetic showcase artifacts for `test_failures`
- new `compaction-family-policy-cards-v0` operator-facing spec

### 4. External docs and skill cards were updated
- README / QUICKSTART now include the minimal operator path
- docs index now links the compaction proof directly
- agent-memory skill surfaces now tell agents to treat compact text as orientation-first and raw artifacts as the exact-evidence lane

## Why this release matters

`openclaw-mem` is now better at keeping prompts small **without lying about evidence**.

Compact command output becomes usable in Pack, but it does not silently replace raw truth.
That keeps the product cheaper, more navigable, and still auditable.

## Suggested release bullets
- Proactive Pack is now the public-facing runtime recall story
- Shipped command-aware compaction receipts + bounded rehydrate
- Pack now emits advisory family-level compaction policy hints
- Added public-safe proofs for `git_diff` and `test_failures`
