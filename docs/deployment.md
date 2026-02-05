# Deployment Guide

Production deployment guide for openclaw-mem.

## Overview

For production use, you'll want:
1. **Auto-capture plugin** — Captures tool results automatically
2. **Periodic ingestion** — Imports captured observations into SQLite
3. **Log rotation** — Prevents JSONL files from growing unbounded
4. **AI compression** — Periodic compression of daily notes (optional)
5. **Monitoring** — Health checks and error alerts

## 1. Plugin Installation

### System-Wide (Recommended)

```bash
# Clone repo to persistent location
sudo mkdir -p /opt/openclaw-mem
sudo git clone https://github.com/phenomenoner/openclaw-mem.git /opt/openclaw-mem
cd /opt/openclaw-mem
sudo uv sync --locked

# Symlink plugin
sudo ln -s /opt/openclaw-mem/extensions/openclaw-mem /usr/lib/openclaw/plugins/openclaw-mem
```

### Per-User

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git ~/openclaw-mem
cd ~/openclaw-mem
uv sync --locked

ln -s ~/openclaw-mem/extensions/openclaw-mem ~/.openclaw/plugins/openclaw-mem
```

### Configuration

Add to `~/.openclaw/openclaw.json` (or `/etc/openclaw/openclaw.json` for system-wide):

```json
{
  "plugins": {
    "entries": {
      "openclaw-mem": {
        "enabled": true,
        "config": {
          "outputPath": "~/.openclaw/memory/openclaw-mem-observations.jsonl",
          "captureMessage": false,
          "excludeTools": ["session_status", "cron.list"]
        }
      }
    }
  }
}
```

## 2. Periodic Ingestion

### Option A: systemd Timer (Linux)

Create `~/.config/systemd/user/openclaw-mem-ingest.service`:

```ini
[Unit]
Description=OpenClaw Memory Ingestion
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/home/YOUR_USER/openclaw-mem
Environment="PATH=/home/YOUR_USER/.local/bin:/usr/bin:/bin"
ExecStart=/usr/bin/uv run --python 3.13 -- python -m openclaw_mem ingest --file /home/YOUR_USER/.openclaw/memory/openclaw-mem-observations.jsonl --json

[Install]
WantedBy=default.target
```

Create `~/.config/systemd/user/openclaw-mem-ingest.timer`:

```ini
[Unit]
Description=Run OpenClaw Memory Ingestion every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable openclaw-mem-ingest.timer
systemctl --user start openclaw-mem-ingest.timer

# Check status
systemctl --user status openclaw-mem-ingest.timer
journalctl --user -u openclaw-mem-ingest.service -f
```

### Option B: OpenClaw Cron Job

Add to OpenClaw config:

```json
{
  "cron": {
    "jobs": [
      {
        "name": "Ingest openclaw-mem observations",
        "schedule": { "kind": "every", "everyMs": 300000 },
        "sessionTarget": "isolated",
        "wakeMode": "next-heartbeat",
        "payload": {
          "kind": "agentTurn",
          "message": "Run: cd /opt/openclaw-mem && uv run --python 3.13 -- python -m openclaw_mem ingest --file ~/.openclaw/memory/openclaw-mem-observations.jsonl --json",
          "deliver": false,
          "model": "gemini-3-flash"
        }
      }
    ]
  }
}
```

### Option C: Traditional Cron

```bash
# Edit crontab
crontab -e

