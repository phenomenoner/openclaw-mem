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

    def test_ingest_autogrades_importance_when_missing_via_cli_override(self):
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
            "--importance-scorer",
            "heuristic-v1",
        )
        self.assertEqual(out["inserted"], 1)
        self.assertEqual(out["total_seen"], 1)
        self.assertEqual(out["graded_filled"], 1)
        self.assertEqual(out["skipped_existing"], 0)
        self.assertEqual(out["skipped_disabled"], 0)
        self.assertEqual(out["scorer_errors"], 0)
        self.assertEqual(sum(out["label_counts"].values()), 1)

        row = self._read_only_row()
        detail = json.loads(row["detail_json"])
        self.assertIn("importance", detail)
        self.assertIsInstance(detail["importance"], dict)
        self.assertEqual(detail["importance"].get("method"), "heuristic-v1")
        self.assertEqual(int(detail["importance"].get("version")), 1)
        self.assertIn(detail["importance"].get("label"), {"ignore", "nice_to_have", "must_remember"})

    def test_ingest_env_fallback_still_autogrades_when_flag_absent(self):
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
        self.assertEqual(out["total_seen"], 1)
        self.assertEqual(out["graded_filled"], 1)
        self.assertEqual(out["scorer_errors"], 0)

        row = self._read_only_row()
        detail = json.loads(row["detail_json"])
        self.assertIn("importance", detail)
        self.assertEqual(detail["importance"].get("method"), "heuristic-v1")

    def test_ingest_cli_off_disables_autograde_even_if_env_set(self):
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
            "--importance-scorer",
            "off",
            env={"OPENCLAW_MEM_IMPORTANCE_SCORER": "heuristic-v1"},
        )
        self.assertEqual(out["inserted"], 1)
        self.assertEqual(out["total_seen"], 1)
        self.assertEqual(out["graded_filled"], 0)
        self.assertEqual(out["skipped_existing"], 0)
        self.assertEqual(out["skipped_disabled"], 1)
        self.assertEqual(out["scorer_errors"], 0)
        self.assertEqual(out["label_counts"], {})

        row = self._read_only_row()
        detail = json.loads(row["detail_json"])
        self.assertNotIn("importance", detail)

    def test_ingest_fail_open_counts_scorer_errors_and_still_inserts(self):
        jsonl_path = Path(self.tmpdir.name) / "obs.jsonl"
        obs = {
            "ts": "2026-02-11T08:02:00Z",
            "kind": "tool",
            "tool_name": "cron.add",
            "summary": "Force a grader failure to validate fail-open behavior",
            "detail": {"ok": True},
        }
        jsonl_path.write_text(json.dumps(obs, ensure_ascii=False) + "\n", encoding="utf-8")

        out = self._run_cli(
            "ingest",
            "--file",
            str(jsonl_path),
            "--importance-scorer",
            "heuristic-v1",
            env={"OPENCLAW_MEM_IMPORTANCE_TEST_RAISE": "1"},
        )
        self.assertEqual(out["inserted"], 1)
        self.assertEqual(out["total_seen"], 1)
        self.assertEqual(out["graded_filled"], 0)
        self.assertEqual(out["skipped_existing"], 0)
        self.assertEqual(out["skipped_disabled"], 0)
        self.assertEqual(out["scorer_errors"], 1)

        row = self._read_only_row()
        detail = json.loads(row["detail_json"])
        self.assertNotIn("importance", detail)

    def test_harvest_autogrades_importance_when_missing_via_cli_override(self):
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
            "--importance-scorer",
            "heuristic-v1",
            "--archive-dir",
            str(archive_dir),
            "--no-embed",
            "--no-update-index",
        )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("ingested"), 1)
        self.assertEqual(out.get("total_seen"), 1)
        self.assertEqual(out.get("graded_filled"), 1)
        self.assertEqual(out.get("scorer_errors"), 0)

        row = self._read_only_row()
        detail = json.loads(row["detail_json"])
        self.assertIn("importance", detail)
        self.assertEqual(detail["importance"].get("method"), "heuristic-v1")


if __name__ == "__main__":
    unittest.main()
