import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import optimize_assist_runner as runner


class TestOptimizeAssistRunner(unittest.TestCase):
    def test_build_parser_parses_apply_flags(self):
        args = runner.build_parser().parse_args(
            [
                "--python",
                "python3",
                "--db",
                "/tmp/openclaw-mem.sqlite",
                "--runner-root",
                "/tmp/runner",
                "--operator",
                "lyria",
                "--allow-apply",
                "--scope",
                "team/alpha",
                "--limit",
                "400",
                "--stale-days",
                "45",
                "--lifecycle-limit",
                "80",
                "--top",
                "4",
                "--max-rows-per-run",
                "2",
                "--max-rows-per-24h",
                "6",
                "--lane",
                "observations.assist",
                "--json",
            ]
        )
        self.assertEqual(args.python, "python3")
        self.assertTrue(args.allow_apply)
        self.assertEqual(args.scope, "team/alpha")
        self.assertEqual(args.max_rows_per_run, 2)
        self.assertTrue(args.json)

    def test_run_pipeline_writes_packet_files_and_summary(self):
        with tempfile.TemporaryDirectory() as td:
            args = SimpleNamespace(
                python="python3",
                db="/tmp/openclaw-mem.sqlite",
                runner_root=td,
                operator="lyria",
                allow_apply=False,
                approve_stale=True,
                scope="team/alpha",
                limit=100,
                stale_days=60,
                lifecycle_limit=50,
                top=5,
                max_rows_per_run=5,
                max_rows_per_24h=20,
                lane="observations.assist",
                json=True,
            )
            outputs = [
                runner.CommandResult(
                    argv=["evolution"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.evolution-review.v0", "counts": {"items": 2}}),
                    stderr="",
                ),
                runner.CommandResult(
                    argv=["governor"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.governor-review.v0", "counts": {"approvedForApply": 1}}),
                    stderr="",
                ),
                runner.CommandResult(
                    argv=["assist"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.assist.after.v1", "result": "dry_run", "applied_rows": 0, "skipped_rows": 1, "blocked_by_caps": []}),
                    stderr="",
                ),
            ]

            with patch.object(runner, "_run", side_effect=outputs):
                out = runner.run_pipeline(args)

            self.assertEqual(out["mode"], "dry_run")
            self.assertEqual(out["counts"]["evolution_candidates"], 2)
            self.assertEqual(out["counts"]["governor_approved"], 1)
            self.assertEqual(out["results"]["assist_result"], "dry_run")
            run_dir = Path(out["artifacts"]["run_dir"])
            self.assertTrue((run_dir / "evolution.json").exists())
            self.assertTrue((run_dir / "governor.json").exists())
            self.assertTrue((run_dir / "assist-after.json").exists())
            self.assertIn("--dry-run", out["commands"]["assist_apply"])

    def test_run_pipeline_raises_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as td:
            args = SimpleNamespace(
                python="python3",
                db="/tmp/openclaw-mem.sqlite",
                runner_root=td,
                operator="lyria",
                allow_apply=False,
                approve_stale=True,
                scope=None,
                limit=100,
                stale_days=60,
                lifecycle_limit=50,
                top=5,
                max_rows_per_run=5,
                max_rows_per_24h=20,
                lane="observations.assist",
                json=True,
            )
            outputs = [
                runner.CommandResult(argv=["evolution"], returncode=0, stdout="not-json", stderr=""),
            ]
            with patch.object(runner, "_run", side_effect=outputs):
                with self.assertRaises(runner.RunnerError):
                    runner.run_pipeline(args)


if __name__ == "__main__":
    unittest.main()
