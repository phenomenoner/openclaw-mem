from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from openclaw_mem.cli import _connect, cmd_graph_fact


class TestGraphFactGuard(unittest.TestCase):
    def _write_facts(self, path: Path) -> None:
        rows = [
            {
                "fact_id": "fact:old",
                "kind": "constraint",
                "predicate": "requires_gate",
                "target": "openclaw_mem/cli.py",
                "text": "old gate",
                "source_refs": ["doc:old"],
                "receipt_id": "receipt:old",
                "freshness": "2020-01-01T00:00:00Z",
            },
            {
                "fact_id": "fact:a",
                "kind": "constraint",
                "predicate": "requires_gate",
                "target": "openclaw_mem/cli.py",
                "text": "run bridge recall tests",
                "source_refs": ["doc:a"],
                "receipt_id": "receipt:a",
                "freshness": "snapshot",
            },
            {
                "fact_id": "fact:b",
                "kind": "regression-risk",
                "predicate": "known_bug",
                "target": "openclaw_mem/cli.py",
                "text": "store writes must stay rejected",
                "source_refs": ["doc:b"],
                "receipt_id": "receipt:b",
                "freshness": "snapshot",
                "supersedes": ["fact:a"],
            },
        ]
        path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")

    def test_propose_without_source_ref_is_machine_readable_rejection(self) -> None:
        conn = _connect(":memory:")
        args = SimpleNamespace(
            graph_fact_cmd="propose",
            text="bridge must reject writes",
            file="",
            source_ref=None,
            kind="constraint",
            target="openclaw_mem/cli.py",
            max_proposals=20,
            json=True,
        )
        with self.assertRaises(SystemExit) as cm:
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_fact(conn, args)
        self.assertEqual(cm.exception.code, 2)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["rejection_reason"], "missing_source_ref")

    def test_guard_excludes_stale_and_superseded_with_context_pack(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            facts = Path(td) / "facts.jsonl"
            self._write_facts(facts)
            before = hashlib.sha256(facts.read_bytes()).hexdigest()
            conn = _connect(":memory:")
            args = SimpleNamespace(graph_fact_cmd="guard", facts=str(facts), target="openclaw_mem/cli.py", intent="edit bridge", stale_after_days=30, json=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_fact(conn, args)
            after = hashlib.sha256(facts.read_bytes()).hexdigest()
        out = json.loads(buf.getvalue())
        self.assertEqual(after, before)
        self.assertFalse(out["writes_performed"])
        self.assertEqual([item["fact_id"] for item in out["stale"]], ["fact:old"])
        self.assertEqual([item["fact_id"] for item in out["superseded"]], ["fact:a"])
        self.assertEqual([item["fact_id"] for item in out["regression_risks"]], ["fact:b"])
        self.assertEqual(out["context_pack_fragment"]["schema"], "openclaw-mem.context-pack.fragment.v0")
        self.assertEqual(out["context_pack_fragment"]["items"][0]["receipt_ids"], ["receipt:b"])

    def test_guard_lint_conflict_then_resolved_by_supersedes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            facts = Path(td) / "facts.jsonl"
            base = [
                {"fact_id": "p", "predicate": "prohibits", "target": "x.py", "text": "do not touch", "freshness": "snapshot"},
                {"fact_id": "v", "predicate": "validated_by", "target": "x.py", "text": "validated", "freshness": "snapshot"},
            ]
            facts.write_text("\n".join(json.dumps(x) for x in base) + "\n", encoding="utf-8")
            conn = _connect(":memory:")
            args = SimpleNamespace(graph_fact_cmd="guard-lint", facts=str(facts), stale_after_days=30, json=True)
            with self.assertRaises(SystemExit) as cm:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_graph_fact(conn, args)
            self.assertEqual(cm.exception.code, 1)
            self.assertEqual(json.loads(buf.getvalue())["issues"][0]["code"], "conflicting_active_constraints")

            base[1]["supersedes"] = ["p"]
            facts.write_text("\n".join(json.dumps(x) for x in base) + "\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_fact(conn, args)
            self.assertTrue(json.loads(buf.getvalue())["ok"])

    def test_corrupt_facts_fail_open_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            facts = Path(td) / "facts.jsonl"
            facts.write_text("{bad json", encoding="utf-8")
            conn = _connect(":memory:")
            args = SimpleNamespace(graph_fact_cmd="guard", facts=str(facts), target="x.py", intent="edit", stale_after_days=30, json=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_fact(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "error")
        self.assertFalse(out["writes_performed"])


if __name__ == "__main__":
    unittest.main()
