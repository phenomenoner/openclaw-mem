from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openclaw_mem.cli import _connect, cmd_bridge_recall, cmd_bridge_store, cmd_ingest


class TestBridgeRecallV1(unittest.TestCase):
    FIXTURE = Path(__file__).parent / "data" / "graph_search_hybrid" / "observations.jsonl"

    def _db(self, root: Path) -> Path:
        db = root / "mem.sqlite"
        conn = _connect(str(db))
        try:
            cmd_ingest(conn, SimpleNamespace(file=str(self.FIXTURE), json=True, importance_scorer=None))
        finally:
            conn.close()
        return db

    def _bridge_recall(self, db: Path, request: dict) -> dict:
        conn = _connect(str(db))
        try:
            args = SimpleNamespace(db=str(db), json=True, stdin_json=True, request=None, response=None, limit=5)
            with patch("sys.stdin", io.StringIO(json.dumps(request))):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_bridge_recall(conn, args)
            return json.loads(buf.getvalue())
        finally:
            conn.close()

    def test_ready_recall_envelope_has_policy_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = self._db(Path(td))
            out = self._bridge_recall(db, {"requestId": "r1", "op": "recall", "payload": {"query": "resolver", "limit": 3}})
        self.assertEqual(out["kind"], "openclaw-mem-engine.bridge.recall.v1")
        self.assertEqual(out["status"], "ready")
        self.assertEqual(out["payload"]["backend"], "sqlite-vector+service-writeback")
        self.assertIs(out["payload"]["canonicalWritesAllowed"], False)
        self.assertEqual(out["payload"]["policySource"], "openclaw-mem-engine")

    def test_degraded_recall_has_fallback_reason(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = self._db(Path(td))
            out = self._bridge_recall(db, {"requestId": "r2", "op": "recall", "payload": {"query": "missing-zebra-term", "limit": 3}})
        self.assertEqual(out["status"], "degraded")
        self.assertIs(out["payload"]["fallbackUsed"], True)
        self.assertEqual(out["payload"]["fallbackReason"], "no_hits")

    def test_unavailable_when_db_path_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "missing.sqlite"
            conn = _connect(":memory:")
            try:
                args = SimpleNamespace(db=str(missing), json=True, stdin_json=True, request=None, response=None, limit=5)
                request = {"requestId": "u1", "op": "recall", "payload": {"query": "resolver"}}
                with patch("sys.stdin", io.StringIO(json.dumps(request))):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        cmd_bridge_recall(conn, args)
            finally:
                conn.close()
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "unavailable")
        self.assertEqual(out["payload"]["fallbackReason"], "db_unavailable")

    def test_malformed_request_returns_error_envelope(self) -> None:
        conn = _connect(":memory:")
        try:
            args = SimpleNamespace(db=":memory:", json=True, stdin_json=True, request=None, response=None, limit=5)
            with patch("sys.stdin", io.StringIO("{bad json")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_bridge_recall(conn, args)
        finally:
            conn.close()
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "error")
        self.assertEqual(out["errorCode"], "bridge_protocol")

    def _bridge_store(self, db: Path, request: dict) -> dict:
        conn = _connect(str(db))
        try:
            args = SimpleNamespace(db=str(db), json=True, stdin_json=True, request=None, response=None)
            with patch("sys.stdin", io.StringIO(json.dumps(request))):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_bridge_store(conn, args)
            return json.loads(buf.getvalue())
        finally:
            conn.close()

    def test_unapproved_store_is_policy_denied_and_db_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = self._db(root)
            before = hashlib.sha256(db.read_bytes()).hexdigest()
            request = {"requestId": "w1", "op": "memory_store", "payload": {"text": "must not write"}}
            out = self._bridge_store(db, request)
            after = hashlib.sha256(db.read_bytes()).hexdigest()
        self.assertEqual(out["kind"], "openclaw-mem-engine.bridge.store.v1")
        self.assertEqual(out["status"], "policy_denied")
        self.assertEqual(out["errorCode"], "approval_required")
        self.assertIs(out["payload"]["writesPerformed"], False)
        self.assertEqual(after, before)

    def test_approved_store_writes_and_returns_store_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = self._db(root)
            before = hashlib.sha256(db.read_bytes()).hexdigest()
            request = {
                "requestId": "w2",
                "op": "store",
                "payload": {"text": "operator approved canonical note", "approved": True},
            }
            out = self._bridge_store(db, request)
            after = hashlib.sha256(db.read_bytes()).hexdigest()
            recall = self._bridge_recall(
                db, {"requestId": "w3", "op": "recall", "payload": {"query": "operator approved canonical note", "limit": 3}}
            )
        self.assertEqual(out["status"], "ready")
        self.assertIs(out["payload"]["writesPerformed"], True)
        self.assertTrue(str(out["payload"]["storeId"] or "").startswith("obs:"))
        self.assertNotEqual(after, before)
        self.assertEqual(recall["status"], "ready")
        self.assertTrue(any("operator approved canonical note" in str(h.get("text") or "") for h in recall["payload"]["hits"]))

    def test_subprocess_env_outputs_clean_utf8_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = self._db(root)
            req = root / "request.json"
            req.write_text(json.dumps({"requestId": "s1", "op": "recall", "payload": {"query": "resolver"}}), encoding="utf-8")
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["NODE_NO_WARNINGS"] = "1"
            p = subprocess.run(
                [sys.executable, "-m", "openclaw_mem", "--db", str(db), "--json", "bridge", "recall", "--request", str(req)],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True,
            )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, "")
        self.assertEqual(json.loads(p.stdout)["kind"], "openclaw-mem-engine.bridge.recall.v1")


if __name__ == "__main__":
    unittest.main()
