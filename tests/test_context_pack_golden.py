from __future__ import annotations

import io
import json
import unittest
from contextlib import ExitStack
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openclaw_mem.cli import _connect, build_parser


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield i, json.loads(line)
            except Exception as e:
                raise AssertionError(f"Invalid JSON on line {i}: {e}")


def _normalize_pack_state(raw: dict) -> dict:
    state = dict(raw or {})
    state["fts_ids"] = set(state.get("fts_ids") or [])
    state["vec_ids"] = set(state.get("vec_ids") or [])
    state["vec_en_ids"] = set(state.get("vec_en_ids") or [])
    state["rrf_scores"] = {int(k): float(v) for k, v in dict(state.get("rrf_scores") or {}).items()}
    state["obs_map"] = {int(k): dict(v or {}) for k, v in dict(state.get("obs_map") or {}).items()}
    state["ordered_ids"] = [int(x) for x in list(state.get("ordered_ids") or [])]
    state["candidate_limit"] = int(state.get("candidate_limit") or 12)
    return state


class TestContextPackGoldenFixtures(unittest.TestCase):
    def test_jsonl_fixture_is_well_formed(self):
        path = Path(__file__).resolve().parent / "data" / "CONTEXT_PACK_GOLDEN_SCENARIOS.v0.jsonl"
        self.assertTrue(path.exists(), f"Missing fixture file: {path}")

        ids = []
        for line_no, row in _iter_jsonl(path):
            self.assertEqual(row.get("version"), "v0", f"Line {line_no}: version must be v0")
            sid = str(row.get("id") or "")
            self.assertTrue(sid, f"Line {line_no}: missing id")
            ids.append(sid)
            self.assertTrue(isinstance(row.get("args"), list) and row.get("args"), f"{sid}: missing args")
            self.assertTrue(isinstance(row.get("expect"), dict) and row.get("expect"), f"{sid}: missing expect")
            self.assertTrue(str(row.get("why") or ""), f"{sid}: missing why")

        self.assertEqual(len(ids), len(set(ids)), "Scenario ids must be unique")
        self.assertTrue(ids, "Fixture must contain at least 1 scenario")

    def test_yaml_and_jsonl_fixture_stay_in_sync_by_id(self):
        jsonl = Path(__file__).resolve().parent / "data" / "CONTEXT_PACK_GOLDEN_SCENARIOS.v0.jsonl"
        yaml = Path(__file__).resolve().parents[1] / "docs" / "fixtures" / "context-pack-golden-scenarios.v0.yaml"

        self.assertTrue(jsonl.exists(), f"Missing JSONL fixture: {jsonl}")
        self.assertTrue(yaml.exists(), f"Missing YAML fixture: {yaml}")

        yaml_text = yaml.read_text(encoding="utf-8")
        missing = []
        for _, row in _iter_jsonl(jsonl):
            sid = str(row.get("id") or "")
            if sid and f"id: {sid}" not in yaml_text:
                missing.append(sid)

        if missing:
            self.fail(f"YAML fixture is missing scenario ids present in JSONL: {missing}")


class TestContextPackGoldenHarness(unittest.TestCase):
    def _run_scenario(self, row: dict) -> dict:
        conn = _connect(":memory:")
        args = build_parser().parse_args(list(row["args"]))
        pack_state = _normalize_pack_state(dict(row.get("pack_state") or {}))
        synthesis_pref_raw = dict(row.get("synthesis_pref") or {})
        synthesis_pref = (
            [int(x) for x in list(synthesis_pref_raw.get("selected_ids") or pack_state.get("ordered_ids") or [])],
            dict(synthesis_pref_raw.get("meta") or {"preferredCardRefs": [], "coveredRawRefs": [], "coverageMap": {}}),
        )

        patchers = [
            patch("openclaw_mem.cli._hybrid_retrieve", return_value=pack_state),
            patch("openclaw_mem.cli._hybrid_prefer_synthesis_cards", return_value=synthesis_pref),
        ]

        if "probe" in row:
            patchers.append(patch("openclaw_mem.cli._pack_graph_probe_observations", return_value=row["probe"]))
        if "stage1" in row:
            patchers.append(patch("openclaw_mem.cli._pack_graph_stage1_keywords", return_value=row["stage1"]))
        if "graph_index_payload" in row:
            patchers.append(patch("openclaw_mem.cli._graph_index_payload", return_value=row["graph_index_payload"]))
        if "graph_pack_payload" in row:
            patchers.append(patch("openclaw_mem.cli._graph_pack_payload", return_value=row["graph_pack_payload"]))

        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                with ExitStack() as stack:
                    for patcher in patchers:
                        stack.enter_context(patcher)
                    args.func(conn, args)
            return json.loads(buf.getvalue())
        finally:
            conn.close()

    def test_golden_scenarios(self):
        path = Path(__file__).resolve().parent / "data" / "CONTEXT_PACK_GOLDEN_SCENARIOS.v0.jsonl"
        for _, row in _iter_jsonl(path):
            with self.subTest(row=row.get("id")):
                out = self._run_scenario(row)
                expect = dict(row.get("expect") or {})

                selected_record_refs = expect.get("selected_record_refs")
                if selected_record_refs is not None:
                    self.assertEqual([item.get("recordRef") for item in out.get("items", [])], list(selected_record_refs))

                graph_expect = dict(expect.get("graph") or {})
                if graph_expect:
                    graph = dict(out.get("graph") or {})
                    trace_graph = dict((((out.get("trace") or {}).get("extensions") or {}).get("graph") or {}))
                    if "triggered" in graph_expect:
                        self.assertEqual(graph.get("triggered"), graph_expect["triggered"])
                    if "trigger_reason" in graph_expect:
                        self.assertEqual(graph.get("trigger_reason"), graph_expect["trigger_reason"])
                    if "stage1_categories" in graph_expect:
                        self.assertEqual(trace_graph.get("stage1_categories"), graph_expect["stage1_categories"])
                    if "probe" in graph_expect:
                        for key, value in dict(graph_expect.get("probe") or {}).items():
                            self.assertEqual(dict(trace_graph.get("probe") or {}).get(key), value)

                policy_expect = dict(expect.get("policy") or {})
                if policy_expect:
                    policy = dict((((out.get("trace") or {}).get("extensions") or {}).get("policy") or {}))
                    for key, value in policy_expect.items():
                        self.assertEqual(policy.get(key), value)


if __name__ == "__main__":
    unittest.main()
