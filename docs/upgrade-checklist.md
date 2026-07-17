# Upgrade an existing local agent to openclaw-mem v2

Use this checklist when a local Codex, Claude Code, OpenClaw, Gemini CLI,
Cursor, Windsurf, or generic agent already has an older `openclaw-mem`
installation, database, skill card, or MCP entry.

The safe order is:

```text
inventory → stop writers → preserve rollback inputs → upgrade code
→ preview/migrate DB → preview/refresh harness files → read-only smoke
→ controlled write smoke → resume automation
```

Do not delete the old database, WAL/SHM files, config, installer backups, or
migration receipt until the upgraded agent has passed its normal workload.

## 1. Choose the upgrade owner

Run the upgrade from the same Python environment and user account that owns the
current `openclaw-mem` executable. Do not mix a system `pip`, a project virtual
environment, `pipx`, and `uv tool` in one upgrade.

Record the current executable and package before changing anything:

=== "PowerShell"

    ```powershell
    Get-Command openclaw-mem | Format-List Source,Version
    python -m pip show openclaw-context-pack
    python -c "import openclaw_mem; print(openclaw_mem.__version__)"
    openclaw-mem --help-all
    ```

=== "POSIX shell"

    ```bash
    command -v openclaw-mem
    python -m pip show openclaw-context-pack
    python -c 'import openclaw_mem; print(openclaw_mem.__version__)'
    openclaw-mem --help-all
    ```

If the import version and executable environment do not agree, stop and fix
the environment selection first.

## 2. Inventory the agent and database

Record these operator-controlled paths outside the repository:

- SQLite database path
- `~/.openclaw-mem/config.toml`, if present
- harness root and any explicit config path
- observation JSONL / service-writeback inputs
- active OpenClaw memory owner, if OpenClaw is involved
- current package version and the intended rollback version

With the old agent still stopped or read-only, capture aggregate diagnostics:

```bash
openclaw-mem db info --db <memory.sqlite> --json > db-info.before.json
openclaw-mem doctor --db <memory.sqlite> --json > doctor.before.json
```

Treat these receipts as sensitive operational metadata. Do not commit them or
raw memory rows.

## 3. Stop writers and preserve rollback inputs

Pause agent sessions, harvest jobs, hooks, cron tasks, and any mem-engine owner
that can write the database. Then copy the database and configuration to an
operator-only backup location. If SQLite WAL mode is active, copy the database
only after writers have stopped and the connection has closed.

At minimum preserve:

- the database
- adjacent `-wal` / `-shm` files if they still exist
- config and harness instruction files
- the old package version or checkout commit

The governed DB migration creates its own hash-bound backup later; this manual
snapshot protects the period before the new package runs.

## 4. Install v2 from one channel

The distribution name remains `openclaw-context-pack`; the executable remains
`openclaw-mem`.

For a registry installation after v2 is available on that registry:

```bash
python -m pip install --upgrade "openclaw-context-pack==2.0.0"
```

For the GitHub v2.0.0 release tag:

```bash
python -m pip install --upgrade \
  "openclaw-context-pack @ git+https://github.com/phenomenoner/openclaw-mem.git@v2.0.0"
```

For an existing source checkout:

```bash
git fetch --tags origin
git checkout v2.0.0
uv sync --locked
uv run python -c "import openclaw_mem; print(openclaw_mem.__version__)"
```

For `pipx` or `uv tool`, upgrade or force-install the same distribution in the
existing tool environment; do not create a second competing executable.

Confirm the new version before touching operator state:

```bash
python -c "import openclaw_mem; print(openclaw_mem.__version__)"
openclaw-mem --help
```

Expected primary command families are `recall`, `store`, `curate`, `sync`,
`graph`, and `db`. Older commands remain available through `--help-all` with
additive deprecation guidance.

## 5. Preview and apply the database migration

Use the upgraded CLI. `db info` and migration dry-run are the hard gates before
the first normal writer resumes:

```bash
openclaw-mem db info --db <memory.sqlite> --json
openclaw-mem db migrate --db <memory.sqlite> --dry-run --json
openclaw-mem db migrate --db <memory.sqlite> \
  --receipt-out <operator-only>/migration-v2.json --json
openclaw-mem db info --db <memory.sqlite> --json
openclaw-mem doctor --db <memory.sqlite> --json
```

