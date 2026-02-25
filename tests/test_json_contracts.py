import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestJsonContracts(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(__file__).resolve().parents[1]
        self.db_path = Path(self.tmpdir.name) / "test.sqlite"
        self.source = Path(self.tmpdir.name) / "openclaw-mem-observations.jsonl"
        self.state_path = Path(self.tmpdir.name) / "triage-state.json"

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

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.repo_root,
        )

    def _run_json_ok(self, *args):
        result = self._run_cli(*args)
        if result.returncode != 0:
            self.fail(
                f"CLI failed: rc={result.returncode}\\nstderr=\\n{result.stderr}\\nstdout=\\n{result.stdout}"
            )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f"Invalid JSON output:\\n{result.stdout}")

    def test_harvest_json_contract_v0(self):
        out = self._run_json_ok(
            "harvest",
            "--source",
            str(self.source),
            "--no-embed",
            "--no-update-index",
        )

        self.assertEqual(out["kind"], "openclaw-mem.harvest.v0")
        self.assertIsInstance(out["ts"], str)
        self.assertIsInstance(out["version"], dict)
        self.assertEqual(out["version"].get("schema"), "v0")
        self.assertIn("openclaw_mem", out["version"])
        self.assertIn("total_seen", out)
        self.assertIn("graded_filled", out)
        self.assertIn("skipped_existing", out)
        self.assertIn("skipped_disabled", out)
        self.assertIn("scorer_errors", out)
        self.assertIn("label_counts", out)

    def test_triage_json_contract_v0(self):
        out = self._run_json_ok(
            "triage",
            "--mode",
            "heartbeat",
            "--state-path",
            str(self.state_path),
        )

        self.assertEqual(out["kind"], "openclaw-mem.triage.v0")
        self.assertIsInstance(out["ts"], str)
        self.assertIsInstance(out["version"], dict)
        self.assertEqual(out["version"].get("schema"), "v0")
        self.assertIn("openclaw_mem", out["version"])
        self.assertIn("needs_attention", out)
        self.assertIn("observations", out)
        self.assertIn("cron", out)
        self.assertIn("tasks", out)


if __name__ == "__main__":
    unittest.main()
