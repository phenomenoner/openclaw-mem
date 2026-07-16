# OpenClaw quickstart

1. Preview: `openclaw-mem install --harness openclaw --root . --dry-run --json`.
2. Install: `openclaw-mem install --harness openclaw --root . --mode write --verify --json`.
3. Reference `.openclaw-mem/agent-memory-card.md` from the harness instruction surface.
4. Diagnose later with `openclaw-mem doctor --harness openclaw --root . --json`.

The managed card uses environment variables for gateway credentials; no token is written.
