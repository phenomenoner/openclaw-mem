import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openclaw_mem.capsule import cmd_diff, cmd_export_canonical, cmd_inspect, cmd_seal, cmd_verify
from openclaw_mem.cli import build_parser


class TestCapsuleCli(unittest.TestCase):
    def test_main_parser_exposes_capsule_family(self):
        a = build_parser().parse_args(["capsule", "inspect", "/tmp/capsule"])
        self.assertEqual(a.cmd, "capsule")
        self.assertEqual(a.capsule_cmd, "inspect")

        b = build_parser().parse_args(["capsule", "export-canonical", "--dry-run", "--json"])
        self.assertEqual(b.cmd, "capsule")
        self.assertEqual(b.capsule_cmd, "export-canonical")
        self.assertTrue(b.dry_run)
        self.assertTrue(b.json)

    def test_export_canonical_dry_run_json_contract(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, summary TEXT)")
            conn.execute(
                "INSERT INTO observations (ts, kind, summary) VALUES (?, ?, ?)",
                ("2026-03-30T03:00:00Z", "fact", "portable capsule sample"),
            )
            conn.commit()
            conn.close()

            args = SimpleNamespace(dry_run=True, db=str(db_path), to=str(Path(td) / "future.capsule"), json=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_export_canonical(args)

            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["schema"], "openclaw-mem.pack-capsule.export-canonical.v1")
            self.assertTrue(out["dry_run"])
            self.assertFalse(out["restore_supported"])
            self.assertEqual(out["manifest"]["schema"], "openclaw-mem.pack-capsule.canonical-manifest.v1")
            self.assertEqual(out["manifest"]["source"]["observations_count"], 1)

    def test_export_canonical_rejects_non_dry_run(self):
        args = SimpleNamespace(dry_run=False, db=None, to=None, json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_export_canonical(args)

        self.assertEqual(rc, 2)
        out = json.loads(buf.getvalue())
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "dry_run_required")

    def test_capsule_seal_verify_inspect_diff_smoke_with_stub_pack(self):
        fake_payload = {
            "bundle_text": "- [obs:1] capsule sample",
            "items": [
                {
                    "recordRef": "obs:1",
                    "kind": "fact",
                    "summary": "capsule sample",
                }
            ],
            "citations": [{"recordRef": "obs:1"}],
            "trace": {"kind": "openclaw-mem.pack.trace.v1"},
        }

        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / "capsules"
            db_path = Path(td) / "target.sqlite"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, summary TEXT)")
            conn.execute(
                "INSERT INTO observations (ts, kind, summary) VALUES (?, ?, ?)",
                ("2026-03-30T03:00:00Z", "fact", "capsule sample"),
            )
            conn.commit()
            conn.close()

            with patch(
                "openclaw_mem.capsule.run_pack",
                return_value={"command": ["openclaw-mem", "pack"], "payload": fake_payload},
            ):
                seal_args = SimpleNamespace(
                    query="capsule sample",
                    out=out_root,
                    db=str(db_path),
                    query_en="",
                    limit=12,
                    budget_tokens=1200,
                    use_graph="off",
                    graph_scope="",
                    pack_trust_policy="off",
                    stash_artifact=False,
                    gzip_artifact=False,
                    label="capsule",
                )
                seal_buf = io.StringIO()
                with redirect_stdout(seal_buf):
                    seal_rc = cmd_seal(seal_args)
                self.assertEqual(seal_rc, 0)
                seal_out = json.loads(seal_buf.getvalue())
                capsule_dir = Path(seal_out["capsule_dir"])

            verify_buf = io.StringIO()
            with redirect_stdout(verify_buf):
                verify_rc = cmd_verify(SimpleNamespace(capsule=capsule_dir))
            self.assertEqual(verify_rc, 0)
            verify_out = json.loads(verify_buf.getvalue())
            self.assertTrue(verify_out["ok"])

            inspect_buf = io.StringIO()
            with redirect_stdout(inspect_buf):
                inspect_rc = cmd_inspect(SimpleNamespace(capsule=capsule_dir, json=True))
            self.assertEqual(inspect_rc, 0)
            inspect_out = json.loads(inspect_buf.getvalue())
            self.assertFalse(inspect_out["restorable"])

            diff_buf = io.StringIO()
            with redirect_stdout(diff_buf):
                diff_rc = cmd_diff(
                    SimpleNamespace(
                        capsule=capsule_dir,
                        db=str(db_path),
                        write_receipt=False,
                        write_report_md=False,
                    )
                )
            self.assertEqual(diff_rc, 0)
            diff_out = json.loads(diff_buf.getvalue())
            self.assertEqual(diff_out["counts"]["present"], 1)
            self.assertEqual(diff_out["counts"]["missing"], 0)


if __name__ == "__main__":
    unittest.main()
