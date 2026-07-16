from __future__ import annotations

import subprocess
import sys

from openclaw_mem.core.api import connect, pack, search, store_observation


def test_importing_core_db_does_not_import_cli_monolith() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import openclaw_mem.core.db; "
            "raise SystemExit(1 if 'openclaw_mem.cli' in sys.modules else 0)",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert probe.returncode == 0, probe.stderr


def test_stable_core_api_round_trip() -> None:
    conn = connect(":memory:")
    try:
        record_id = store_observation(conn, {"kind": "fact", "summary": "alpha core memory"})
        conn.commit()

        results = search(conn, "alpha", limit=5)
        bundle = pack(conn, "alpha", limit=2, budget_tokens=200)

        assert record_id == 1
        assert results[0]["summary"] == "alpha core memory"
        assert bundle["context_pack"]["schema"] == "openclaw-mem.context-pack.v1"
    finally:
        conn.close()
