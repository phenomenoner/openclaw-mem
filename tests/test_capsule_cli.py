import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import openclaw_mem.cli as mem_cli
from openclaw_mem.capsule import cmd_diff, cmd_export_canonical, cmd_inspect, cmd_restore, cmd_seal, cmd_verify
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

        c = build_parser().parse_args(["capsule", "restore", "/tmp/canonical", "--dry-run", "--json"])
        self.assertEqual(c.cmd, "capsule")
        self.assertEqual(c.capsule_cmd, "restore")
        self.assertTrue(c.dry_run)
        self.assertFalse(c.apply)
        self.assertTrue(c.json)

    def test_cli_main_capsule_skips_global_connect_side_effects(self):
        captured = {}

        def fake_func(conn, args):
            captured["db"] = getattr(args, "db", None)
            captured["json"] = getattr(args, "json", None)
            captured["conn_type"] = type(conn).__name__

        fake_args = SimpleNamespace(
            cmd="capsule",
            db=None,
            db_global="/tmp/should-not-be-forced.sqlite",
            json=False,
            json_global=True,
            func=fake_func,
        )
        fake_parser = SimpleNamespace(parse_args=lambda: fake_args)

        with patch("openclaw_mem.cli.build_parser", return_value=fake_parser), patch(
            "openclaw_mem.cli._connect", side_effect=AssertionError("_connect must not run for capsule commands")
        ):
            mem_cli.main()

        self.assertIsNone(captured["db"])
        self.assertTrue(captured["json"])
        self.assertEqual(captured["conn_type"], "Connection")

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
            self.assertTrue(out["restore_supported"])
            self.assertEqual(out["manifest"]["schema"], "openclaw-mem.pack-capsule.canonical-manifest.v1")
            self.assertEqual(out["manifest"]["source"]["observations_count"], 1)

    def test_export_canonical_write_and_verify_inspect(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            out_root = Path(td) / "exports"

            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE observations (id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, summary TEXT, scope TEXT)"
            )
            conn.execute(
                "INSERT INTO observations (ts, kind, summary, scope) VALUES (?, ?, ?, ?)",
                ("2026-03-30T03:00:00Z", "fact", "portable capsule sample", "test"),
            )
            conn.commit()
            conn.close()

            export_buf = io.StringIO()
            with redirect_stdout(export_buf):
                rc = cmd_export_canonical(
                    SimpleNamespace(dry_run=False, db=str(db_path), to=str(out_root), json=True)
                )
            self.assertEqual(rc, 0)
            export_out = json.loads(export_buf.getvalue())
            self.assertTrue(export_out["archive_written"])
            artifact_dir = Path(export_out["artifact_dir"])
            self.assertTrue((artifact_dir / "manifest.json").exists())
            self.assertTrue((artifact_dir / "observations.jsonl").exists())
            self.assertTrue((artifact_dir / "index.json").exists())
            self.assertTrue((artifact_dir / "provenance.json").exists())

            verify_buf = io.StringIO()
            with redirect_stdout(verify_buf):
                verify_rc = cmd_verify(SimpleNamespace(capsule=artifact_dir))
            self.assertEqual(verify_rc, 0)
            verify_out = json.loads(verify_buf.getvalue())
            self.assertTrue(verify_out["ok"])

            inspect_buf = io.StringIO()
            with redirect_stdout(inspect_buf):
                inspect_rc = cmd_inspect(SimpleNamespace(capsule=artifact_dir, json=True))
            self.assertEqual(inspect_rc, 0)
            inspect_out = json.loads(inspect_buf.getvalue())
            self.assertEqual(inspect_out["schema"], "openclaw-mem.canonical-capsule.inspect.v1")
            self.assertTrue(inspect_out["restorable"])

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

    def test_restore_dry_run_and_apply_isolated_target(self):
        with tempfile.TemporaryDirectory() as td:
            source_db = Path(td) / "source.sqlite"
            target_db = Path(td) / "isolated.sqlite"
            export_root = Path(td) / "exports"

            conn = sqlite3.connect(source_db)
            conn.execute(
                "CREATE TABLE observations (id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, summary TEXT, scope TEXT)"
            )
            conn.execute(
                "INSERT INTO observations (id, ts, kind, summary, scope) VALUES (?, ?, ?, ?, ?)",
                (1, "2026-03-30T03:00:00Z", "fact", "restore sample 1", "demo"),
            )
            conn.execute(
                "INSERT INTO observations (id, ts, kind, summary, scope) VALUES (?, ?, ?, ?, ?)",
                (2, "2026-03-30T03:05:00Z", "fact", "restore sample 2", "demo"),
            )
            conn.commit()
            conn.close()

            export_buf = io.StringIO()
            with redirect_stdout(export_buf):
                export_rc = cmd_export_canonical(
                    SimpleNamespace(dry_run=False, db=str(source_db), to=str(export_root), json=True)
                )
            self.assertEqual(export_rc, 0)
            export_out = json.loads(export_buf.getvalue())
            capsule_dir = Path(export_out["artifact_dir"])

            dry_buf = io.StringIO()
            with redirect_stdout(dry_buf):
                dry_rc = cmd_restore(
                    SimpleNamespace(
                        capsule=capsule_dir,
                        dry_run=True,
                        apply=False,
                        db=str(target_db),
                        json=True,
                    )
                )
            self.assertEqual(dry_rc, 0)
            dry_out = json.loads(dry_buf.getvalue())
            self.assertTrue(dry_out["ok"])
            self.assertEqual(dry_out["mode"], "dry-run")
            self.assertEqual(dry_out["plan"]["rows_to_append"], 2)
            self.assertEqual(dry_out["target"]["table_status"], "missing_target_db")

            apply_buf = io.StringIO()
            with redirect_stdout(apply_buf):
                apply_rc = cmd_restore(
                    SimpleNamespace(
                        capsule=capsule_dir,
                        dry_run=False,
                        apply=True,
                        db=str(target_db),
                        json=True,
                    )
                )
            self.assertEqual(apply_rc, 0)
            apply_out = json.loads(apply_buf.getvalue())
            self.assertTrue(apply_out["ok"])
            self.assertTrue(apply_out["apply"]["readback"]["ok"])
            self.assertEqual(apply_out["apply"]["rows_applied"], 2)
            self.assertTrue(Path(apply_out["rollback_manifest_path"]).exists())
            self.assertTrue(Path(apply_out["restore_receipt_path"]).exists())

            check_conn = sqlite3.connect(target_db)
            count = check_conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            check_conn.close()
            self.assertEqual(count, 2)

    def test_restore_rejects_non_canonical_schema(self):
        with tempfile.TemporaryDirectory() as td:
            capsule_dir = Path(td) / "fake-capsule"
            capsule_dir.mkdir(parents=True, exist_ok=True)

            placeholder = capsule_dir / "bundle.json"
            placeholder.write_text("{}\n", encoding="utf-8")
            manifest = {
                "schema": "openclaw-mem.pack-capsule.v1",
                "capsule_version": 0,
                "files": [
                    {
                        "name": "bundle.json",
                        "sha256": "",
                        "bytes": placeholder.stat().st_size,
                    }
                ],
            }
            manifest_path = capsule_dir / "manifest.json"
            manifest["files"][0]["sha256"] = hashlib.sha256(placeholder.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            out_buf = io.StringIO()
            with redirect_stdout(out_buf):
                rc = cmd_restore(
                    SimpleNamespace(
                        capsule=capsule_dir,
                        dry_run=True,
                        apply=False,
                        db=str(Path(td) / "target.sqlite"),
                        json=True,
                    )
                )
            self.assertEqual(rc, 2)
            out = json.loads(out_buf.getvalue())
            self.assertFalse(out["ok"])
            codes = [c.get("code") for c in out.get("conflicts", []) if isinstance(c, dict)]
            self.assertIn("unsupported_manifest_schema", codes)

    def test_restore_apply_rejects_non_empty_target(self):
        with tempfile.TemporaryDirectory() as td:
            source_db = Path(td) / "source.sqlite"
            target_db = Path(td) / "target.sqlite"
            export_root = Path(td) / "exports"

            conn = sqlite3.connect(source_db)
            conn.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, summary TEXT)")
            conn.execute(
                "INSERT INTO observations (id, ts, kind, summary) VALUES (?, ?, ?, ?)",
                (1, "2026-03-30T03:00:00Z", "fact", "restore source"),
            )
            conn.commit()
            conn.close()

            target_conn = sqlite3.connect(target_db)
            target_conn.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, summary TEXT)")
            target_conn.execute(
                "INSERT INTO observations (id, ts, kind, summary) VALUES (?, ?, ?, ?)",
                (9, "2026-03-30T04:00:00Z", "fact", "already live"),
            )
            target_conn.commit()
            target_conn.close()

            export_buf = io.StringIO()
            with redirect_stdout(export_buf):
                export_rc = cmd_export_canonical(
                    SimpleNamespace(dry_run=False, db=str(source_db), to=str(export_root), json=True)
                )
            self.assertEqual(export_rc, 0)
            capsule_dir = Path(json.loads(export_buf.getvalue())["artifact_dir"])

            out_buf = io.StringIO()
            with redirect_stdout(out_buf):
                rc = cmd_restore(
                    SimpleNamespace(
                        capsule=capsule_dir,
                        dry_run=False,
                        apply=True,
                        db=str(target_db),
                        json=True,
                    )
                )
            self.assertEqual(rc, 2)
            out = json.loads(out_buf.getvalue())
            self.assertFalse(out["ok"])
            codes = [c.get("code") for c in out.get("conflicts", []) if isinstance(c, dict)]
            self.assertIn("non_empty_target_store", codes)


if __name__ == "__main__":
    unittest.main()
