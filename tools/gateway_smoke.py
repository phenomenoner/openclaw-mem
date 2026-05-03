#!/usr/bin/env python3
"""Live smoke for openclaw-mem-gateway.

Writes reviewable JSON artifacts under .state/openclaw-mem-gateway-smoke/.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_STATE = Path(os.getenv("OPENCLAW_WORKSPACE_STATE", "/root/.openclaw/workspace/.state"))
OUT = WORKSPACE_STATE / "openclaw-mem-gateway-smoke"
OUT.mkdir(parents=True, exist_ok=True)
DB = OUT / "smoke.sqlite"
READ_TOKEN = "smoke-read-token"
WRITE_TOKEN = "smoke-write-token"
ADMIN_TOKEN = "smoke-admin-token"


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return int(port)


def request(base: str, method: str, path: str, *, token: str | None = None, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return {"status": resp.status, "payload": payload}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
        return {"status": e.code, "payload": payload}


def main() -> int:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["OPENCLAW_MEM_GATEWAY_TOKENS"] = f"{READ_TOKEN}:read,{WRITE_TOKEN}:write,{ADMIN_TOKEN}:admin"
    env["OPENCLAW_MEM_DB"] = str(DB)
    proc = subprocess.Popen(
        [sys.executable, "-m", "openclaw_mem.gateway", "--host", "127.0.0.1", "--port", str(port), "--db", str(DB)],
        cwd=str(ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    artifacts: dict[str, object] = {"base": base, "db": str(DB), "checks": {}}
    try:
        first = proc.stdout.readline().strip() if proc.stdout else ""
        artifacts["startup"] = json.loads(first) if first else {"raw": first}
        deadline = time.time() + 10
        while time.time() < deadline:
            health = request(base, "GET", "/health")
            if health["status"] == 200:
                break
            time.sleep(0.1)
        checks = artifacts["checks"]  # type: ignore[assignment]
        checks["health"] = request(base, "GET", "/health")
        checks["status_missing_auth"] = request(base, "GET", "/v1/status")
        checks["status_read"] = request(base, "GET", "/v1/status", token=READ_TOKEN)
        checks["append_read_forbidden"] = request(
            base,
            "POST",
            "/v1/episodes/append",
            token=READ_TOKEN,
            body={
                "scope": "openclaw-mem",
                "session_id": "gateway-smoke",
                "agent_id": "smoke",
                "type": "ops.decision",
                "summary": "read token should not append",
            },
        )
        checks["append_write"] = request(
            base,
            "POST",
            "/v1/episodes/append",
            token=WRITE_TOKEN,
            body={
                "scope": "openclaw-mem",
                "session_id": "gateway-smoke",
                "agent_id": "smoke",
                "type": "ops.decision",
                "summary": "Gateway smoke appended scoped event",
                "refs": {"smoke": True},
            },
        )
        checks["episodes_query"] = request(
            base,
            "POST",
            "/v1/episodes/query",
            token=READ_TOKEN,
            body={"scope": "openclaw-mem", "session_id": "gateway-smoke", "limit": 10},
        )
        checks["store_propose"] = request(
            base,
            "POST",
            "/v1/store/propose",
            token=WRITE_TOKEN,
            body={
                "scope": "openclaw-mem",
                "agent_id": "smoke",
                "category": "decision",
                "importance": 0.7,
                "text": "Gateway smoke memory proposal",
                "provenance": {"smoke": True},
            },
        )
        checks["search"] = request(
            base,
            "POST",
            "/v1/search",
            token=READ_TOKEN,
            body={"query": "Gateway smoke", "limit": 5},
        )
        checks["pack"] = request(
            base,
            "POST",
            "/v1/pack",
            token=READ_TOKEN,
            body={"query": "Gateway smoke memory proposal", "limit": 5, "budget_tokens": 800},
        )
        checks["direct_store_blocked"] = request(
            base,
            "POST",
            "/v1/store",
            token=ADMIN_TOKEN,
            body={"text": "Should be blocked", "category": "fact", "importance": 0.5},
        )
        checks["archive_dry_run"] = request(
            base,
            "POST",
            "/v1/archive/export-canonical",
            token=ADMIN_TOKEN,
            body={"dry_run": True},
        )

        expected = {
            "health": 200,
            "status_missing_auth": 401,
            "status_read": 200,
            "append_read_forbidden": 403,
            "append_write": 200,
            "episodes_query": 200,
            "store_propose": 200,
            "search": 200,
            "pack": 200,
            "direct_store_blocked": 403,
            "archive_dry_run": 200,
        }
        failures = []
        for name, status in expected.items():
            got = checks[name]["status"]  # type: ignore[index]
            if got != status:
                failures.append({"check": name, "expected": status, "got": got})
        artifacts["failures"] = failures
        artifacts["ok"] = not failures
        (OUT / "gateway_smoke_receipt.json").write_text(json.dumps(artifacts, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if not failures else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr = ""
        if proc.stderr:
            try:
                stderr = proc.stderr.read()[-4000:]
            except Exception:
                stderr = ""
        (OUT / "gateway_stderr.log").write_text(stderr, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
