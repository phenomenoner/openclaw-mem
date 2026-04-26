import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openclaw_mem.cli import _connect, build_parser


class TestEngineSnapshotsCli(unittest.TestCase):
    def _run(self, argv, *, expect_exit=None):
        conn = _connect(":memory:")
        args = build_parser().parse_args(argv)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                if expect_exit is None:
                    args.func(conn, args)
                else:
                    with self.assertRaises(SystemExit) as cm:
                        args.func(conn, args)
                    self.assertEqual(cm.exception.code, expect_exit)
        finally:
            conn.close()
        out = buf.getvalue().strip()
        return json.loads(out) if out else None

    def test_snapshot_create_list_checkout_delete_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "lancedb"
            db.mkdir()
            (db / "table.lance").write_text("v1", encoding="utf-8")
            snaps = root / "snapshots"

            created = self._run(
                [
                    "engine",
                    "snapshot",
                    "create",
                    "--tag",
                    "pre-change_1",
                    "--reason",
                    "before risky test",
                    "--db-path",
                    str(db),
                    "--snapshots-dir",
                    str(snaps),
                    "--json",
                ]
            )
            self.assertTrue(created["ok"])
            self.assertEqual(created["tag"], "pre-change_1")
            self.assertEqual(created["stats"]["fileCount"], 1)
            self.assertEqual(created["stats"]["files"][0]["path"], "table.lance")
            self.assertRegex(created["stats"]["files"][0]["sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(created["stats"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertNotIn("reason", created)
            self.assertNotIn("v1", json.dumps(created))
            self.assertNotIn("before risky test", json.dumps(created))
            self.assertTrue((snaps / "pre-change_1" / "manifest.json").exists())
            manifest = json.loads((snaps / "pre-change_1" / "manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn("reason", manifest)
            self.assertNotIn("before risky test", json.dumps(manifest))

            listed = self._run(["engine", "snapshot", "list", "--snapshots-dir", str(snaps), "--json"])
            self.assertEqual(listed["count"], 1)
            self.assertEqual(listed["items"][0]["tag"], "pre-change_1")
            self.assertRegex(listed["items"][0]["stats"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertNotIn("reason", listed["items"][0])
            self.assertNotIn("before risky test", json.dumps(listed))

            (db / "table.lance").write_text("v2", encoding="utf-8")
            checkout_blocked = self._run(
                ["engine", "snapshot", "checkout", "--tag", "pre-change_1", "--db-path", str(db), "--snapshots-dir", str(snaps), "--json"],
                expect_exit=2,
            )
            self.assertFalse(checkout_blocked["ok"])

            checked = self._run(
                [
                    "engine",
                    "snapshot",
                    "checkout",
                    "--tag",
                    "pre-change_1",
                    "--db-path",
                    str(db),
                    "--snapshots-dir",
                    str(snaps),
                    "--yes",
                    "--json",
                ]
            )
            self.assertTrue(checked["ok"])
            self.assertTrue(checked["restartRequired"])
            self.assertEqual((db / "table.lance").read_text(encoding="utf-8"), "v1")
            self.assertTrue(Path(checked["previousDbPath"]).exists())

            delete_blocked = self._run(
                ["engine", "snapshot", "delete", "--tag", "pre-change_1", "--snapshots-dir", str(snaps), "--json"],
                expect_exit=2,
            )
            self.assertFalse(delete_blocked["ok"])

            deleted = self._run(["engine", "snapshot", "delete", "--tag", "pre-change_1", "--snapshots-dir", str(snaps), "--yes", "--json"])
            self.assertTrue(deleted["ok"])
            self.assertFalse((snaps / "pre-change_1").exists())

    def test_snapshot_create_skips_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "lancedb"
            db.mkdir()
            outside = root / "outside-secret.txt"
            outside.write_text("do not copy", encoding="utf-8")
            (db / "external-link").symlink_to(outside)
            snaps = root / "snapshots"

            out = self._run(
                [
                    "engine",
                    "snapshot",
                    "create",
                    "--tag",
                    "skip-symlink",
                    "--db-path",
                    str(db),
                    "--snapshots-dir",
                    str(snaps),
                    "--json",
                ]
            )
            self.assertTrue(out["ok"])
            self.assertFalse((snaps / "skip-symlink" / "data" / "external-link").exists())

    def test_snapshot_checkout_restores_backup_after_partial_copy_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "lancedb"
            db.mkdir()
            (db / "table.lance").write_text("v1", encoding="utf-8")
            snaps = root / "snapshots"
            self._run(["engine", "snapshot", "create", "--tag", "safe", "--db-path", str(db), "--snapshots-dir", str(snaps), "--json"])
            (db / "table.lance").write_text("v2", encoding="utf-8")

            def failing_copytree(src, dst, *args, **kwargs):
                Path(dst).mkdir(parents=True, exist_ok=True)
                (Path(dst) / "partial").write_text("broken", encoding="utf-8")
                raise OSError("simulated copy failure")

            with patch("openclaw_mem.cli.shutil.copytree", failing_copytree):
                with self.assertRaises(OSError):
                    self._run(["engine", "snapshot", "checkout", "--tag", "safe", "--db-path", str(db), "--snapshots-dir", str(snaps), "--yes", "--json"])

            self.assertEqual((db / "table.lance").read_text(encoding="utf-8"), "v2")
            self.assertFalse((db / "partial").exists())

    def test_snapshot_rejects_path_traversal_tag(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "lancedb"
            db.mkdir()
            out = self._run(
                [
                    "engine",
                    "snapshot",
                    "create",
                    "--tag",
                    "../escape",
                    "--db-path",
                    str(db),
                    "--snapshots-dir",
                    str(root / "snapshots"),
                    "--json",
                ],
                expect_exit=2,
            )
            self.assertFalse(out["ok"])
            self.assertIn("tag", out["error"])


if __name__ == "__main__":
    unittest.main()
