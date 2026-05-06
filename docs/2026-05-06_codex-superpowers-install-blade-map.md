# Codex Superpowers-style openclaw-mem install blade map

Status: implementation slice
Date: 2026-05-06

## Goal

Upgrade `openclaw-mem` Codex install from instruction-card-only posture into a verifiable install surface that behaves closer to a Superpowers-style persistent capability:

- global Codex card install, not only workspace-local `AGENTS.md`;
- environment/config checks;
- gateway live smoke;
- generated CLI shim instructions/artifact;
- generated MCP/server config artifact when requested/available;
- `doctor` command that proves the installed surface is present and the gateway is reachable with the expected role.

## Non-goals

- Do not claim an official Codex plugin API exists unless Codex documents/provides one.
- Do not write raw gateway tokens to instruction files, docs, receipts, or git-tracked files.
- Do not enable direct durable store.
- Do not mutate Windows user environment from Linux/WSL automatically; emit exact commands and verify what can be verified from the current host.
- Do not merge unrelated extension state-dir fallback changes.

## Inputs

- Codex home / global instruction root, defaulting to `~/.codex` or an explicit `--codex-home`.
- Gateway URL, defaulting to `OPENCLAW_MEM_GATEWAY_URL` or `http://127.0.0.1:18765` for the upper-system production mapping.
- Token from env only (`OPENCLAW_MEM_GATEWAY_TOKEN`) for live doctor; never from CLI arg.
- Desired mode (`read`, `write`, `owner`) and expected role.
- Scope and agent_id defaults: `openclaw-mem`, `codex-windows`.

## Outputs / artifacts

- Managed global Codex `AGENTS.md` block.
- Install receipt JSON.
- Doctor receipt JSON.
- Optional markdown install bundle with PowerShell env commands and smoke commands.
- Optional MCP config candidate JSON that references env vars, not raw tokens.

## Invariants

- No token literals written to card/docs/receipts.
- `write` remains proposal/episode only; `/v1/store` is not used by installer/doctor.
- Existing human content outside managed markers is preserved.
- Dry-run default for mutating install.
- `doctor` fails closed when gateway URL points at the wrong service or token role does not match.

## Topology/config impact

- Repo CLI/docs behavior changes.
- No live cron/gateway topology change in this slice.
- If later installed on Windows, Codex global config/instruction topology changes outside this repo; installer must produce receipts and rollback instructions.

## Verifier plan

- Unit tests for global Codex target path, dry-run no-write, no-token card, wrong-service doctor failure, role mismatch failure, and success with mocked gateway.
- CLI smoke for `openclaw-mem codex install --dry-run --json` and `openclaw-mem codex doctor --json` against a local fake gateway.
- MkDocs strict build after docs updates.
- `git diff --check`.

## Rollback

- Remove managed block between `OPENCLAW_MEM_HARNESS` markers from Codex global `AGENTS.md`.
- Delete generated install bundle/MCP candidate files.
- Unset Windows user env vars if installed persistently.
- Revert this repo commit.
