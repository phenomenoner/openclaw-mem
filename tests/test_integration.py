import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestE2EWorkflow(unittest.TestCase):
    """End-to-end integration test for openclaw-mem CLI."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.sqlite"
        self.jsonl_path = Path(self.tmpdir.name) / "observations.jsonl"

        # Create sample JSONL data
        observations = [
            {
                "ts": "2026-02-05T10:00:00Z",
                "kind": "tool",
                "tool_name": "web_search",
                "summary": "searched for OpenClaw documentation",
                "detail": {"results": 5},
            },
            {
                "ts": "2026-02-05T10:01:00Z",
                "kind": "tool",
                "tool_name": "web_fetch",
                "summary": "fetched https://openclaw.ai/docs",
                "detail": {"ok": True},
            },
            {
                "ts": "2026-02-05T10:02:00Z",
                "kind": "tool",
                "tool_name": "exec",
                "summary": "executed git status",
                "detail": {"exit_code": 0},
            },
            {
                "ts": "2026-02-05T10:03:00Z",
                "kind": "tool",
                "tool_name": "web_search",
                "summary": "searched for gateway timeout issues",
                "detail": {"results": 3},
            },
        ]

        with self.jsonl_path.open("w") as f:
            for obs in observations:
                f.write(json.dumps(obs) + "\n")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run_cli(self, *args):
        """Run openclaw-mem CLI and return parsed JSON output."""
        cmd = [
            "uv",
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
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[1],
        )

        if result.returncode != 0:
            self.fail(f"CLI failed: {result.stderr}")

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f"Invalid JSON output: {result.stdout}")

    def test_e2e_workflow(self):
        """Test complete workflow: ingest → search → timeline → get."""

        # Step 1: Ingest JSONL
        result = self._run_cli("ingest", "--file", str(self.jsonl_path))
        self.assertEqual(result["inserted"], 4)
        self.assertIn("ids", result)

        # Step 2: Status check
        result = self._run_cli("status")
        self.assertEqual(result["count"], 4)
        self.assertIsNotNone(result["min_ts"])
        self.assertIsNotNone(result["max_ts"])

        # Step 3: Search for "web_search"
        result = self._run_cli("search", "web_search", "--limit", "10")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)  # 2 web_search observations
        self.assertEqual(result[0]["tool_name"], "web_search")
        search_id = result[0]["id"]

        # Step 4: Timeline around search result
        result = self._run_cli("timeline", str(search_id), "--window", "2")
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 1)

        # Step 5: Get full details
        result = self._run_cli("get", str(search_id))
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], search_id)
        self.assertEqual(result[0]["tool_name"], "web_search")
        self.assertIn("detail_json", result[0])

        # Verify detail JSON is parseable
        detail = json.loads(result[0]["detail_json"])
        self.assertEqual(detail["results"], 5)

    def test_search_with_fts_syntax(self):
        """Test FTS5 query syntax."""
        # Ingest data
        self._run_cli("ingest", "--file", str(self.jsonl_path))

        # Search with FTS5 OR operator
        result = self._run_cli("search", "gateway OR timeout", "--limit", "10")
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 1)

        # Search with exact phrase
        result = self._run_cli("search", '"gateway timeout"', "--limit", "10")
        self.assertIsInstance(result, list)

    def test_empty_search_results(self):
        """Test search with no matches."""
        # Ingest data
        self._run_cli("ingest", "--file", str(self.jsonl_path))

        # Search for nonexistent term
        result = self._run_cli("search", "nonexistent_term_xyz", "--limit", "10")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_get_nonexistent_id(self):
        """Test get command with ID that doesn't exist."""
        # Ingest data
        self._run_cli("ingest", "--file", str(self.jsonl_path))

        # Try to get ID 999 (doesn't exist)
        result = self._run_cli("get", "999")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()