# Add line (runs every 5 minutes)
*/5 * * * * cd /opt/openclaw-mem && uv run --python 3.13 -- python -m openclaw_mem ingest --file ~/.openclaw/memory/openclaw-mem-observations.jsonl --json >> ~/.openclaw/logs/openclaw-mem-ingest.log 2>&1
```

## 3. Log Rotation

### logrotate (Linux)

Create `/etc/logrotate.d/openclaw-mem` (or `~/.logrotate.d/openclaw-mem`):

```
/home/*/.openclaw/memory/openclaw-mem-observations.jsonl {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 user user
    sharedscripts
}
```

Test rotation:

```bash
logrotate -d ~/.logrotate.d/openclaw-mem  # dry-run
logrotate -f ~/.logrotate.d/openclaw-mem  # force rotate
```

### Manual Script

```bash
#!/bin/bash
# ~/.openclaw/scripts/rotate-observations.sh

DATE=$(date +%Y-%m-%d)
SRC="$HOME/.openclaw/memory/openclaw-mem-observations.jsonl"
DST="$HOME/.openclaw/memory/archive/openclaw-mem-observations-$DATE.jsonl.gz"

if [ -f "$SRC" ]; then
    mkdir -p "$(dirname "$DST")"
    gzip -c "$SRC" > "$DST"
    > "$SRC"  # truncate original
    echo "Rotated to $DST"
fi
```

Add to cron:

```bash
# Run daily at midnight
0 0 * * * /bin/bash ~/.openclaw/scripts/rotate-observations.sh
```

## 4. AI Compression (Optional)

### Daily Compression (systemd)

Create `~/.config/systemd/user/openclaw-mem-compress.service`:

```ini
[Unit]
Description=OpenClaw Memory AI Compression

[Service]
Type=oneshot
WorkingDirectory=/home/YOUR_USER/openclaw-mem
Environment="OPENAI_API_KEY=sk-YOUR_KEY"
Environment="PATH=/home/YOUR_USER/.local/bin:/usr/bin:/bin"
ExecStart=/usr/bin/uv run --python 3.13 -- python -m openclaw_mem summarize --json

[Install]
WantedBy=default.target
```

Create `~/.config/systemd/user/openclaw-mem-compress.timer`:

```ini
[Unit]
Description=Run OpenClaw Memory AI Compression daily

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:

```bash
systemctl --user daemon-reload
systemctl --user enable openclaw-mem-compress.timer
systemctl --user start openclaw-mem-compress.timer
```

### OpenClaw Cron Job

```json
{
  "cron": {
    "jobs": [
      {
        "name": "Daily AI compression",
        "schedule": { "kind": "cron", "expr": "0 2 * * *", "tz": "UTC" },
        "sessionTarget": "isolated",
        "payload": {
          "kind": "agentTurn",
          "message": "Run: cd /opt/openclaw-mem && OPENAI_API_KEY=$OPENAI_API_KEY uv run --python 3.13 -- python -m openclaw_mem summarize --json",
          "deliver": false
        }
      }
    ]
  }
}
```

## 5. Monitoring

### Health Check Script

```bash
#!/bin/bash
# ~/.openclaw/scripts/healthcheck-openclaw-mem.sh

DB="$HOME/.openclaw/memory/openclaw-mem.sqlite"
JSONL="$HOME/.openclaw/memory/openclaw-mem-observations.jsonl"

# Check DB exists and is writable
if [ ! -f "$DB" ] || [ ! -w "$DB" ]; then
    echo "ERROR: Database missing or not writable: $DB"
    exit 1
fi

# Check JSONL isn't too large (>50MB)
if [ -f "$JSONL" ]; then
    SIZE=$(stat -f%z "$JSONL" 2>/dev/null || stat -c%s "$JSONL" 2>/dev/null)
    if [ "$SIZE" -gt 52428800 ]; then
        echo "WARNING: JSONL file is large (${SIZE} bytes). Consider rotation."
    fi
fi

# Check observation count
cd /opt/openclaw-mem
COUNT=$(uv run --python 3.13 -- python -m openclaw_mem status --json | jq -r '.count')
if [ "$COUNT" -lt 10 ]; then
    echo "WARNING: Low observation count ($COUNT). Check plugin is capturing."
fi

echo "OK: $COUNT observations in DB"
```

Add to cron for daily checks:

```bash
0 6 * * * /bin/bash ~/.openclaw/scripts/healthcheck-openclaw-mem.sh
```

### Metrics Export (Optional)

```python
#!/usr/bin/env python3
# Export metrics for Prometheus/Grafana

import json
import sqlite3
from pathlib import Path

DB = Path.home() / ".openclaw/memory/openclaw-mem.sqlite"
conn = sqlite3.connect(DB)

# Total observations
count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
print(f"openclaw_mem_observations_total {count}")

# Observations by tool
rows = conn.execute(
    "SELECT tool_name, COUNT(*) FROM observations GROUP BY tool_name"
).fetchall()
for tool, cnt in rows:
    print(f'openclaw_mem_observations_by_tool{{tool="{tool}"}} {cnt}')

conn.close()
```

## 6. Backup & Disaster Recovery

### Backup Script

```bash
#!/bin/bash
# Backup SQLite DB and JSONL to S3/rsync

DATE=$(date +%Y-%m-%d)
BACKUP_DIR="$HOME/.openclaw/backups/$DATE"
mkdir -p "$BACKUP_DIR"

# Copy DB (safe even while writes are happening due to WAL mode)
cp ~/.openclaw/memory/openclaw-mem.sqlite "$BACKUP_DIR/"
cp ~/.openclaw/memory/openclaw-mem-observations.jsonl "$BACKUP_DIR/" 2>/dev/null || true

# Compress
tar -czf "$HOME/.openclaw/backups/openclaw-mem-$DATE.tar.gz" -C "$HOME/.openclaw/backups" "$DATE"
rm -rf "$BACKUP_DIR"

# Upload to S3 (optional)
# aws s3 cp "$HOME/.openclaw/backups/openclaw-mem-$DATE.tar.gz" s3://my-bucket/openclaw-mem/

# Keep last 7 days
find "$HOME/.openclaw/backups" -name "openclaw-mem-*.tar.gz" -mtime +7 -delete

echo "Backup complete: openclaw-mem-$DATE.tar.gz"
```

### Recovery

```bash
# Extract backup
tar -xzf openclaw-mem-2026-02-05.tar.gz

# Restore DB
cp 2026-02-05/openclaw-mem.sqlite ~/.openclaw/memory/

# Verify
cd /opt/openclaw-mem
uv run --python 3.13 -- python -m openclaw_mem status --json
```

## 7. Security Hardening

### File Permissions

```bash
# Restrict DB to user only
chmod 600 ~/.openclaw/memory/openclaw-mem.sqlite

# Restrict JSONL
chmod 600 ~/.openclaw/memory/openclaw-mem-observations.jsonl
```

### Secrets Management

Don't hardcode `OPENAI_API_KEY` in config files. Use:

**systemd:**
```ini
[Service]
EnvironmentFile=/etc/secrets/openclaw-mem.env
```

**Cron:**
```bash
*/5 * * * * source ~/.openclaw/secrets.env && cd /opt/openclaw-mem && ...
```

**OpenClaw config:**
Use environment variable substitution:
```json
{
  "env": {
    "OPENAI_API_KEY": "${OPENAI_API_KEY}"
  }
}
```

### Network Isolation (Optional)

If running on a server, restrict OpenAI API access:

```bash
# Allow only OpenAI API
sudo iptables -A OUTPUT -p tcp -d api.openai.com --dport 443 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 443 -j DROP  # drop all other HTTPS
```

## 8. Troubleshooting

### Check Plugin Status

```bash
openclaw plugins list | grep openclaw-mem
```

### Check Capture Activity

```bash
# Tail JSONL (should show new lines as tools run)
tail -f ~/.openclaw/memory/openclaw-mem-observations.jsonl

