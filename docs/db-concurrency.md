# Database Concurrency & Locking

## Problem
Multiple OpenClaw sessions, cron jobs, or heartbeat checks may access the SQLite database concurrently, causing lock contention or corruption.

## Solution: WAL Mode + Short-Lived Connections

### 1. Enable WAL Mode
Write-Ahead Logging allows concurrent readers while a writer is active.

```python
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode=WAL;")
```

**Already implemented in `openclaw_mem/cli.py`** ✅

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
