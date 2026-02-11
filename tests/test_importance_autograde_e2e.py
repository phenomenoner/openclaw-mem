import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestImportanceAutogradeE2E(unittest.TestCase):
    """E2E tests that OPENCLAW_MEM_IMPORTANCE_SCORER applies during ingest/harvest.

    These tests are intentionally black-box: they invoke the CLI and inspect the
    resulting SQLite rows.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.sqlite"
        self.repo_root = Path(__file__).resolve().parents[1]

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run_cli(self, *args: str, env: dict | None = None) -> dict:
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
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        r = subprocess.run(cmd, capture_output=True, text=True, cwd=self.repo_root, env=merged_env)
        if r.returncode != 0:
            self.fail(f"CLI failed (code={r.returncode}):\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}")

        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError as e:
            self.fail(f"Invalid JSON output: {e}\nSTDOUT:\n{r.stdout}")

    def _read_only_row(self) -> dict:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM observations ORDER BY id ASC LIMIT 1").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        return dict(row)

    def test_ingest_autogrades_importance_when_missing(self):
        jsonl_path = Path(self.tmpdir.name) / "obs.jsonl"
        obs = {
            "ts": "2026-02-11T08:00:00Z",
            "kind": "tool",
            "tool_name": "cron.add",
            "summary": "Created cron job jobId=00000000-0000-0000-0000-000000000000 for importance grading; set OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1",
            "detail": {"ok": True},
        }
        jsonl_path.write_text(json.dumps(obs, ensure_ascii=False) + "\n", encoding="utf-8")

        out = self._run_cli(
            "ingest",
            "--file",
            str(jsonl_path),
            env={"OPENCLAW_MEM_IMPORTANCE_SCORER": "heuristic-v1"},
        )
        self.assertEqual(out["inserted"], 1)

        row = self._read_only_row()
        detail = json.loads(row["detail_json"])
        self.assertIn("importance", detail)
        self.assertIsInstance(detail["importance"], dict)
        self.assertEqual(detail["importance"].get("method"), "heuristic-v1")
        self.assertEqual(int(detail["importance"].get("version")), 1)
        self.assertIn(detail["importance"].get("label"), {"ignore", "nice_to_have", "must_remember"})

    def test_harvest_autogrades_importance_when_missing(self):
        # Use harvest since it's the default "log ingestion" path.
        source = Path(self.tmpdir.name) / "openclaw-mem-observations.jsonl"
        archive_dir = Path(self.tmpdir.name) / "archive"
        obs = {
            "ts": "2026-02-11T08:01:00Z",
            "kind": "tool",
            "tool_name": "gateway.config.get",
            "summary": "Decision: keep MVP autograde behind OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1 (jobId=11111111-1111-1111-1111-111111111111)",
            "detail": {"ok": True},
        }
        source.write_text(json.dumps(obs, ensure_ascii=False) + "\n", encoding="utf-8")

        out = self._run_cli(
            "harvest",
            "--source",
            str(source),
            "--archive-dir",
            str(archive_dir),
            "--no-embed",
            "--no-update-index",
            env={"OPENCLAW_MEM_IMPORTANCE_SCORER": "heuristic-v1"},
        )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("ingested"), 1)

        row = self._read_only_row()
        detail = json.loads(row["detail_json"])
        self.assertIn("importance", detail)
        self.assertEqual(detail["importance"].get("method"), "heuristic-v1")


if __name__ == "__main__":
    unittest.main()