# Check file modification time
stat ~/.openclaw/memory/openclaw-mem-observations.jsonl
```

### Check Ingestion Logs

```bash
# systemd
journalctl --user -u openclaw-mem-ingest.service -f

# cron
tail -f ~/.openclaw/logs/openclaw-mem-ingest.log
```

### Database Locked Errors

Ensure WAL mode is enabled:

```bash
sqlite3 ~/.openclaw/memory/openclaw-mem.sqlite "PRAGMA journal_mode;"
# Should output: wal
```

### High Memory Usage

Check DB size:

```bash
du -h ~/.openclaw/memory/openclaw-mem.sqlite
```

If >1GB, consider archiving old observations:

```sql
-- Archive observations older than 90 days
DELETE FROM observations WHERE ts < datetime('now', '-90 days');
VACUUM;
```

## Production Checklist

- [ ] Plugin installed and enabled in config
- [ ] Periodic ingestion set up (systemd/cron)
- [ ] Log rotation configured
- [ ] Health checks in place
- [ ] Backups automated
- [ ] File permissions secured
- [ ] Secrets stored securely (not in config files)
- [ ] Monitoring/alerting configured
- [ ] Documentation updated with custom paths

## Performance Tips

- Run ingestion every 5-10 minutes (not every minute)
- Use `captureMessage: false` in plugin config (saves ~80% space)
- Enable log rotation (keeps JSONL files <50MB)
- Archive old observations (DELETE + VACUUM quarterly)
- Use `gemini-3-flash` for AI compression (cheaper than GPT-4)

## Support

For deployment issues, see:
- [`docs/db-concurrency.md`](db-concurrency.md) — Database locking
- [`docs/auto-capture.md`](auto-capture.md) — Plugin troubleshooting
- GitHub Issues: https://github.com/phenomenoner/openclaw-mem/issues
