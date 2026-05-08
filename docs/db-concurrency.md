# Database Concurrency & Locking

## Problem
Multiple OpenClaw sessions, cron jobs, or heartbeat checks may access the SQLite database concurrently, causing lock contention or corruption.

## Solution: WAL Mode + Short-Lived Connections

### 1. Enable WAL Mode
Write-Ahead Logging allows concurrent readers while a writer is active.

```python
conn = sqlite3.connect(db_path, timeout=10.0)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=5000;")
```

**Implemented in the main sidecar connection path (`openclaw_mem/cli.py`) and graph refresh write path** ✅

`journal_mode=WAL` is best-effort in the main CLI connection path. Writable stores still use WAL, but read-only/read-mostly gateway lanes tolerate SQLite refusing the journal-mode switch (for example, `attempt to write a readonly database`) so read endpoints can still run `SELECT` queries instead of failing before search/pack logic starts. For read-only gateway routes, the CLI may skip schema initialization and open SQLite with a `mode=ro&immutable=1` URI; if the indexed DB/docs route is empty or degraded, the gateway can fall back to read-only workspace Markdown scanning. Unexpected SQLite operational errors outside those read-only paths still propagate.

### 2. Short-Lived Connections
Open → operate → close immediately. Avoid holding connections across operations.

```python
# Good: short-lived
def cmd_search(conn, args):
    rows = conn.execute("SELECT ...").fetchall()
    return rows  # connection closed by caller

# Bad: long-lived (blocks other writers)
global_conn = sqlite3.connect(db_path)  # held forever
```

### 3. Read-Only for Heartbeats
Cron jobs that only query should open read-only:

```python
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
```

### 4. Per-Agent DB Path (Optional)
For multi-agent setups, consider separate DBs:

```bash
~/.openclaw/memory/openclaw-mem-{agentId}.sqlite
```

### 5. File Locking (Alternative)
If WAL isn't enough, use `fcntl` (Unix) or `msvcrt` (Windows) to acquire exclusive locks during writes.

## Recommended Flags

```python
conn = sqlite3.connect(db_path, timeout=10.0)  # wait up to 10s for lock
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=5000;")  # 5s busy timeout
```

## Testing Concurrency
Spawn multiple CLI processes simultaneously:

```bash
for i in {1..10}; do
  openclaw-mem search "test" --json &
done
wait
```

If you see `database is locked` errors, review connection lifetime and WAL settings.
