# Gateway retired docs and local enablement receipt - 2026-06-12

## Scope

- Mark legacy gateway documentation as retired so it is not mistaken for the active install path.
- Enable local `openclaw-mem` v1.9.27 through CLI/MCP/Channel A/hooks wrappers.
- Do not enable or rebuild the retired Docker gateway path.

## Active install path

- MCP online tools: `openclaw-mem-mcp`
- Fail-open ContextPack files: `openclaw-mem-channel-a`
- Lifecycle hooks: `openclaw-mem-hooks`

## Legacy/retired path

- `docs/remote-memory-gateway.md`
- `docs/shared-memory-gateway-agent-guide.md`
- `docs/harness-persistent-memory.md`

The gateway code remains in the repository for compatibility and future deprecation work. It is not the active install path.

## Rollback

- Restore `C:\Users\user\.codex\bin\openclaw-mem.cmd` from the timestamped `.bak-*` backup.
- Remove the new wrapper files for `openclaw-mem-mcp.cmd`, `openclaw-mem-channel-a.cmd`, and `openclaw-mem-hooks.cmd` if needed.

## Verification

- Wrapper backup: `C:\Users\user\.codex\bin\openclaw-mem.cmd.bak-20260612-134228`
- Active wrapper source: `D:\Warehouse\Research\Claude_Discuss\OpenClaw-mem\repo-work`
- Active import version: `openclaw_mem.__version__ == 1.9.27`
- Real harness memory DB smoke:
  - `openclaw-mem --db D:\Warehouse\Rust-OpenClaw-Core\.agent-harness\memory\openclaw-mem.sqlite status --json`
  - result: version `1.9.27`, count `63744`
- MCP wrapper smoke:
  - `openclaw-mem-mcp --db D:\Warehouse\Rust-OpenClaw-Core\.agent-harness\memory\openclaw-mem.sqlite --tool-descriptions`
  - result: schema `openclaw-mem.mcp.tools.v1`
- Channel A wrapper smoke:
  - temp DB + fixture ingest wrote `openclaw-mem.context-pack.v1`
  - result: `inserted=2`, `skippedDuplicate=1`, `items=1`
- Hooks wrapper smoke:
  - `openclaw-mem-hooks install-config ...`
  - result: schema `openclaw-mem.lifecycle-hooks.config.v1`

## Notes

- The harness plugin catalog still contains legacy OpenClaw plugin roots from the old imported source tree. That is separate from this v1.9.27 CLI/MCP/Channel A/hooks enablement path.
- The retired Docker gateway was not started, rebuilt, or used.
