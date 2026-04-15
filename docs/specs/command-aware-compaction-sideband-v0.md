# Command-aware compaction sideband v0

Status: minimal shipped contract for the first RTK-derived absorption slice.

## Verdict
`openclaw-mem` should treat command-aware compaction as an **Observe-side sideband contract**, not as an invisible replacement for raw command truth.

## Whole-picture promise
When operators or agents compact noisy command output, the system should retain three things at once:
1. the original command intent,
2. a compact view suitable for bounded context,
3. a deterministic pointer back to raw evidence.

## Boundary
This v0 slice does **not** introduce automatic shell hooks, transparent rewrites, or new canonical storage semantics.

It only introduces a receipt contract for pairing compacted output with recoverable raw evidence.

## CLI surface

```bash
openclaw-mem artifact compact-receipt \
  --command "git status" \
  --rewritten-command "rtk git status" \
  --tool rtk \
  --compact-file ./compact.txt \
  --raw-file ./raw.txt \
  --json
```

Or, if raw output is already offloaded:

```bash
openclaw-mem artifact compact-receipt \
  --command "git status" \
  --tool rtk \
  --compact-text "ok main" \
  --raw-handle ocm_artifact:v1:sha256:<64hex> \
  --json
```

## Receipt contract

```json
{
  "schema": "openclaw-mem.artifact.compaction-receipt.v1",
  "createdAt": "2026-04-15T00:00:00+00:00",
  "mode": "sideband",
  "tool": "rtk",
  "command": "git status",
  "rewrittenCommand": "rtk git status",
  "rawArtifact": {
    "handle": "ocm_artifact:v1:sha256:<64hex>",
    "sha256": "<64hex>",
    "bytes": 1234,
    "kind": "tool_output"
  },
  "compact": {
    "text": "ok main",
    "bytes": 7
  },
  "meta": {}
}
```

## Rules
- `command` is required.
- compacted text is required, via `--compact-text` or `--compact-file`.
- raw evidence is required, via `--raw-file` or `--raw-handle`.
- if `--raw-file` is used, the file is stashed via the existing artifact sidecar first.
- compacted text is **not** promoted to durable memory by default.
- the receipt is an Observe artifact, not a Store record.

## Why this shape
- It keeps raw evidence recoverable.
- It preserves explicit provenance when an external compactor rewrites or summarizes output.
- It gives Pack a future contract to consume without forcing shell-hook dependence.

## Non-goals
- automatic command interception
- shell-hook installation
- silent replacement of raw output in prompt surfaces
- tool-specific semantics beyond the generic sideband receipt

## Verification
- parser contract test for `artifact compact-receipt`
- CLI contract test with a stashed raw artifact handle
- local operator smoke using RTK on a real repo command

## Follow-up
- pack trace awareness of compaction receipts
- bounded raw rehydrate helper in pack/observe flows
- command-family-specific compaction policies
