import json
import os
import subprocess
import sysconfig


def _console_script() -> str:
    suffix = ".exe" if os.name == "nt" else ""
    return os.path.join(sysconfig.get_path("scripts"), f"openclaw-mem{suffix}")


def _run_console(*args: str, cwd: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [_console_script(), *args],
        cwd=cwd,
        env=env,
        text=True, encoding="utf-8", errors="replace",
        capture_output=True,
        check=False,
    )


def test_windows_console_wrapper_bridge_status_recall_store(tmp_path):
    script = _console_script()
    assert os.path.exists(script), script

    db = tmp_path / "mem.sqlite"
    status = _run_console("--db", str(db), "--json", "bridge", "status", cwd=str(tmp_path))
    assert status.returncode == 0, status.stderr
    status_payload = json.loads(status.stdout)
    assert status_payload["status"] == "ready"
    assert status_payload["payload"]["fallbackUsed"] is False

    store_request = tmp_path / "store-request.json"
    store_request.write_text(
        json.dumps(
            {
                "v": 1,
                "op": "store",
                "requestId": "wrapper-store",
                "payload": {
                    "text": "windows console wrapper bridge marker",
                    "approved": True,
                    "category": "fact",
                    "importance": 0.7,
                },
            }
        ),
        encoding="utf-8",
    )
    store = _run_console(
        "--db",
        str(db),
        "--json",
        "bridge",
        "store",
        "--request",
        str(store_request),
        cwd=str(tmp_path),
    )
    assert store.returncode == 0, store.stderr
    store_payload = json.loads(store.stdout)
    assert store_payload["status"] == "ready"
    assert store_payload["payload"]["writesPerformed"] is True

    recall_request = tmp_path / "recall-request.json"
    recall_request.write_text(
        json.dumps(
            {
                "v": 1,
                "op": "recall",
                "requestId": "wrapper-recall",
                "payload": {
                    "query": "windows console wrapper bridge marker",
                    "limit": 3,
                },
            }
        ),
        encoding="utf-8",
    )
    recall = _run_console(
        "--db",
        str(db),
        "--json",
        "bridge",
        "recall",
        "--request",
        str(recall_request),
        cwd=str(tmp_path),
    )
    assert recall.returncode == 0, recall.stderr
    recall_payload = json.loads(recall.stdout)
    assert recall_payload["status"] == "ready"
    assert recall_payload["payload"]["fallbackUsed"] is False
    assert recall_payload["payload"]["hitCount"] >= 1
