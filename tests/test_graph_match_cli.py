from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, _insert_observation, cmd_graph_match


class TestGraphMatchCli(unittest.TestCase):
    def test_cmd_graph_match_groups_evidence_into_project_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)

            playbook_repo = workspace / "openclaw-async-coding-playbook"
            playbook_repo.mkdir()
            (playbook_repo / ".git").mkdir()
            project_doc = playbook_repo / "projects" / "openclaw-mem" / "TECH_NOTES" / "graph-semantic.md"
            project_doc.parent.mkdir(parents=True)
            project_doc.write_text("# graph semantic memory\n", encoding="utf-8")

            mem_repo = workspace / "openclaw-mem"
            mem_repo.mkdir()
            (mem_repo / ".git").mkdir()
            spec_doc = mem_repo / "docs" / "specs" / "graph-match-v0.md"
            spec_doc.parent.mkdir(parents=True)
            spec_doc.write_text("# graph match v0\n", encoding="utf-8")

            other_repo = workspace / "steamer"
            other_repo.mkdir()
            (other_repo / ".git").mkdir()
            other_doc = other_repo / "docs" / "roadmap.md"
            other_doc.parent.mkdir(parents=True)
            other_doc.write_text("# execution cadence\n", encoding="utf-8")

            db_path = root / "mem.sqlite"
            conn = _connect(str(db_path))
            try:
                _insert_observation(
                    conn,
                    {
                        "kind": "note",
                        "tool_name": "graph.capture-md",
                        "summary": "[MD] graph-semantic.md#Graph semantic memory roadmap",
                        "detail": {
                            "source_path": str(project_doc),
                            "rel_path": "projects/openclaw-mem/TECH_NOTES/graph-semantic.md",
                            "heading": "Graph semantic memory roadmap",
                            "start_line": 1,
                            "end_line": 20,
                        },
                    },
                )
                _insert_observation(
                    conn,
                    {
                        "kind": "note",
                        "tool_name": "graph.capture-md",
                        "summary": "[MD] graph-match-v0.md#Graph semantic memory architecture",
                        "detail": {
                            "source_path": str(spec_doc),
                            "rel_path": "docs/specs/graph-match-v0.md",
                            "heading": "Graph semantic memory architecture",
                            "start_line": 1,
                            "end_line": 12,
                        },
                    },
                )
                _insert_observation(
                    conn,
                    {
                        "kind": "note",
                        "tool_name": "graph.capture-md",
                        "summary": "[MD] roadmap.md#Steamer cadence",
                        "detail": {
                            "source_path": str(other_doc),
                            "rel_path": "docs/roadmap.md",
                            "heading": "Steamer execution cadence",
                            "start_line": 1,
                            "end_line": 8,
                        },
                    },
                )
                conn.commit()

                args = type(
                    "Args",
                    (),
                    {
                        "query": "graph semantic memory",
                        "scope": None,
                        "limit": 5,
                        "support_limit": 3,
                        "search_limit": 20,
                        "json": True,
                    },
                )()

                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_graph_match(conn, args)

                out = json.loads(buf.getvalue())
                self.assertEqual(out["kind"], "openclaw-mem.graph.match.v0")
                self.assertEqual(out["result"]["count"], 1)
                cand = out["result"]["candidates"][0]
                self.assertEqual(cand["candidateRef"], "project:openclaw-mem")
                self.assertEqual(cand["title"], "openclaw-mem")
                self.assertEqual(cand["support_count"], 2)
                self.assertIn("query:graph semantic memory", cand["explanation_path"])
                self.assertIn("project:openclaw-mem", cand["explanation_path"])
                related_types = {item["type"] for item in cand["related_items"]}
                self.assertIn("task_or_slice", related_types)
                self.assertIn("concept", related_types)
                self.assertEqual(
                    cand["supporting_records"][0]["provenance_ref"]["kind"],
                    "file_line",
                )
            finally:
                conn.close()

    def test_cmd_graph_match_scope_filter_can_infer_scope_from_repo_root_when_detail_scope_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)

            mem_repo = workspace / "openclaw-mem"
            mem_repo.mkdir()
            (mem_repo / ".git").mkdir()
            skill_doc = mem_repo / "skills" / "route-auto-synthesis.ops.md"
            skill_doc.parent.mkdir(parents=True)
            skill_doc.write_text("# route auto synthesis\n", encoding="utf-8")

            other_repo = workspace / "steamer"
            other_repo.mkdir()
            (other_repo / ".git").mkdir()
            other_doc = other_repo / "docs" / "route-auto.md"
            other_doc.parent.mkdir(parents=True)
            other_doc.write_text("# route auto\n", encoding="utf-8")

            db_path = root / "mem.sqlite"
            conn = _connect(str(db_path))
            try:
                _insert_observation(
                    conn,
                    {
                        "kind": "note",
                        "tool_name": "graph.capture-md",
                        "summary": "[MD] route-auto-synthesis.ops.md#Route auto synthesis",
                        "detail": {
                            "source_path": str(skill_doc),
                            "rel_path": "skills/route-auto-synthesis.ops.md",
                            "heading": "Route auto synthesis",
                            "start_line": 1,
                            "end_line": 5,
                        },
                    },
                )
                _insert_observation(
                    conn,
                    {
                        "kind": "note",
                        "tool_name": "graph.capture-md",
                        "summary": "[MD] route-auto.md#Steamer route auto",
                        "detail": {
                            "source_path": str(other_doc),
                            "rel_path": "docs/route-auto.md",
                            "heading": "Steamer route auto",
                            "start_line": 1,
                            "end_line": 5,
                        },
                    },
                )
                conn.commit()

                args = type(
                    "Args",
                    (),
                    {
                        "query": "route auto synthesis",
                        "scope": "openclaw-mem",
                        "limit": 5,
                        "support_limit": 3,
                        "search_limit": 20,
                        "json": True,
                    },
                )()

                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_graph_match(conn, args)

                out = json.loads(buf.getvalue())
                self.assertEqual(out["result"]["count"], 1)
                cand = out["result"]["candidates"][0]
                self.assertEqual(cand["candidateRef"], "project:openclaw-mem")
                self.assertEqual(cand["locator_kind"], "repo_root")
                self.assertEqual(cand["support_count"], 1)
            finally:
                conn.close()
