import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from openclaw_mem.project_resolver import evaluate_routing_probes, resolve_project
from openclaw_mem.cli import build_parser


def init_repo(path: Path, remote: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "remote", "add", "origin", remote], cwd=path, check=True)


class TestProjectResolver(unittest.TestCase):
    def test_resolve_prefers_alias_map_over_adjacent_repo_name(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            alpha = root / "alpha-memory"
            beta = root / "beta-close"
            init_repo(alpha, "https://example.invalid/org/alpha-memory.git")
            init_repo(beta, "https://example.invalid/org/beta-close.git")
            project_map = root / "projects.json"
            project_map.write_text(
                json.dumps(
                    {
                        "projects": [
                            {"name": "Alpha Memory", "path": str(alpha), "aliases": ["alpha", "memory product"]},
                            {"name": "Beta Close", "path": str(beta), "aliases": ["close", "relationship continuity"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            out = resolve_project("close landing page", workspace_root=root, project_map=project_map)

        self.assertEqual(out.status, "resolved")
        self.assertIsNotNone(out.candidate)
        self.assertEqual(Path(out.candidate.path).name, "beta-close")
        self.assertIn("beta-close", out.candidate.remote or "")

    def test_eval_reports_forbidden_path_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            alpha = root / "alpha-memory"
            beta = root / "beta-close"
            init_repo(alpha, "https://example.invalid/org/alpha-memory.git")
            init_repo(beta, "https://example.invalid/org/beta-close.git")
            project_map = root / "projects.json"
            project_map.write_text(
                json.dumps({"projects": [{"name": "Beta Close", "path": str(beta), "aliases": ["close"]}]}),
                encoding="utf-8",
            )
            probes = [
                {
                    "query": "close landing page",
                    "expected_path": str(beta),
                    "expected_remote_contains": "beta-close",
                    "forbidden_path": str(alpha),
                }
            ]
            out = evaluate_routing_probes(probes, workspace_root=root, project_map=project_map)

        self.assertEqual(out["summary"], {"total": 1, "passed": 1, "failed": 0})
        self.assertTrue(out["items"][0]["ok"])

    def test_resolve_matches_hyphenated_repo_from_spaced_query(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "openclaw-mem"
            init_repo(repo, "https://example.invalid/org/openclaw-mem.git")

            out = resolve_project("openclaw mem routing", workspace_root=root)

        self.assertEqual(out.status, "resolved")
        self.assertIsNotNone(out.candidate)
        self.assertEqual(Path(out.candidate.path).name, "openclaw-mem")

    def test_parser_accepts_routing_eval(self):
        args = build_parser().parse_args(
            [
                "routing",
                "eval",
                "--probes",
                "probes.json",
                "--workspace-root",
                "/workspace",
                "--project-map",
                "projects.json",
                "--json",
            ]
        )
        self.assertEqual(args.cmd, "routing")
        self.assertEqual(args.routing_cmd, "eval")
        self.assertEqual(args.probes, "probes.json")
        self.assertEqual(args.workspace_root, "/workspace")
        self.assertTrue(args.json)


if __name__ == "__main__":
    unittest.main()
