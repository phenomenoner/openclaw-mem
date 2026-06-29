import json
import subprocess
import sys


def _run_cli(*args, input_obj=None, cwd=None):
    proc = subprocess.run(
        [sys.executable, "-m", "openclaw_mem", *args],
        input=json.dumps(input_obj) if input_obj is not None else None,
        text=True,
        capture_output=True,
        cwd=cwd,
    )
    return proc


def test_bridge_recall_emits_agent_harness_envelope(tmp_path):
    db = tmp_path / "mem.sqlite"
    store = _run_cli(
        "--db",
        str(db),
        "--json",
        "store",
        "bridge recall primary path marker",
        "--category",
        "fact",
        "--importance",
        "0.8",
        "--no-file-write",
    )
    assert store.returncode == 0, store.stderr

    request = {
        "v": 1,
        "op": "recall",
        "requestId": "req-recall-1",
        "deadlineMs": 1500,
        "host": {"agentId": "main", "sessionKey": "s1", "platform": "windows"},
        "payload": {"query": "primary path marker", "limit": 5},
    }
    proc = _run_cli("--db", str(db), "--json", "bridge", "recall", "--stdin-json", input_obj=request)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(proc.stdout)
    assert payload["v"] == 1
    assert payload["requestId"] == "req-recall-1"
    assert payload["provider"] == "openclaw-mem-engine"
    assert payload["operation"] == "recall"
    assert payload["status"] == "ready"
    assert payload["payload"]["backend"] == "sqlite-vector+service-writeback"
    assert payload["payload"]["fallbackUsed"] is False
    assert payload["payload"]["writesPerformed"] is False
    assert payload["payload"]["canonicalWritesAllowed"] is False
    assert payload["payload"]["policySource"] == "openclaw-mem-engine"
    assert payload["payload"]["hitCount"] >= 1
    assert payload["payload"]["hits"][0]["text"]


def test_bridge_store_requires_approval_and_then_recall_sees_write(tmp_path):
    db = tmp_path / "mem.sqlite"
    request = {
        "v": 1,
        "op": "store",
        "requestId": "req-store-1",
        "deadlineMs": 1500,
        "host": {"agentId": "main", "sessionKey": "s1", "platform": "windows"},
        "payload": {
            "text": "bridge approved store marker",
            "approved": False,
            "category": "fact",
            "importance": 0.9,
        },
    }
    denied = _run_cli("--db", str(db), "--json", "bridge", "store", "--stdin-json", input_obj=request)
    assert denied.returncode == 0, denied.stderr
    denied_payload = json.loads(denied.stdout)
    assert denied_payload["status"] == "policy_denied"
    assert denied_payload["payload"]["writesPerformed"] is False

    request["requestId"] = "req-store-2"
    request["payload"]["approved"] = True
    stored = _run_cli("--db", str(db), "--json", "bridge", "store", "--stdin-json", input_obj=request)
    assert stored.returncode == 0, stored.stderr
    stored_payload = json.loads(stored.stdout)
    assert stored_payload["status"] == "ready"
    assert stored_payload["payload"]["writesPerformed"] is True
    assert stored_payload["payload"]["canonicalWritesAllowed"] is True
    assert stored_payload["payload"]["storeId"]

    recall_request = {
        "v": 1,
        "op": "recall",
        "requestId": "req-recall-2",
        "payload": {"query": "approved store marker", "limit": 3},
    }
    recall = _run_cli("--db", str(db), "--json", "bridge", "recall", "--stdin-json", input_obj=recall_request)
    assert recall.returncode == 0, recall.stderr
    recall_payload = json.loads(recall.stdout)
    assert recall_payload["status"] == "ready"
    assert recall_payload["payload"]["hitCount"] >= 1
