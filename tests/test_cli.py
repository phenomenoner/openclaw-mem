import io
import json
import sys
import unittest
from contextlib import redirect_stdout

from openclaw_mem.cli import _connect, _summary_has_task_marker, build_parser, cmd_ingest, cmd_search, cmd_get, cmd_timeline, cmd_triage, cmd_store, cmd_hybrid, cmd_status, cmd_profile, cmd_backend, cmd_graph_index, cmd_graph_pack, cmd_graph_preflight, cmd_graph_auto_status, cmd_graph_capture_git, cmd_graph_capture_md, cmd_graph_export


class TestCliM0(unittest.TestCase):
    def test_schema_contains_english_embeddings_table(self):
        conn = _connect(":memory:")
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        self.assertIn("observation_embeddings_en", tables)

        args = type("Args", (), {"db": ":memory:", "json": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_status(conn, args)
        out = json.loads(buf.getvalue())
        self.assertIn("embeddings_en", out)
        self.assertEqual(out["embeddings_en"]["count"], 0)
        conn.close()

    def test_summary_has_task_marker_accepts_full_width_colon_and_unicode_dashes(self):
        self.assertTrue(_summary_has_task_marker("reminder：pay rent"))
        self.assertTrue(_summary_has_task_marker("ＴＯＤＯ：繳房租"))
        self.assertTrue(_summary_has_task_marker("Task－follow up on release checklist"))
        self.assertTrue(_summary_has_task_marker("Task–follow up on release checklist"))
        self.assertTrue(_summary_has_task_marker("Task—follow up on release checklist"))
        self.assertTrue(_summary_has_task_marker("Task−follow up on release checklist"))

    def test_summary_has_task_marker_accepts_lowercase_marker_with_separator(self):
        self.assertTrue(_summary_has_task_marker("todo buy milk"))
        self.assertTrue(_summary_has_task_marker("task - clean desk"))
        self.assertTrue(_summary_has_task_marker("task\tclean desk"))

    def test_summary_has_task_marker_accepts_example_formats(self):
        self.assertTrue(_summary_has_task_marker("TODO: rotate runbook"))
        self.assertTrue(_summary_has_task_marker("task- check alerts"))
        self.assertTrue(_summary_has_task_marker("(TASK): review PR"))
        self.assertTrue(_summary_has_task_marker("- [ ] TODO file patch"))

    def test_summary_has_task_marker_accepts_marker_only_forms(self):
        self.assertTrue(_summary_has_task_marker("TODO"))
        self.assertTrue(_summary_has_task_marker("[TASK]"))
        self.assertTrue(_summary_has_task_marker("(REMINDER)"))

    def test_summary_has_task_marker_accepts_bracket_wrapped_marker(self):
        self.assertTrue(_summary_has_task_marker("[TODO] buy milk"))
        self.assertTrue(_summary_has_task_marker("(task): clean desk"))
        self.assertTrue(_summary_has_task_marker("（ＲＥＭＩＮＤＥＲ） 續約網域"))
        self.assertTrue(_summary_has_task_marker("【ＴＡＳＫ】 續約網域"))

    def test_summary_has_task_marker_accepts_list_and_checkbox_prefixes(self):
        self.assertTrue(_summary_has_task_marker("- TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("* [ ] TASK: clean desk"))
        self.assertTrue(_summary_has_task_marker("+ TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("> TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("> > [ ] TASK: clean desk"))
        self.assertTrue(_summary_has_task_marker(">> TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("• [x] [REMINDER] renew domain"))
        self.assertTrue(_summary_has_task_marker("‣ TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("∙ [ ] TASK: clean desk"))
        self.assertTrue(_summary_has_task_marker("· [x] [REMINDER] renew domain"))
        self.assertTrue(_summary_has_task_marker("- [✓] TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("1. [✔] TASK: clean desk"))
        self.assertTrue(_summary_has_task_marker("1. TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("2) [ ] TASK: clean desk"))
        self.assertTrue(_summary_has_task_marker("(3) TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("a) TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("(a) TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("（ａ） TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("B. [ ] TASK: clean desk"))
        self.assertTrue(_summary_has_task_marker("iv) TODO buy milk"))
        self.assertTrue(_summary_has_task_marker("IX. [ ] TASK: clean desk"))
        self.assertTrue(_summary_has_task_marker("(iv) TODO buy milk"))

    def test_summary_has_task_marker_accepts_nested_prefix_combinations(self):
        self.assertTrue(_summary_has_task_marker("* (1) [ ] TODO: clean desk"))
        self.assertTrue(_summary_has_task_marker("• （２） [x] [TASK] rotate notes"))
        self.assertTrue(_summary_has_task_marker("> - a) [ ] TODO: clean desk"))
        self.assertTrue(_summary_has_task_marker("- > (iv) [ ] TODO: clean desk"))
        self.assertTrue(_summary_has_task_marker("- a) [ ] TODO: clean desk"))
        self.assertTrue(_summary_has_task_marker("- (iv) [ ] TODO: clean desk"))
        self.assertTrue(_summary_has_task_marker(">>[x]TODO: compact wrappers"))
        self.assertTrue(_summary_has_task_marker("-1)TODO compact ordered marker"))

    def test_summary_has_task_marker_rejects_non_marker_prefixes_and_requires_marker_boundaries(self):
        self.assertFalse(_summary_has_task_marker("TODOLIST clean old notes"))
        self.assertFalse(_summary_has_task_marker("taskforce sync tomorrow"))
        self.assertFalse(_summary_has_task_marker("[TODOLIST] clean old notes"))
        self.assertFalse(_summary_has_task_marker("[TODO]clean old notes"))
        self.assertFalse(_summary_has_task_marker("【TODO】clean old notes"))
        self.assertTrue(_summary_has_task_marker("-TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker("+TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker(">TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker(">>TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker(">>>TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker("‣TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker("·TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker("[x]TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker("[✓]TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker("1.TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker("1)TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker("(1)TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker("a)TODO clean old notes"))
        self.assertFalse(_summary_has_task_marker("ab) TODO clean old notes"))
        self.assertFalse(_summary_has_task_marker("(ab) TODO clean old notes"))
        self.assertFalse(_summary_has_task_marker("中) TODO clean old notes"))
        self.assertFalse(_summary_has_task_marker("(中) TODO clean old notes"))
        self.assertFalse(_summary_has_task_marker("é) TODO clean old notes"))
        self.assertFalse(_summary_has_task_marker("(é) TODO clean old notes"))
        self.assertFalse(_summary_has_task_marker("in) TODO clean old notes"))
        self.assertFalse(_summary_has_task_marker("ic) TODO clean old notes"))
        self.assertFalse(_summary_has_task_marker("(iiv) TODO clean old notes"))
        self.assertTrue(_summary_has_task_marker("* (1)TODO clean old notes"))

    def test_parser_merges_global_and_command_json_flags(self):
        before_args = build_parser().parse_args(["--json", "status"])
        after_args = build_parser().parse_args(["status", "--json"])

        self.assertTrue(before_args.json_global)
        self.assertFalse(before_args.json)

        self.assertTrue(after_args.json)
        self.assertFalse(after_args.json_global)

        merged_before = bool(before_args.json or before_args.json_global)
        merged_after = bool(after_args.json or after_args.json_global)

        self.assertTrue(merged_before)
        self.assertTrue(merged_after)

    def test_graph_parser_can_parse_subcommands(self):
        a = build_parser().parse_args(["graph", "index", "hello"])
        self.assertEqual(a.cmd, "graph")
        self.assertEqual(a.graph_cmd, "index")
        self.assertEqual(a.query, "hello")

        a = build_parser().parse_args(["graph", "pack", "obs:1"])
        self.assertEqual(a.cmd, "graph")
        self.assertEqual(a.graph_cmd, "pack")
        self.assertEqual(a.ids, ["obs:1"])

        a = build_parser().parse_args(["graph", "preflight", "hello"])
        self.assertEqual(a.cmd, "graph")
        self.assertEqual(a.graph_cmd, "preflight")
        self.assertEqual(a.query, "hello")

        a = build_parser().parse_args(["graph", "auto-status"])
        self.assertEqual(a.cmd, "graph")
        self.assertEqual(a.graph_cmd, "auto-status")

        a = build_parser().parse_args(["graph", "capture-git", "--repo", "/tmp/repo"])
        self.assertEqual(a.cmd, "graph")
        self.assertEqual(a.graph_cmd, "capture-git")
        self.assertEqual(a.repo, ["/tmp/repo"])

        a = build_parser().parse_args(["graph", "capture-md", "--path", "/tmp/notes"])
        self.assertEqual(a.cmd, "graph")
        self.assertEqual(a.graph_cmd, "capture-md")
        self.assertEqual(a.path, ["/tmp/notes"])

        a = build_parser().parse_args(["graph", "export", "--query", "hello", "--to", "/tmp/graph.json"])
        self.assertEqual(a.cmd, "graph")
        self.assertEqual(a.graph_cmd, "export")
        self.assertEqual(a.query, "hello")


    def test_writeback_lancedb_parser_accepts_flags(self):
        a = build_parser().parse_args([
            "writeback-lancedb",
            "--db",
            "/tmp/sidecar.sqlite",
            "--lancedb",
            "/tmp/lancedb",
            "--table",
            "memories",
            "--limit",
            "11",
            "--batch",
            "7",
            "--dry-run",
            "--force",
            "--force-fields",
            "importance,trust_tier,category",
        ])

        self.assertEqual(a.cmd, "writeback-lancedb")
        self.assertEqual(a.db, "/tmp/sidecar.sqlite")
        self.assertEqual(a.lancedb, "/tmp/lancedb")
        self.assertEqual(a.table, "memories")
        self.assertEqual(a.limit, 11)
        self.assertEqual(a.batch, 7)
        self.assertTrue(a.dry_run)
        self.assertTrue(a.force)
        self.assertEqual(a.force_fields, "importance,trust_tier,category")

    def test_graph_index_and_pack_smoke_budgeted(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "tool",
                        "tool_name": "exec",
                        "summary": "alpha one",
                        "detail": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "tool",
                        "tool_name": "read",
                        "summary": "beta two",
                        "detail": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:02:00Z",
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "alpha three",
                        "detail": {},
                    }
                ),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        # graph index
        args = type(
            "Args",
            (),
            {
                "query": "alpha",
                "scope": None,
                "limit": 8,
                "window": 1,
                "suggest_limit": 3,
                "budget_tokens": 20,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_graph_index(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.graph.index.v0")
        self.assertIn("index_text", out)
        self.assertLessEqual(out["budget"]["estimatedTokens"], out["budget"]["budgetTokens"])

        # graph pack
        args = type(
            "Args",
            (),
            {
                "ids": ["obs:1", "2"],
                "max_items": 20,
                "budget_tokens": 30,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_graph_pack(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.graph.pack.v0")
        self.assertIn("bundle_text", out)
        self.assertIn("obs:1", out["bundle_text"])

        conn.close()

    def test_graph_preflight_smoke_selects_refs_and_respects_budget(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "tool",
                        "tool_name": "exec",
                        "summary": "alpha one",
                        "detail": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "tool",
                        "tool_name": "read",
                        "summary": "alpha two",
                        "detail": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:02:00Z",
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "beta three",
                        "detail": {},
                    }
                ),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        args = type(
            "Args",
            (),
            {
                "query": "alpha",
                "scope": None,
                "limit": 8,
                "window": 1,
                "suggest_limit": 3,
                "budget_tokens": 25,
                "take": 12,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_graph_preflight(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.graph.preflight.v0")
        self.assertIn("bundle_text", out)
        self.assertIn("obs:", out["bundle_text"])
        self.assertLessEqual(out["budget"]["estimatedTokens"], out["budget"]["budgetTokens"])
        self.assertGreaterEqual(len(out["selection"]["recordRefs"]), 1)

        conn.close()


    def test_graph_auto_status_reports_flags_and_invalid_values(self):
        from unittest.mock import patch

        conn = _connect(":memory:")

        args = type("Args", (), {"json": True})()
        with patch.dict(
            "os.environ",
            {
                "OPENCLAW_MEM_GRAPH_AUTO_RECALL": "1",
                "OPENCLAW_MEM_GRAPH_AUTO_CAPTURE": "off",
                "OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD": "maybe",
            },
            clear=False,
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_auto_status(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.graph.auto-status.v0")

        recall = out["flags"]["OPENCLAW_MEM_GRAPH_AUTO_RECALL"]
        self.assertTrue(recall["enabled"])
        self.assertTrue(recall["valid"])
        self.assertEqual(recall["reason"], "parsed_truthy")

        capture = out["flags"]["OPENCLAW_MEM_GRAPH_AUTO_CAPTURE"]
        self.assertFalse(capture["enabled"])
        self.assertTrue(capture["valid"])
        self.assertEqual(capture["reason"], "parsed_falsy")

        capture_md = out["flags"]["OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD"]
        self.assertFalse(capture_md["enabled"])
        self.assertFalse(capture_md["valid"])
        self.assertEqual(capture_md["reason"], "invalid_fallback_default")

        conn.close()

    def test_graph_auto_status_reports_unset_default_reason(self):
        from unittest.mock import patch

        conn = _connect(":memory:")

        args = type("Args", (), {"json": True})()
        with patch.dict("os.environ", {}, clear=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_auto_status(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.graph.auto-status.v0")

        for st in out["flags"].values():
            self.assertFalse(st["present"])
            self.assertFalse(st["enabled"])
            self.assertTrue(st["valid"])
            self.assertEqual(st["reason"], "unset_default")

        conn.close()

    def test_graph_capture_git_errors_cleanly_when_repo_missing(self):
        import tempfile

        conn = _connect(":memory:")
        missing_repo = "/tmp/openclaw-mem-not-a-repo"

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "repo": [missing_repo],
                "since": 24,
                "state": state_path,
                "max_commits": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_graph_capture_git(conn, args)

        self.assertEqual(cm.exception.code, 1)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["totals"]["errors"], 1)
        self.assertEqual(out["repos"][0]["inserted"], 0)

        conn.close()

    def test_graph_capture_md_smoke_is_index_only_and_idempotent(self):
        import os
        import tempfile
        import time

        conn = _connect(":memory:")

        with tempfile.TemporaryDirectory() as td:
            md_path = os.path.join(td, "notes.md")
            state_path = os.path.join(td, "graph-capture-md-state.json")

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(
                    "# Title\n\n"
                    "## Alpha\n"
                    "first line\n"
                    "```\n"
                    "## hidden\n"
                    "```\n\n"
                    "### Beta\n"
                    "second line\n"
                )

            args = type(
                "Args",
                (),
                {
                    "path": [td],
                    "include": [".md"],
                    "exclude_glob": ["**/node_modules/**", "**/.venv/**", "**/.git/**", "**/dist/**"],
                    "max_files": 200,
                    "max_sections_per_file": 50,
                    "min_heading_level": 2,
                    "state": state_path,
                    "since_hours": 24,
                    "json": True,
                },
            )()

            buf1 = io.StringIO()
            with redirect_stdout(buf1):
                cmd_graph_capture_md(conn, args)

            out1 = json.loads(buf1.getvalue())
            self.assertEqual(out1["inserted"], 2)
            self.assertEqual(out1["skipped_existing"], 0)
            self.assertEqual(out1["errors"], 0)

            now = time.time() + 2.0
            os.utime(md_path, (now, now))

            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                cmd_graph_capture_md(conn, args)

            out2 = json.loads(buf2.getvalue())
            self.assertEqual(out2["changed_files"], 1)
            self.assertEqual(out2["inserted"], 0)
            self.assertEqual(out2["skipped_existing"], 2)

            rows = conn.execute(
                "SELECT summary, detail_json FROM observations WHERE tool_name = 'graph.capture-md' ORDER BY id"
            ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(r["summary"].startswith("[MD] notes.md#") for r in rows))

            detail = json.loads(rows[0]["detail_json"])
            self.assertIn("source_path", detail)
            self.assertIn("heading", detail)
            self.assertIn("section_fingerprint", detail)
            self.assertNotIn("excerpt", detail)
            self.assertNotIn("content", detail)

        conn.close()

    def test_profile_reports_counts_labels_and_recent(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "decision",
                        "tool_name": "memory_store",
                        "summary": "Pin model for dev lane",
                        "detail": {"importance": {"score": 0.92, "label": "must_remember"}},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "task",
                        "tool_name": "memory_store",
                        "summary": "TODO: run benchmark",
                        "detail": {"importance": 0.65},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:02:00Z",
                        "kind": "tool",
                        "tool_name": "exec",
                        "summary": "lint passed",
                        "detail": {},
                    }
                ),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "text-embedding-3-small", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO observation_embeddings_en (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "text-embedding-3-small", 2, pack_f32([0.0, 1.0]), l2_norm([0.0, 1.0]), "2026-02-05T00:00:00Z"),
        )
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "db": ":memory:",
                "json": True,
                "recent_limit": 2,
                "tool_limit": 5,
                "kind_limit": 5,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_profile(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["observations"]["count"], 3)
        self.assertEqual(out["importance"]["present"], 2)
        self.assertEqual(out["importance"]["missing"], 1)
        self.assertEqual(out["importance"]["label_counts"]["must_remember"], 1)
        self.assertEqual(out["importance"]["label_counts"]["nice_to_have"], 1)
        self.assertEqual(out["importance"]["label_counts"]["unknown"], 1)
        self.assertEqual(out["embeddings"]["original"]["count"], 1)
        self.assertEqual(out["embeddings"]["english"]["count"], 1)
        self.assertLessEqual(len(out["recent"]), 2)
        self.assertEqual(out["recent"][0]["id"], 3)

        conn.close()

    def test_profile_counts_malformed_importance_as_unknown(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "decision",
                        "tool_name": "memory_store",
                        "summary": "Persist critical decision",
                        "detail": {"importance": {"label": "must remember"}},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "Malformed importance payload",
                        "detail": {"importance": {"score": "high"}},
                    }
                ),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        args = type(
            "Args",
            (),
            {
                "db": ":memory:",
                "json": True,
                "recent_limit": 5,
                "tool_limit": 5,
                "kind_limit": 5,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_profile(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["importance"]["present"], 2)
        self.assertEqual(out["importance"]["missing"], 0)
        self.assertEqual(out["importance"]["label_counts"]["must_remember"], 1)
        self.assertEqual(out["importance"]["label_counts"]["ignore"], 0)
        self.assertEqual(out["importance"]["label_counts"]["unknown"], 1)
        self.assertEqual(out["importance"]["avg_score"], 0.8)

        conn.close()

    def test_backend_reports_slot_and_readiness(self):
        conn = _connect(":memory:")

        fake_cfg = {
            "plugins": {
                "slots": {"memory": "memory-lancedb"},
                "entries": {
                    "memory-core": {"enabled": True},
                    "memory-lancedb": {
                        "enabled": True,
                        "config": {"embedding": {"apiKey": "${OPENAI_API_KEY}"}},
                    },
                    "openclaw-mem": {"enabled": True},
                },
            }
        }

        from unittest.mock import patch

        args = type("Args", (), {"json": True})()
        buf = io.StringIO()
        with patch("openclaw_mem.cli._read_openclaw_config", return_value=fake_cfg), patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
            with redirect_stdout(buf):
                cmd_backend(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["memory_slot"], "memory-lancedb")
        self.assertTrue(out["entries"]["memory-lancedb"]["embedding_api_key_ready"])
        conn.close()

    def test_ingest_preserves_extra_fields_into_detail_json(self):
        conn = _connect(":memory:")

        sample = json.dumps(
            {
                "ts": "2026-02-04T13:00:00Z",
                "kind": "tool",
                "tool_name": "memory_recall",
                "summary": "Found memories",
                "detail": {"base": 1},
                "memory_backend": "memory-lancedb",
                "memory_backend_ready": True,
                "memory_operation": "recall",
            }
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        row = conn.execute("SELECT detail_json FROM observations WHERE id = 1").fetchone()
        detail = json.loads(row["detail_json"])
        self.assertEqual(detail["base"], 1)
        self.assertEqual(detail["memory_backend"], "memory-lancedb")
        self.assertEqual(detail["memory_operation"], "recall")
        conn.close()

    def test_ingest_search_timeline_get_json(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "tool",
                        "tool_name": "cron.list",
                        "summary": "cron list called",
                        "detail": {"ok": True},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "tool",
                        "tool_name": "gateway.config.get",
                        "summary": "read gateway config",
                        "detail": {"ok": True},
                    }
                ),
            ]
        )

        # Ingest via stdin
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_ingest(conn, args)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["inserted"], 2)
            self.assertTrue(out["ids"])
        finally:
            sys.stdin = old_stdin

        # Search
        args = type("Args", (), {"query": "cron", "limit": 20, "json": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_search(conn, args)
        hits = json.loads(buf.getvalue())
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["tool_name"], "cron.list")

        # Timeline around ID 1
        args = type("Args", (), {"ids": [1], "window": 1, "json": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_timeline(conn, args)
        tl = json.loads(buf.getvalue())
        self.assertGreaterEqual(len(tl), 1)

        # Get
        args = type("Args", (), {"ids": [1, 2], "json": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_get(conn, args)
        rows = json.loads(buf.getvalue())
        self.assertEqual([r["id"] for r in rows], [1, 2])

        conn.close()

    def test_cjk_search_fallback_when_fts_misses(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "tool",
                        "tool_name": "memorybench",
                        "summary": "我今天在台北開產品會議，晚上再整理筆記。",
                        "detail": {"session_id": "s-zh-1"},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "tool",
                        "tool_name": "memorybench",
                        "summary": "I booked a train ticket to Taichung for next week.",
                        "detail": {"session_id": "s-en-1"},
                    }
                ),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        # This query is semantically related but not an exact phrase; CJK fallback should recover it.
        args = type("Args", (), {"query": "今天會議在什麼城市", "limit": 10, "json": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_search(conn, args)

        hits = json.loads(buf.getvalue())
        self.assertGreaterEqual(len(hits), 1)
        self.assertIn("台北", hits[0]["summary"])
        conn.close()

    def test_triage_exit_code_and_json(self):
        conn = _connect(":memory:")

        # Ingest one normal and one error-ish observation
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps({"ts": now, "kind": "tool", "tool_name": "web_fetch", "summary": "ok", "detail": {}}),
                json.dumps({"ts": now, "kind": "tool", "tool_name": "exec", "summary": "Error: command failed", "detail": {}}),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "observations",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        # Should signal attention
        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertTrue(out["needs_attention"])
        self.assertGreaterEqual(out["observations"]["found_new"], 1)

        conn.close()

    def test_triage_tasks_mode_dedupes_by_state(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "task",
                        "tool_name": "memory_store",
                        "summary": "TODO: buy coffee this afternoon",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        # First run: should alert
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)
        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)

        # Second run: should NOT alert again (state dedupe)
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            with self.assertRaises(SystemExit) as cm2:
                cmd_triage(conn, args)
        self.assertEqual(cm2.exception.code, 0)
        out2 = json.loads(buf2.getvalue())
        self.assertEqual(out2["tasks"]["found_new"], 0)

        conn.close()

    def test_triage_tasks_accepts_task_marker_without_colon(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "TODO buy coffee this afternoon",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "TODO buy coffee this afternoon")

        conn.close()

    def test_triage_tasks_accepts_marker_only_summary(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "TODO",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "TODO")

        conn.close()

    def test_triage_tasks_accepts_bracket_wrapped_task_marker_prefix(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "[TODO] buy coffee this afternoon",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "[TODO] buy coffee this afternoon")

        conn.close()

    def test_triage_tasks_accepts_cjk_bracket_wrapped_task_marker_prefix(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "【TODO】 buy coffee this afternoon",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "【TODO】 buy coffee this afternoon")

        conn.close()

    def test_triage_tasks_accepts_markdown_checkbox_prefixed_task_marker(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "- [ ] TODO: rotate on-call notes",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "- [ ] TODO: rotate on-call notes")

        conn.close()

    def test_triage_tasks_accepts_plus_bullet_prefixed_task_marker(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "+ TODO: rotate on-call notes",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "+ TODO: rotate on-call notes")

        conn.close()

    def test_triage_tasks_accepts_blockquote_prefixed_task_marker(self):
        import tempfile
        from datetime import datetime, timezone

        summaries = (
            "> TODO: rotate on-call notes",
            "> > [ ] TASK: rotate on-call notes",
            ">> TODO: rotate on-call notes",
            "- > (iv) [ ] TODO: rotate on-call notes",
        )

        for summary in summaries:
            with self.subTest(summary=summary):
                conn = _connect(":memory:")

                now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                sample = "\n".join(
                    [
                        json.dumps(
                            {
                                "ts": now,
                                "kind": "note",
                                "tool_name": "memory_store",
                                "summary": summary,
                                "detail": {"importance": 0.9},
                            }
                        )
                    ]
                )

                old_stdin = sys.stdin
                try:
                    sys.stdin = io.StringIO(sample)
                    args = type("Args", (), {"file": None, "json": True})()
                    with redirect_stdout(io.StringIO()):
                        cmd_ingest(conn, args)
                finally:
                    sys.stdin = old_stdin

                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
                    state_path = st.name

                args = type(
                    "Args",
                    (),
                    {
                        "mode": "tasks",
                        "since_minutes": 60,
                        "limit": 10,
                        "keywords": None,
                        "cron_jobs_path": None,
                        "tasks_since_minutes": 1440,
                        "importance_min": 0.7,
                        "state_path": state_path,
                        "json": True,
                    },
                )()

                buf = io.StringIO()
                with redirect_stdout(buf):
                    with self.assertRaises(SystemExit) as cm:
                        cmd_triage(conn, args)

                self.assertEqual(cm.exception.code, 10)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["tasks"]["found_new"], 1)
                self.assertEqual(out["tasks"]["matches"][0]["summary"], summary)

                conn.close()

    def test_triage_tasks_accepts_unicode_bullet_prefixed_task_marker(self):
        import tempfile
        from datetime import datetime, timezone

        summaries = (
            "‣ TODO: rotate on-call notes",
            "∙ [ ] TASK: rotate on-call notes",
            "· [x] [REMINDER] rotate on-call notes",
        )

        for summary in summaries:
            with self.subTest(summary=summary):
                conn = _connect(":memory:")

                now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                sample = "\n".join(
                    [
                        json.dumps(
                            {
                                "ts": now,
                                "kind": "note",
                                "tool_name": "memory_store",
                                "summary": summary,
                                "detail": {"importance": 0.9},
                            }
                        )
                    ]
                )

                old_stdin = sys.stdin
                try:
                    sys.stdin = io.StringIO(sample)
                    args = type("Args", (), {"file": None, "json": True})()
                    with redirect_stdout(io.StringIO()):
                        cmd_ingest(conn, args)
                finally:
                    sys.stdin = old_stdin

                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
                    state_path = st.name

                args = type(
                    "Args",
                    (),
                    {
                        "mode": "tasks",
                        "since_minutes": 60,
                        "limit": 10,
                        "keywords": None,
                        "cron_jobs_path": None,
                        "tasks_since_minutes": 1440,
                        "importance_min": 0.7,
                        "state_path": state_path,
                        "json": True,
                    },
                )()

                buf = io.StringIO()
                with redirect_stdout(buf):
                    with self.assertRaises(SystemExit) as cm:
                        cmd_triage(conn, args)

                self.assertEqual(cm.exception.code, 10)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["tasks"]["found_new"], 1)
                self.assertEqual(out["tasks"]["matches"][0]["summary"], summary)

                conn.close()

    def test_triage_tasks_accepts_ordered_list_prefixed_task_marker(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "1. [ ] TODO: rotate on-call notes",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "1. [ ] TODO: rotate on-call notes")

        conn.close()

    def test_triage_tasks_accepts_alpha_ordered_prefix_task_marker(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "a) [ ] TODO: rotate on-call notes",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "a) [ ] TODO: rotate on-call notes")

        conn.close()

    def test_triage_tasks_accepts_parenthesized_alpha_ordered_prefix_task_marker(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "(a) [ ] TODO: rotate on-call notes",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "(a) [ ] TODO: rotate on-call notes")

        conn.close()

    def test_triage_tasks_accepts_roman_ordered_prefix_task_marker(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "iv) [ ] TODO: rotate on-call notes",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "iv) [ ] TODO: rotate on-call notes")

        conn.close()

    def test_triage_tasks_rejects_invalid_roman_ordered_prefix(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "ic) TODO: should not match",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 0)

        conn.close()

    def test_triage_tasks_accepts_parenthesized_ordered_prefix_task_marker(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "(1) [ ] TODO: rotate on-call notes",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "(1) [ ] TODO: rotate on-call notes")

        conn.close()

    def test_triage_tasks_accepts_full_width_parenthesized_ordered_prefix_task_marker(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "（１） [ ] TODO: rotate on-call notes",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "（１） [ ] TODO: rotate on-call notes")

        conn.close()

    def test_triage_tasks_accepts_full_width_task_marker_prefix(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "ＴＡＳＫ：整理慢煮 lane 清單",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "ＴＡＳＫ：整理慢煮 lane 清單")

        conn.close()

    def test_triage_tasks_accepts_task_marker_with_en_dash_separator(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "REMINDER–renew domain this week",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "REMINDER–renew domain this week")

        conn.close()

    def test_triage_tasks_accepts_task_marker_with_em_dash_separator(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "REMINDER—renew domain this week",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "REMINDER—renew domain this week")

        conn.close()

    def test_triage_tasks_accepts_task_marker_with_unicode_minus_separator(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "TASK−follow up on release checklist",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "TASK−follow up on release checklist")

        conn.close()

    def test_triage_tasks_accepts_task_marker_with_full_width_hyphen_separator(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "TASK－follow up on release checklist",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "TASK－follow up on release checklist")

        conn.close()

    def test_triage_tasks_accepts_task_marker_with_newline_separator(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "note",
                        "tool_name": "memory_store",
                        "summary": "TASK\nfollow up on release checklist",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertEqual(out["tasks"]["matches"][0]["summary"], "TASK\nfollow up on release checklist")

        conn.close()

    def test_triage_tasks_parses_importance_object(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "task",
                        "tool_name": "memory_store",
                        "summary": "TODO: send invoice to vendor",
                        "detail": {"importance": {"score": 0.9, "label": "must_remember"}},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)
        self.assertAlmostEqual(out["tasks"]["matches"][0]["importance"], 0.9, places=5)

        conn.close()

    def test_triage_cron_errors_reads_jobs_json(self):
        import tempfile

        # Fake cron jobs store
        jobs = {
            "jobs": [
                {
                    "id": "job1",
                    "name": "Job 1",
                    "enabled": True,
                    "state": {"lastStatus": "ok", "lastRunAtMs": 9999999999999},
                },
                {
                    "id": "job2",
                    "name": "Job 2",
                    "enabled": True,
                    "state": {"lastStatus": "error", "lastRunAtMs": 9999999999999, "lastDurationMs": 1234},
                },
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as tmp:
            json.dump(jobs, tmp)
            tmp_path = tmp.name

        conn = _connect(":memory:")
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "cron-errors",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": tmp_path,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)
        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["cron"]["found_new"], 1)
        self.assertEqual(out["cron"]["matches"][0]["id"], "job2")

        conn.close()

    def test_store_persists_dual_language_fields(self):
        conn = _connect(":memory:")

        args = type(
            "Args",
            (),
            {
                "text": "나는 커피를 좋아해",
                "text_en": "I like coffee",
                "lang": "ko",
                "category": "preference",
                "importance": 0.8,
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "workspace": None,
                "json": True,
            },
        )()

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value=None):
            with redirect_stdout(buf):
                cmd_store(conn, args)

        out = json.loads(buf.getvalue())
        self.assertTrue(out["ok"])
        row = conn.execute("SELECT summary, summary_en, lang FROM observations WHERE id = ?", (out["id"],)).fetchone()
        self.assertEqual(row["summary"], "나는 커피를 좋아해")
        self.assertEqual(row["summary_en"], "I like coffee")
        self.assertEqual(row["lang"], "ko")
        conn.close()

    def test_store_emits_canonical_importance_object(self):
        conn = _connect(":memory:")

        args = type(
            "Args",
            (),
            {
                "text": "Prefer tabs over spaces",
                "text_en": None,
                "lang": "en",
                "category": "preference",
                "importance": 0.9,
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "workspace": None,
                "json": True,
            },
        )()

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value=None):
            with redirect_stdout(buf):
                cmd_store(conn, args)

        out = json.loads(buf.getvalue())
        row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (out["id"],)).fetchone()
        detail = json.loads(row["detail_json"])
        self.assertIsInstance(detail.get("importance"), dict)
        self.assertAlmostEqual(float(detail["importance"]["score"]), 0.9, places=5)
        self.assertEqual(detail["importance"]["label"], "must_remember")
        self.assertEqual(detail["importance"]["method"], "manual-via-cli")
        self.assertIn("graded_at", detail["importance"])

        conn.close()

    def test_store_persists_english_embedding_when_text_en_present(self):
        conn = _connect(":memory:")

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = type(
            "Args",
            (),
            {
                "text": "원문",
                "text_en": "english",
                "lang": "ko",
                "category": "fact",
                "importance": 0.7,
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "workspace": None,
                "json": True,
            },
        )()

        from unittest.mock import patch

        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(io.StringIO()):
                cmd_store(conn, args)

        orig = conn.execute("SELECT COUNT(*) FROM observation_embeddings").fetchone()[0]
        en = conn.execute("SELECT COUNT(*) FROM observation_embeddings_en").fetchone()[0]
        self.assertEqual(orig, 1)
        self.assertEqual(en, 1)
        conn.close()

    def test_hybrid_supports_query_en_route(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps({"ts": "2026-02-04T13:00:00Z", "kind": "fact", "summary": "사과", "summary_en": "apple", "tool_name": "memory_store", "detail": {}}),
                json.dumps({"ts": "2026-02-04T13:01:00Z", "kind": "fact", "summary": "바나나", "summary_en": "banana", "tool_name": "memory_store", "detail": {}}),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            ingest_args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, ingest_args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        # Original table: id=1 aligns with [1,0], id=2 aligns with [0,1]
        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "test-model", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "test-model", 2, pack_f32([0.0, 1.0]), l2_norm([0.0, 1.0]), "2026-02-05T00:00:00Z"),
        )
        # EN table intentionally reversed so we can detect table preference.
        conn.execute(
            "INSERT INTO observation_embeddings_en (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "test-model", 2, pack_f32([0.0, 1.0]), l2_norm([0.0, 1.0]), "2026-02-05T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO observation_embeddings_en (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "test-model", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                out = []
                for t in texts:
                    if t == "zzzz":
                        out.append([0.0, 0.0])
                    else:
                        out.append([1.0, 0.0])
                return out

        args = type(
            "Args",
            (),
            {
                "query": "zzzz",
                "query_en": "banana",
                "model": "test-model",
                "limit": 5,
                "k": 60,
                "base_url": "https://example.com/v1",
                "json": True,
            },
        )()

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(buf):
                cmd_hybrid(conn, args)

        out = json.loads(buf.getvalue())
        self.assertGreaterEqual(len(out), 1)
        self.assertEqual(out[0]["id"], 2)
        self.assertIn("vector_en", out[0]["match"])
        conn.close()

    def test_hybrid_rerank_reorders_results(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps({"ts": "2026-02-04T13:00:00Z", "kind": "fact", "summary": "first", "summary_en": "first", "tool_name": "memory_store", "detail": {}}),
                json.dumps({"ts": "2026-02-04T13:01:00Z", "kind": "fact", "summary": "second", "summary_en": "second", "tool_name": "memory_store", "detail": {}}),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            ingest_args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, ingest_args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "test-model", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "test-model", 2, pack_f32([0.0, 1.0]), l2_norm([0.0, 1.0]), "2026-02-05T00:00:00Z"),
        )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = type(
            "Args",
            (),
            {
                "query": "zzzz",
                "query_en": None,
                "model": "test-model",
                "limit": 5,
                "k": 60,
                "base_url": "https://example.com/v1",
                "rerank_provider": "jina",
                "rerank_model": "jina-reranker-v2-base-multilingual",
                "rerank_topn": 2,
                "rerank_api_key": "test-rerank-key",
                "rerank_base_url": None,
                "rerank_timeout_sec": 5,
                "json": True,
            },
        )()

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient), patch(
            "openclaw_mem.cli._call_rerank_provider", return_value=[(1, 0.9), (0, 0.1)]
        ):
            with redirect_stdout(buf):
                cmd_hybrid(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out[0]["id"], 2)
        self.assertEqual(out[0].get("rerank_provider"), "jina")
        self.assertEqual(out[0].get("rank_stage"), "rerank")
        conn.close()

    def test_hybrid_rerank_fail_open_keeps_rrf_order(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps({"ts": "2026-02-04T13:00:00Z", "kind": "fact", "summary": "first", "summary_en": "first", "tool_name": "memory_store", "detail": {}}),
                json.dumps({"ts": "2026-02-04T13:01:00Z", "kind": "fact", "summary": "second", "summary_en": "second", "tool_name": "memory_store", "detail": {}}),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            ingest_args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, ingest_args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "test-model", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "test-model", 2, pack_f32([0.0, 1.0]), l2_norm([0.0, 1.0]), "2026-02-05T00:00:00Z"),
        )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = type(
            "Args",
            (),
            {
                "query": "zzzz",
                "query_en": None,
                "model": "test-model",
                "limit": 5,
                "k": 60,
                "base_url": "https://example.com/v1",
                "rerank_provider": "jina",
                "rerank_model": "jina-reranker-v2-base-multilingual",
                "rerank_topn": 2,
                "rerank_api_key": "test-rerank-key",
                "rerank_base_url": None,
                "rerank_timeout_sec": 5,
                "json": True,
            },
        )()

        from unittest.mock import patch
        from contextlib import redirect_stderr

        buf = io.StringIO()
        err = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient), patch(
            "openclaw_mem.cli._call_rerank_provider", side_effect=RuntimeError("boom")
        ):
            with redirect_stdout(buf), redirect_stderr(err):
                cmd_hybrid(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out[0]["id"], 1)
        self.assertEqual(out[0].get("rerank_provider"), "jina")
        self.assertNotIn("rank_stage", out[0])
        self.assertIn("rerank failed", err.getvalue())
        conn.close()

    def test_pack_rejects_blank_query(self):
        conn = _connect(":memory:")

        args = build_parser().parse_args(["pack", "--query", "   ", "--json"])

        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with redirect_stdout(buf):
                args.func(conn, args)

        self.assertEqual(cm.exception.code, 2)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["error"], "empty query")
        conn.close()

    def test_pack_accepts_query_en_for_hybrid_retrieval(self):
        conn = _connect(":memory:")

        captured = {}

        def fake_retrieve(conn_, args_, candidate_limit_override=None):
            captured["query_en"] = args_.query_en
            captured["candidate_limit_override"] = candidate_limit_override
            return {
                "ordered_ids": [1],
                "fts_ids": {1},
                "vec_ids": set(),
                "vec_en_ids": set(),
                "rrf_scores": {1: 0.77},
                "obs_map": {
                    1: {
                        "summary": "plain summary",
                        "summary_en": "plain summary",
                        "kind": "fact",
                        "lang": "en",
                    }
                },
                "candidate_limit": 12,
            }

        args = build_parser().parse_args(["pack", "--query", "테스트", "--query-en", "test", "--json", "--limit", "4"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._hybrid_retrieve", side_effect=fake_retrieve):
            with redirect_stdout(buf):
                args.func(conn, args)

        self.assertEqual(captured.get("query_en"), "test")
        self.assertEqual(captured.get("candidate_limit_override"), 12)

        out = json.loads(buf.getvalue())
        self.assertEqual(len(out["items"]), 1)
        self.assertEqual(out["items"][0]["recordRef"], "obs:1")
        conn.close()

    def test_pack_no_json_outputs_plain_bundle_text(self):
        conn = _connect(":memory:")

        pack_state = {
            "ordered_ids": [1],
            "fts_ids": {1},
            "vec_ids": set(),
            "vec_en_ids": set(),
            "rrf_scores": {1: 0.77},
            "obs_map": {
                1: {
                    "summary": "plain summary",
                    "summary_en": "plain summary",
                    "kind": "fact",
                    "lang": "en",
                }
            },
            "candidate_limit": 12,
        }

        args = build_parser().parse_args(["pack", "--query", "something", "--no-json", "--limit", "3"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._hybrid_retrieve", return_value=pack_state):
            with redirect_stdout(buf):
                args.func(conn, args)

        self.assertEqual(buf.getvalue(), "- [obs:1] plain summary\n")
        conn.close()

    def test_pack_budget_tokens_clamped_to_minimum_one(self):
        conn = _connect(":memory:")

        pack_state = {
            "ordered_ids": [1],
            "fts_ids": {1},
            "vec_ids": set(),
            "vec_en_ids": set(),
            "rrf_scores": {1: 0.77},
            "obs_map": {
                1: {
                    "summary": "a",
                    "summary_en": "a",
                    "kind": "fact",
                    "lang": "en",
                }
            },
            "candidate_limit": 12,
        }

        args = build_parser().parse_args(["pack", "--query", "x", "--no-json", "--limit", "3", "--budget-tokens", "-5"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._hybrid_retrieve", return_value=pack_state):
            with redirect_stdout(buf):
                args.func(conn, args)

        self.assertEqual(buf.getvalue(), "- [obs:1] a\n")
        conn.close()

    def test_pack_trace_empty_candidates_returns_zero_counts(self):
        conn = _connect(":memory:")

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = build_parser().parse_args(["pack", "--query", "nothing-matches", "--trace", "--json", "--limit", "5", "--budget-tokens", "1200"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(buf):
                args.func(conn, args)

        out = json.loads(buf.getvalue())
        self.assertIn("bundle_text", out)
        self.assertEqual(out["bundle_text"], "")
        self.assertEqual(out["items"], [])
        self.assertEqual(out["citations"], [])

        trace = out["trace"]
        self.assertEqual(trace["query"]["text"], "nothing-matches")
        self.assertEqual(trace["output"]["includedCount"], 0)
        self.assertEqual(trace["output"]["excludedCount"], 0)
        self.assertEqual(trace["output"]["citationsCount"], 0)
        self.assertEqual(trace["output"]["refreshedRecordRefs"], [])
        self.assertEqual(trace["candidates"], [])

        conn.close()

    def test_pack_trace_json_shape_and_redaction(self):
        conn = _connect(":memory:")

        sample = json.dumps(
            {
                "ts": "2026-02-04T13:00:00Z",
                "kind": "fact",
                "summary": "test pack summary",
                "summary_en": "test pack summary en",
                "tool_name": "memory_store",
                "detail": {},
            }
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            ingest_args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, ingest_args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "text-embedding-3-small", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = build_parser().parse_args(["pack", "--query", "test", "--trace", "--json"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(buf):
                args.func(conn, args)

        out = json.loads(buf.getvalue())
        self.assertIn("bundle_text", out)
        self.assertIn("items", out)
        self.assertIn("citations", out)
        self.assertIn("trace", out)
        self.assertEqual(out["trace"]["kind"], "openclaw-mem.pack.trace.v1")
        self.assertIn("ts", out["trace"])
        self.assertIn("T", out["trace"]["ts"])
        self.assertTrue(out["trace"]["ts"].endswith("+00:00"))
        self.assertEqual(out["trace"]["version"]["schema"], "v1")
        self.assertRegex(out["trace"]["version"]["openclaw_mem"], r"^\d+\.\d+\.\d+")
        self.assertEqual(out["trace"]["query"]["text"], "test")
        self.assertIn("output", out["trace"])
        self.assertEqual(out["trace"]["budgets"]["maxL2Items"], 0)
        self.assertEqual(out["trace"]["budgets"]["niceCap"], 100)
        self.assertEqual(out["trace"]["output"]["includedCount"], 1)
        self.assertEqual(out["trace"]["output"]["excludedCount"], 0)
        self.assertEqual(out["trace"]["output"]["citationsCount"], 1)
        self.assertEqual(out["trace"]["output"]["refreshedRecordRefs"], ["obs:1"])
        self.assertIn("coverage", out["trace"]["output"])
        self.assertEqual(out["trace"]["output"]["coverage"]["rationaleMissingCount"], 0)
        self.assertEqual(out["trace"]["output"]["coverage"]["citationMissingCount"], 0)

        candidate = out["trace"]["candidates"][0]
        self.assertIn("caps", candidate["decision"])
        self.assertFalse(candidate["decision"]["caps"]["niceCapHit"])
        self.assertFalse(candidate["decision"]["caps"]["l2CapHit"])
        self.assertEqual(candidate["decision"]["rationale"], candidate["decision"]["reason"])
        self.assertIsNone(candidate["citations"]["url"])

        self.assertEqual(
            set(out["trace"].keys()),
            {
                "kind",
                "ts",
                "version",
                "query",
                "budgets",
                "lanes",
                "candidates",
                "output",
                "timing",
            },
        )

        for lane in out["trace"]["lanes"]:
            self.assertIn("retrievers", lane)
            self.assertIsInstance(lane["retrievers"], list)

        self.assertIn("reason", candidate["decision"])
        self.assertIsInstance(candidate["decision"]["reason"], list)
        self.assertGreater(len(candidate["decision"]["reason"]), 0)

        trace_dump = json.dumps(out["trace"], ensure_ascii=False)
        # Trace should be redaction-safe (no raw memory text or local absolute paths).
        self.assertNotIn("test pack summary", trace_dump)
        self.assertNotIn("/root/", trace_dump)
        self.assertNotIn("/home/", trace_dump)
        self.assertNotIn("/Users/", trace_dump)
        self.assertNotRegex(trace_dump, r"[A-Za-z]:\\\\")
        conn.close()

    def test_pack_trace_stable_schema_contract(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "fact",
                        "summary": "stability sample one",
                        "summary_en": "stability sample one",
                        "tool_name": "memory_store",
                        "detail": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "fact",
                        "summary": "stability sample two",
                        "summary_en": "stability sample two",
                        "tool_name": "memory_store",
                        "detail": {},
                    }
                ),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            ingest_args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, ingest_args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        for obs_id in (1, 2):
            conn.execute(
                "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (obs_id, "text-embedding-3-small", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
            )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = build_parser().parse_args(["pack", "--query", "stability", "--query-en", "stability", "--trace", "--json", "--limit", "2", "--budget-tokens", "150"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(buf):
                args.func(conn, args)

        out = json.loads(buf.getvalue())
        trace = out["trace"]

        self.assertEqual(trace["kind"], "openclaw-mem.pack.trace.v1")
        self.assertIn("ts", trace)
        self.assertIn("version", trace)
        self.assertEqual(trace["version"]["schema"], "v1")
        self.assertIn("query", trace)
        self.assertIn("text", trace["query"])
        self.assertIn("scope", trace["query"])
        self.assertIn("intent", trace["query"])
        self.assertIn("budgets", trace)
        self.assertEqual(trace["budgets"]["maxItems"], 2)
        self.assertEqual(trace["budgets"]["maxL2Items"], 0)
        self.assertEqual(trace["budgets"]["niceCap"], 100)

        lane_names = [lane["name"] for lane in trace["lanes"]]
        self.assertEqual(lane_names, ["hot", "warm", "cold"])
        warm = next(lane for lane in trace["lanes"] if lane["name"] == "warm")
        self.assertEqual(warm["source"], "sqlite-observations")
        self.assertTrue(warm["searched"])
        self.assertEqual([r["kind"] for r in warm["retrievers"]], ["fts5", "vector", "rrf"])

        self.assertIn("candidates", trace)
        self.assertGreater(len(trace["candidates"]), 0)
        candidate = trace["candidates"][0]
        for key in ["id", "layer", "importance", "trust", "scores", "decision", "citations"]:
            self.assertIn(key, candidate)
        self.assertIn("niceCapHit", candidate["decision"]["caps"])
        self.assertIn("l2CapHit", candidate["decision"]["caps"])
        self.assertIn("rationale", candidate["decision"])
        self.assertEqual(candidate["decision"]["rationale"], candidate["decision"]["reason"])
        self.assertIn("output", trace)
        self.assertIn("includedCount", trace["output"])
        self.assertIn("refreshedRecordRefs", trace["output"])
        self.assertIn("coverage", trace["output"])
        self.assertIn("allIncludedHaveRationale", trace["output"]["coverage"])
        self.assertIn("allIncludedHaveCitations", trace["output"]["coverage"])
        self.assertIsInstance(trace["output"]["refreshedRecordRefs"], list)

        conn.close()

    def test_pack_trace_candidate_uses_importance_and_trust_from_detail_json(self):
        conn = _connect(":memory:")

        sample = json.dumps(
            {
                "ts": "2026-02-04T13:00:00Z",
                "kind": "fact",
                "summary": "trust aware memory item",
                "summary_en": "trust aware memory item",
                "tool_name": "memory_store",
                "detail": {
                    "importance": {"label": "must_remember", "score": 0.91},
                    "trust_tier": "quarantine",
                },
            }
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            ingest_args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, ingest_args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "text-embedding-3-small", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = build_parser().parse_args(["pack", "--query", "trust", "--trace", "--json"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(buf):
                args.func(conn, args)

        out = json.loads(buf.getvalue())
        candidate = out["trace"]["candidates"][0]
        self.assertEqual(candidate["importance"], "must_remember")
        self.assertEqual(candidate["trust"], "quarantined")
        conn.close()

    def test_pack_trace_candidate_uses_unknown_when_detail_labels_are_invalid(self):
        conn = _connect(":memory:")

        sample = json.dumps(
            {
                "ts": "2026-02-04T13:00:00Z",
                "kind": "fact",
                "summary": "unknown label sample",
                "summary_en": "unknown label sample",
                "tool_name": "memory_store",
                "detail": {
                    "importance": {"label": "someday_maybe"},
                    "provenance": {"trust": "semi_trusted"},
                },
            }
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            ingest_args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, ingest_args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "text-embedding-3-small", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = build_parser().parse_args(["pack", "--query", "unknown", "--trace", "--json"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(buf):
                args.func(conn, args)

        out = json.loads(buf.getvalue())
        candidate = out["trace"]["candidates"][0]
        self.assertEqual(candidate["importance"], "unknown")
        self.assertEqual(candidate["trust"], "unknown")
        conn.close()

    def test_pack_trace_output_counts_with_exclusions(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "fact",
                        "summary": "test pack alpha",
                        "summary_en": "test pack alpha",
                        "tool_name": "memory_store",
                        "detail": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "fact",
                        "summary": "test pack beta",
                        "summary_en": "test pack beta",
                        "tool_name": "memory_store",
                        "detail": {},
                    }
                ),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            ingest_args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, ingest_args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "text-embedding-3-small", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "text-embedding-3-small", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = build_parser().parse_args(["pack", "--query", "test", "--trace", "--json", "--limit", "1"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(buf):
                args.func(conn, args)

        out = json.loads(buf.getvalue())
        trace = out["trace"]
        self.assertEqual(trace["output"]["includedCount"], 1)
        self.assertGreaterEqual(trace["output"]["excludedCount"], 1)
        self.assertEqual(trace["output"]["includedCount"] + trace["output"]["excludedCount"], len(trace["candidates"]))
        self.assertEqual(trace["output"]["refreshedRecordRefs"], [out["items"][0]["recordRef"]])
        conn.close()

    def test_pack_trace_reason_keys_are_known(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "fact",
                        "summary": "trace reason sample one",
                        "summary_en": "trace reason sample one",
                        "tool_name": "memory_store",
                        "detail": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "fact",
                        "summary": "",
                        "summary_en": "",
                        "tool_name": "memory_store",
                        "detail": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:02:00Z",
                        "kind": "fact",
                        "summary": "trace reason sample three",
                        "summary_en": "trace reason sample three",
                        "tool_name": "memory_store",
                        "detail": {},
                    }
                ),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            ingest_args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, ingest_args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        for obs_id in (1, 2, 3):
            conn.execute(
                "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (obs_id, "text-embedding-3-small", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
            )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = build_parser().parse_args(["pack", "--query", "trace", "--trace", "--json", "--limit", "1"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(buf):
                args.func(conn, args)

        out = json.loads(buf.getvalue())
        allowed = {
            "missing_row",
            "missing_summary",
            "max_items_reached",
            "budget_tokens_exceeded",
            "within_item_limit",
            "within_budget",
            "matched_fts",
            "matched_vector",
        }
        observed_reasons = set()
        for candidate in out["trace"]["candidates"]:
            reasons = candidate["decision"].get("reason", [])
            reason_set = set(reasons)
            self.assertTrue(reasons, f"candidate {candidate.get('id')} has no decision reasons")
            self.assertLessEqual(reason_set - allowed, set())
            observed_reasons |= reason_set

        self.assertIn("missing_summary", observed_reasons)
        self.assertIn("within_budget", observed_reasons)
        self.assertIn("within_item_limit", observed_reasons)
        conn.close()

    def test_pack_respects_budget_tokens(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "fact",
                        "summary": "ping",
                        "summary_en": "ping",
                        "tool_name": "memory_store",
                        "detail": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "fact",
                        "summary": "ping this is a much longer summary that should never fit into the tiny budget",
                        "summary_en": "ping this is a much longer summary that should never fit into the tiny budget",
                        "tool_name": "memory_store",
                        "detail": {},
                    }
                ),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            ingest_args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, ingest_args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "text-embedding-3-small", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "text-embedding-3-small", 2, pack_f32([0.0, 1.0]), l2_norm([0.0, 1.0]), "2026-02-05T00:00:00Z"),
        )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = build_parser().parse_args(["pack", "--query", "ping", "--trace", "--json", "--limit", "2", "--budget-tokens", "1"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(buf):
                args.func(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["items"][0]["id"], 1)
        self.assertLessEqual(len(out["items"]), 1)
        self.assertEqual(out["trace"]["output"]["includedCount"], 1)
        self.assertEqual(out["trace"]["output"]["excludedCount"], 1)
        self.assertEqual(out["trace"]["candidates"][1]["id"], "obs:2")
        self.assertEqual(out["trace"]["candidates"][1]["decision"]["reason"], ["budget_tokens_exceeded"])
        self.assertIn("within_item_limit", out["trace"]["candidates"][0]["decision"]["reason"])
        self.assertIn("within_budget", out["trace"]["candidates"][0]["decision"]["reason"])
        conn.close()

    def test_pack_trace_records_max_items_reached_reason(self):
        conn = _connect(":memory:")

        pack_state = {
            "ordered_ids": [1, 2],
            "fts_ids": {1, 2},
            "vec_ids": set(),
            "vec_en_ids": set(),
            "rrf_scores": {1: 0.9, 2: 0.8},
            "obs_map": {
                1: {
                    "summary": "first short summary",
                    "summary_en": "first short summary",
                    "kind": "fact",
                    "lang": "en",
                },
                2: {
                    "summary": "second short summary",
                    "summary_en": "second short summary",
                    "kind": "fact",
                    "lang": "en",
                },
            },
            "candidate_limit": 12,
        }

        args = build_parser().parse_args(["pack", "--query", "short", "--trace", "--json", "--limit", "1"])

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._hybrid_retrieve", return_value=pack_state):
            with redirect_stdout(buf):
                args.func(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(len(out["items"]), 1)
        self.assertEqual(out["items"][0]["recordRef"], "obs:1")

        candidates = out["trace"]["candidates"]
        self.assertEqual(len(candidates), 2)
        self.assertTrue(candidates[0]["decision"]["included"])
        self.assertIn("within_item_limit", candidates[0]["decision"]["reason"])
        self.assertFalse(candidates[1]["decision"]["included"])
        self.assertEqual(candidates[1]["decision"]["reason"], ["max_items_reached"])
        self.assertEqual(out["trace"]["output"]["includedCount"], 1)
        self.assertEqual(out["trace"]["output"]["excludedCount"], 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
