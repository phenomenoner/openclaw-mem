from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "legacy_dbs" / "v1.9.31.sqlite"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _snapshot(db: Path) -> dict[str, tuple[bool, str | None]]:
    result: dict[str, tuple[bool, str | None]] = {}
    for path in (db, Path(f"{db}-wal"), Path(f"{db}-shm")):
        exists = path.exists()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
        result[path.name] = (exists, digest)
    return result


def _readonly_command(db: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "OPENCLAW_MEM_READONLY_DB": "1",
            "OPENAI_API_KEY": "",
            "PYTHONUTF8": "1",
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "openclaw_mem", "--db", str(db), "--json", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_readonly_command_matrix_never_changes_db_wal_or_shm(tmp_path: Path) -> None:
    db = tmp_path / "readonly.sqlite"
    shutil.copy2(FIXTURE, db)
    before = _snapshot(db)
    commands = (
        ("status",),
        ("search", "legacy anchor"),
        ("timeline", "1"),
        ("get", "1"),
        ("pack", "--query", "legacy anchor"),
        ("db", "info"),
    )

    for command in commands:
        completed = _readonly_command(db, *command)
        assert completed.returncode == 0, (
            f"readonly command failed: {command!r}\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
        payload = json.loads(completed.stdout)
        assert payload
        assert _snapshot(db) == before, f"readonly command mutated files: {command!r}"


def test_readonly_mode_still_rejects_newer_database_generation(tmp_path: Path) -> None:
    db = tmp_path / "future.sqlite"
    shutil.copy2(FIXTURE, db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    before = _snapshot(db)

    completed = _readonly_command(db, "status")

    assert completed.returncode != 0
    assert "db_version_unsupported" in completed.stderr
    assert _snapshot(db) == before
