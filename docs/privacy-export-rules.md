# Privacy & Export Rules

## Problem
Auto-exporting learnings to `MEMORY.md` may leak sensitive data (API keys, private conversations, internal context) if done indiscriminately.

## Principles
1. **Explicit consent** — Don't auto-export to long-term memory without user confirmation
2. **Session-aware** — Only export from private/main sessions, never from shared/public sessions
3. **Audit trail** — Log what was exported, when, and by whom

## Rules

### ✅ Safe to Auto-Export (with confirmation)
- Private sessions (`agent:main:main`)
- Isolated sessions spawned by private sessions
- After explicit `/stop` or end-of-day compression

### ❌ Never Auto-Export
- Shared/public sessions (e.g., group chats, external channels)
- Cron jobs (isolated background tasks)
- Sessions labeled `ephemeral`
- Any session with `export_disabled: true` in metadata

### 🔐 Required Flags for Export
All export commands that write to `MEMORY.md` **MUST** require explicit confirmation:

```bash
# ❌ Blocked by default
openclaw-mem export --to MEMORY.md

# ✅ Requires --yes
openclaw-mem export --to MEMORY.md --yes

# ✅ Or interactive prompt (if TTY available)
openclaw-mem export --to MEMORY.md
# → Prompt: "Export 3 summaries to MEMORY.md? [y/N]"
```

### 🚦 Configuration Override
Users can opt-in to auto-export in config:

```json
{
  "openclaw-mem": {
    "autoExport": {
      "enabled": true,
      "sessions": ["agent:main:main"],
      "requireConfirmation": false
    }
  }
}
```

**Default:** `autoExport.enabled = false`

## Export Audit Trail
Every export operation should append a signature line to `MEMORY.md`:

```markdown
## 2026-02-05 Summary
...learnings...

---
_Exported by openclaw-mem v0.1.0 | agent:main:main | 2026-02-05T20:00:00Z_
```

## Redaction Policy (Optional)
Before exporting, scan learnings for sensitive patterns:

- API keys: `sk-[a-zA-Z0-9]{32,}`
- Tokens: `Bearer [a-zA-Z0-9]+`
- Secrets: marked with `[REDACTED]` tags

Add a `--redact` flag for manual runs:

```bash
openclaw-mem export --to MEMORY.md --yes --redact
```

## Implementation Checklist
- [ ] Add `--yes` / `--force` flags to `export` command
- [ ] Check session metadata for `export_disabled`
- [ ] Add audit signature line to exports
- [ ] Add config schema for `autoExport`
- [ ] Implement redaction scanner (Phase 2+)

## Testing
```bash
# Should fail without --yes
openclaw-mem export --to /tmp/test-memory.md
# → Error: "Export to MEMORY.md requires --yes flag"

# Should succeed
openclaw-mem export --to /tmp/test-memory.md --yes
# → Success: "Exported 3 summaries to /tmp/test-memory.md"
```

## Future: Consent UI
For GUI/web dashboard:
- Show preview of what will be exported
- Checkbox: "Include session XYZ"
- Confirm button with audit log display