Require all of the following:

- no future-version or integrity error
- migration receipt invariants pass
- backup and receipt exist outside the repository
- row counts are plausible relative to `db-info.before.json`
- FTS and optional embedding/sqlite-vec diagnostics are healthy or explicitly
  degraded with an actionable hint

Kind classification is additive and can be staged separately:

```bash
openclaw-mem db backfill --db <memory.sqlite> --kind --dry-run --json
openclaw-mem db backfill --db <memory.sqlite> --kind --json
```

Run the write only after reviewing the dry-run distribution. Existing explicit
kinds are preserved.

## 6. Refresh config without overwriting operator choices

```bash
openclaw-mem init --db <memory.sqlite> --json
```

`init` is idempotent and fill-only: environment variables still override TOML,
and existing TOML values are not replaced. Review the emitted capability and
configuration receipt instead of assuming optional vector or embedding lanes
are active.

## 7. Preview and refresh the local agent integration

Choose exactly one harness value:

`claude-code`, `codex`, `openclaw`, `generic`, `gemini`, `cursor`, or
`windsurf`.

```bash
openclaw-mem install --harness <harness> --root <harness-root> \
  --dry-run --json
openclaw-mem install --harness <harness> --root <harness-root> \
  --verify --json
openclaw-mem doctor --harness <harness> --root <harness-root> --json
```

Use `--config-path` or `--skills-dir` only when the harness uses a non-default
location. The installer merges managed content, preserves unrelated settings,
and backs up changed existing targets. A dry-run must report zero writes.

For MCP-capable agents, verify the stdio command is `openclaw-mem-mcp`. Do not
put database contents, API keys, or gateway tokens in the skill card or MCP
arguments.

## 8. Run the upgrade smoke tests

First exercise v2 on a disposable database:

```bash
openclaw-mem init --db <temporary.sqlite> --json
openclaw-mem store "Upgrade canary: local agent v2 smoke" \
  --db <temporary.sqlite> --no-file-write --json
openclaw-mem recall "local agent v2 smoke" \
  --db <temporary.sqlite> --mode auto --json
openclaw-mem pack --query "local agent v2 smoke" \
  --db <temporary.sqlite> --trace --json
openclaw-mem curate scan --target memory --db <temporary.sqlite> --json
openclaw-mem db info --db <temporary.sqlite> --json
```

Then run read-only checks against the real database:

```bash
openclaw-mem recall <known-query> --db <memory.sqlite> --mode auto --json
openclaw-mem pack --query <known-query> --db <memory.sqlite> --trace --json
openclaw-mem db info --db <memory.sqlite> --json
```

Verify that a known record is returned, citations are present, the selected
vector backend and fallback reason are honest, and archived records stay
excluded unless explicitly requested.

Only after the read path is green should the operator perform one controlled
real write appropriate to that agent, confirm readback, and resume automation.

## 9. Pass/fail checklist

| Gate | Pass condition |
| --- | --- |
| Executable | one intended `openclaw-mem` resolves and reports `2.0.0` |
| DB safety | pre-upgrade copy plus governed migration backup/receipt exist |
| DB health | info/doctor have no fatal schema, FTS, or integrity failure |
| Retrieval | known-query recall and traced pack return attributable evidence |
| Lifecycle | archived rows remain excluded by default |
| Harness | installer dry-run is zero-write; apply verification and doctor pass |
| MCP | `openclaw-mem-mcp` starts and the harness points to the intended executable |
| Mutation | one controlled write/readback succeeds before automation resumes |
| Privacy | no DB, receipts, tokens, or private absolute paths were committed |

Any failed gate stops the upgrade. Do not treat fail-open fallback as full
backend parity; record which lane degraded and keep the previous owner paused
until the operator accepts that posture.

## 10. Roll back

Stop writers again. If the DB migration must be reversed, use the matching
receipt:

```bash
openclaw-mem db rollback --db <memory.sqlite> \
  --receipt <operator-only>/migration-v2.json --json
openclaw-mem db info --db <memory.sqlite> --json
```

Then reinstall the recorded previous package version or checkout commit and
restore the installer-created harness backup if the integration files changed.
Do not delete the displaced migrated database until retrieval has been verified
on the restored version.

For command mapping, see [Command migration](command-migration.md). For the
database and concurrency contract, see [Database concurrency](db-concurrency.md).
