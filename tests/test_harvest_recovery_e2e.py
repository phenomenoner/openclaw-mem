import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestHarvestRecoveryE2E(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.sqlite"
        self.source = Path(self.tmpdir.name) / "openclaw-mem-observations.jsonl"
        self.archive_dir = Path(self.tmpdir.name) / "archive"

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run_cli(self, *args):
        uv = shutil.which("uv")
        if uv:
            cmd = [
                uv,
                "run",
                "--python",
                "3.13",
                "--",
                "python",
                "-m",
                "openclaw_mem",
                "--db",
                str(self.db_path),
                "--json",
                *args,
            ]
        else:
            cmd = [
                sys.executable,
                "-m",
                "openclaw_mem",
                "--db",
                str(self.db_path),
                "--json",
                *args,
            ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[1],
        )

        if result.returncode != 0:
            self.fail(f"CLI failed: rc={result.returncode}\nstderr=\n{result.stderr}\nstdout=\n{result.stdout}")

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f"Invalid JSON output:\n{result.stdout}")

    def test_harvest_recovers_orphan_processing_file(self):
        obs = {
            "ts": "2026-02-18T00:00:00Z",
            "kind": "tool",
            "tool_name": "memory_store",
            "summary": "TODO: verify harvest crash recovery",
            "detail": {"ok": True},
        }
        self.source.write_text(json.dumps(obs, ensure_ascii=False) + "\n", encoding="utf-8")

        # Simulate a crash after rotation: source has already been renamed to a *.processing file.
        processing = self.source.with_name(self.source.name + ".20260218_000000.processing")
        self.source.rename(processing)
        self.assertFalse(self.source.exists())
        self.assertTrue(processing.exists())

        out = self._run_cli(
            "harvest",
            "--source",
            str(self.source),
            "--archive-dir",
            str(self.archive_dir),
            "--no-embed",
            "--no-update-index",
        )

        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("ingested"), 1)
        self.assertEqual(out.get("processed_files"), 1)
        self.assertTrue(out.get("recovered"))
        self.assertFalse(out.get("rotated"))

        # File should be archived.
        self.assertFalse(processing.exists())
        self.assertTrue((self.archive_dir / processing.name).exists())


if __name__ == "__main__":
    unittest.main()
