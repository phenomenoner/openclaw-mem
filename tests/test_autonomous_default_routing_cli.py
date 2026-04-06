import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, _episodic_build_search_text, _insert_observation, build_parser
from openclaw_mem.graph.refresh import refresh_topology_file


class TestAutonomousDefaultRoutingCli(unittest.TestCase):
    def _run(self, conn, argv, *, expect_exit=None):
        args = build_parser().parse_args(argv)
        args.db = getattr(args, "db", None) or getattr(args, "db_global", None) or ":memory:"
        args.json = bool(getattr(args, "json", False) or getattr(args, "json_global", False))
        buf = io.StringIO()
        with redirect_stdout(buf):
            if expect_exit is None:
                args.func(conn, args)
            else:
                with self.assertRaises(SystemExit) as cm:
                    args.func(conn, args)
                self.assertEqual(cm.exception.code, expect_exit)
        text = buf.getvalue().strip()
        return json.loads(text) if text else None

    def _insert_episode(
        self,
        conn,
        *,
        event_id: str,
        ts_ms: int,
        scope: str,
        session_id: str,
        summary: str,
        payload: dict | None = None,
        event_type: str = "conversation.user",
    ):
        payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
        refs_json = None
        conn.execute(
            """
            INSERT INTO episodic_events (
                event_id, ts_ms, scope, session_id, agent_id, type, summary,
                payload_json, refs_json, redacted, schema_version, created_at, search_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                event_id,
                ts_ms,
                scope,
                session_id,
                "main",
                event_type,
                summary,
                payload_json,
                refs_json,
                "v0",
                "2026-04-06T08:00:00Z",
                _episodic_build_search_text(summary=summary, payload_json=payload_json, refs_json=refs_json),
            ),
        )
        conn.commit()

    def test_episodes_search_groups_matches_by_session(self):
        conn = _connect(":memory:")
        try:
            self._insert_episode(
                conn,
                event_id="ev-1",
                ts_ms=1000,
                scope="proj-x",
                session_id="sess-1",
                summary="Discuss readiness bridge",
                payload={"text": "Need autonomous default routing bridge today"},
            )
            self._insert_episode(
                conn,
                event_id="ev-2",
                ts_ms=1001,
                scope="proj-x",
                session_id="sess-1",
                summary="Transcript recall should help fail-open routing",
                payload={"text": "episodes search fallback"},
                event_type="conversation.assistant",
            )
            self._insert_episode(
                conn,
                event_id="ev-3",
                ts_ms=1002,
                scope="proj-x",
                session_id="sess-2",
                summary="Weather note",
                payload={"text": "sunny today"},
            )

            out = self._run(conn, ["episodes", "search", "routing", "--scope", "proj-x", "--json"])
            self.assertEqual(out["kind"], "openclaw-mem.episodes.search.v0")
            self.assertEqual(out["result"]["count"], 1)
            session = out["result"]["sessions"][0]
            self.assertEqual(session["session_id"], "sess-1")
            self.assertGreaterEqual(session["hit_count"], 2)
            self.assertIn("episodes replay sess-1", session["replay_hint"]["command"])
        finally:
            conn.close()

    def test_graph_readiness_reports_green_when_refresh_and_support_align(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_path = root / "mem.sqlite"
            topology_path = root / "topology.json"
            topology_path.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "project.openclaw-mem", "type": "project", "tags": ["repo"], "metadata": {}},
                            {"id": "doc.readiness", "type": "doc", "tags": ["sop"], "metadata": {}},
                        ],
                        "edges": [
                            {
                                "src": "project.openclaw-mem",
                                "dst": "doc.readiness",
                                "type": "documents",
                                "provenance": "docs/readiness.md",
                                "metadata": {},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            refresh_topology_file(topology_path=str(topology_path), db_path=str(db_path))
            conn = _connect(str(db_path))
            try:
                _insert_observation(
                    conn,
                    {
                        "ts": "2026-04-06T08:00:00Z",
                        "kind": "note",
                        "tool_name": "graph.capture-md",
                        "summary": "[MD] readiness.md#Autonomous routing bridge",
                        "detail": {
                            "scope": "proj-x",
                            "source_path": str(topology_path),
                            "rel_path": "docs/readiness.md",
                            "heading": "Autonomous routing bridge",
                        },
                    },
                )
                conn.commit()

                out = self._run(
                    conn,
                    ["--db", str(db_path), "--json", "graph", "readiness", "--support-window-hours", "100000"],
                )
                self.assertEqual(out["kind"], "openclaw-mem.graph.readiness.v0")
                self.assertEqual(out["result"]["verdict"], "green")
                self.assertTrue(out["result"]["ready_for_autonomous_match"])
            finally:
                conn.close()

    def test_route_auto_prefers_graph_when_ready_and_candidates_exist(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_path = root / "mem.sqlite"
            topology_path = root / "topology.json"
            topology_path.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "project.openclaw-mem", "type": "project", "tags": ["repo"], "metadata": {}},
                            {"id": "doc.graph-semantic", "type": "doc", "tags": ["sop"], "metadata": {}},
                        ],
                        "edges": [
                            {
                                "src": "project.openclaw-mem",
                                "dst": "doc.graph-semantic",
                                "type": "documents",
                                "provenance": "docs/graph-semantic.md",
                                "metadata": {},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            refresh_topology_file(topology_path=str(topology_path), db_path=str(db_path))

            workspace = root / "workspace"
            playbook_repo = workspace / "openclaw-async-coding-playbook"
            playbook_repo.mkdir(parents=True)
            (playbook_repo / ".git").mkdir()
            project_doc = playbook_repo / "projects" / "openclaw-mem" / "TECH_NOTES" / "graph-semantic.md"
            project_doc.parent.mkdir(parents=True)
            project_doc.write_text("# graph semantic memory\n", encoding="utf-8")

            conn = _connect(str(db_path))
            try:
                _insert_observation(
                    conn,
                    {
                        "ts": "2026-04-06T08:00:00Z",
                        "kind": "note",
                        "tool_name": "graph.capture-md",
                        "summary": "[MD] graph-semantic.md#Graph semantic memory roadmap",
                        "detail": {
                            "scope": "proj-x",
                            "source_path": str(project_doc),
                            "rel_path": "projects/openclaw-mem/TECH_NOTES/graph-semantic.md",
                            "heading": "Graph semantic memory roadmap",
                        },
                    },
                )
                conn.commit()

                out = self._run(
                    conn,
                    [
                        "--db",
                        str(db_path),
                        "--json",
                        "route",
                        "auto",
                        "graph semantic memory",
                        "--scope",
                        "proj-x",
                        "--support-window-hours",
                        "100000",
                    ],
                )
                self.assertEqual(out["kind"], "openclaw-mem.route.auto.v0")
                self.assertEqual(out["selection"]["selected_lane"], "graph_match")
                self.assertEqual(out["inputs"]["graph_match"]["result"]["count"], 1)
            finally:
                conn.close()

    def test_route_auto_fails_open_to_episodes_search_when_graph_not_ready(self):
        conn = _connect(":memory:")
        try:
            self._insert_episode(
                conn,
                event_id="ev-1",
                ts_ms=1000,
                scope="proj-x",
                session_id="sess-episodes",
                summary="Need to revisit the Hermes conversation search comparison",
                payload={"text": "conversation search fallback and transcript recall"},
            )
            out = self._run(
                conn,
                [
                    "--db",
                    ":memory:",
                    "--json",
                    "route",
                    "auto",
                    "conversation search fallback",
                    "--scope",
                    "proj-x",
                ],
            )
            self.assertEqual(out["selection"]["selected_lane"], "episodes_search")
            self.assertTrue(out["selection"]["fail_open"])
            self.assertEqual(out["inputs"]["graph_match_skipped_reason"], "graph_not_ready")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
