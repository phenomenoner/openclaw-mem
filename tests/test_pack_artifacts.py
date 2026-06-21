import hashlib
import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openclaw_mem.pack_artifacts import (
    PACK_RECEIPT_SCHEMA,
    artifact_hash,
    collect_observe_report,
    default_store_path,
    pack_candidate,
    parse_marker,
    put_artifact,
    retrieve_artifact,
    validate_canary_schema,
)


ACTIVE_MARKER_RE = re.compile(r"<<ocm:artifact:v1:sha256:[0-9A-Fa-f]{64}>>>")


def _metadata(session_key: str = "session-a", **overrides):
    meta = {
        "agentId": "agent-a",
        "sessionKey": session_key,
        "sourceKind": "tool-output",
        "sourceId": "cmd-1",
        "trustLevel": "trusted",
        "scope": "project:alpha",
        "contentType": "text/plain",
        "producer": "unittest",
        "commandOrTool": "fixture",
        "receiptId": f"receipt-{session_key}",
        "ttlPolicy": "session",
    }
    meta.update(overrides)
    return meta


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


class TestPackArtifacts(unittest.TestCase):
    def test_marker_parser_accepts_full_hash_only_and_hash_is_raw_bytes_deterministic(self):
        raw = b"alpha\r\nbeta\x00gamma"
        expected_hex = hashlib.sha256(raw).hexdigest()
        self.assertEqual(artifact_hash(raw), f"sha256:{expected_hex}")

        marker = f"<<ocm:artifact:v1:sha256:{expected_hex.upper()}>>>"
        self.assertEqual(parse_marker(marker), f"sha256:{expected_hex}")

        bad_markers = [
            "",
            f"prefix <<ocm:artifact:v1:sha256:{expected_hex}>>>",
            f"<<ocm:artifact:v1:sha256:{expected_hex}>>> suffix",
            f"<<ocm:artifact:v2:sha256:{expected_hex}>>>",
            f"<<ocm:artifact:v1:sha1:{expected_hex}>>>",
            f"<<ocm:artifact:v1:sha256:{expected_hex[:63]}>>>",
            "<<ocm:artifact:v1:sha256:" + ("g" * 64) + ">>>",
            "ocm:artifact:v1:sha256:" + expected_hex,
            f"<<ocm:artifact:v1:sha256:{expected_hex}>>",
        ]
        for marker_text in bad_markers:
            with self.subTest(marker=marker_text):
                with self.assertRaises(ValueError):
                    parse_marker(marker_text)

    def test_default_store_path_uses_separate_state_root_sqlite(self):
        state_root = Path("C:/operator/state")
        self.assertEqual(
            default_store_path(state_root),
            state_root / "memory" / "pack-artifacts" / "openclaw-mem-pack-artifacts.sqlite",
        )

    def test_store_round_trip_reuses_same_session_duplicate_and_allows_cross_session_record(self):
        with tempfile.TemporaryDirectory() as td:
            store_path = Path(td) / "state" / "artifacts.sqlite"
            raw = b"exact bytes\x00with newline\r\n"

            first = put_artifact(raw, _metadata("session-a"), store_path=store_path)
            second = put_artifact(raw, _metadata("session-a"), store_path=store_path)
            cross = put_artifact(raw, _metadata("session-b"), store_path=store_path)

            self.assertEqual(first["decision"], "stored")
            self.assertEqual(second["decision"], "stored")
            self.assertTrue(second["duplicate"])
            self.assertEqual(first["hash"], second["hash"])
            self.assertEqual(first["recordId"], second["recordId"])
            self.assertEqual(first["hash"], cross["hash"])
            self.assertNotEqual(first["recordId"], cross["recordId"])

            fetched = retrieve_artifact(
                first["marker"],
                _metadata("session-a", trustLevel="trusted", scope="project:alpha"),
                store_path=store_path,
            )
            self.assertEqual(fetched["decision"], "returned")
            self.assertEqual(fetched["rawBytes"], raw)
            self.assertEqual(fetched["receipt"]["scopeDecision"], "allowed")
            self.assertEqual(fetched["receipt"]["trustDecision"], "allowed")
            self.assertNotIn("rawBytes", fetched["receipt"])

    def test_admission_denial_blocks_pack_without_storing_raw_payload_in_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            store_path = Path(td) / "artifacts.sqlite"
            raw = b"tiny payload"
            result = pack_candidate(
                raw,
                _metadata(contentType="text/plain"),
                store_path=store_path,
                admission={"minPackBytes": 1024, "minPackTokensEstimate": 1024},
            )

            self.assertEqual(result["decision"], "blocked")
            self.assertEqual(result["reason"], "admission-denied")
            self.assertEqual(result["content"], raw)
            self.assertNotIn("marker", result)

            receipt_json = json.dumps(result["receipt"], sort_keys=True)
            self.assertIn('"decision": "blocked"', receipt_json)
            self.assertIn('"reason": "admission-denied"', receipt_json)
            self.assertNotIn("tiny payload", receipt_json)
            self.assertNotIn("rawBytes", receipt_json)
            self.assertEqual(result["receipt"]["metadata"]["sessionKey"], "session-a")

            missing = retrieve_artifact(
                artifact_hash(raw),
                _metadata(trustLevel="trusted", scope="project:alpha"),
                store_path=store_path,
            )
            self.assertEqual(missing["decision"], "missing")

    def test_unsafe_strategy_output_is_blocked_without_storing_raw_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            store_path = Path(td) / "artifacts.sqlite"
            raw = b"{not valid json"

            result = pack_candidate(
                raw,
                _metadata(contentType="application/json"),
                store_path=store_path,
                admission={"minPackBytes": 1, "minPackTokensEstimate": 1},
            )

            self.assertEqual(result["decision"], "blocked")
            self.assertEqual(result["reason"], "unsafe-type")
            self.assertNotIn("marker", result)

            missing = retrieve_artifact(
                artifact_hash(raw),
                _metadata(trustLevel="trusted", scope="project:alpha"),
                store_path=store_path,
            )
            self.assertEqual(missing["decision"], "missing")

    def test_non_shrinking_strategy_output_is_blocked_without_storing_raw_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            store_path = Path(td) / "artifacts.sqlite"
            raw = b"ERROR x\n"

            result = pack_candidate(
                raw,
                _metadata(sourceKind="log", contentType="text/plain"),
                store_path=store_path,
                admission={"minPackBytes": 1, "minPackTokensEstimate": 1},
            )

            self.assertEqual(result["decision"], "blocked")
            self.assertEqual(result["reason"], "not-smaller")
            self.assertNotIn("marker", result)
            self.assertEqual(result["content"], raw)

            missing = retrieve_artifact(
                artifact_hash(raw),
                _metadata(trustLevel="trusted", scope="project:alpha"),
                store_path=store_path,
            )
            self.assertEqual(missing["decision"], "missing")

    def test_retrieval_denials_for_missing_expired_scope_and_trust_emit_receipts(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            store_path = Path(td) / "artifacts.sqlite"

            missing = retrieve_artifact(
                "sha256:" + ("1" * 64),
                _metadata(trustLevel="trusted", scope="project:alpha"),
                store_path=store_path,
                now=now,
            )
            self.assertEqual(missing["decision"], "missing")
            self.assertEqual(missing["receipt"]["scopeDecision"], "not-evaluated")
            self.assertEqual(missing["receipt"]["trustDecision"], "not-evaluated")

            expiring = put_artifact(
                b"expires",
                _metadata(ttlPolicy={"kind": "duration", "seconds": 1}),
                store_path=store_path,
                now=now,
            )
            expired = retrieve_artifact(
                expiring["marker"],
                _metadata(trustLevel="trusted", scope="project:alpha"),
                store_path=store_path,
                now=now + timedelta(seconds=2),
            )
            self.assertEqual(expired["decision"], "expired")

            scoped = put_artifact(
                b"scope sensitive",
                _metadata(scope="project:alpha"),
                store_path=store_path,
                now=now,
            )
            scope_denied = retrieve_artifact(
                scoped["marker"],
                _metadata(scope="project:beta", trustLevel="trusted"),
                store_path=store_path,
                now=now,
            )
            self.assertEqual(scope_denied["decision"], "scope-denied")
            self.assertEqual(scope_denied["receipt"]["scopeDecision"], "denied")
            self.assertEqual(scope_denied["receipt"]["trustDecision"], "not-evaluated")

            trusted = put_artifact(
                b"trust sensitive",
                _metadata(trustLevel="high"),
                store_path=store_path,
                now=now,
            )
            trust_denied = retrieve_artifact(
                trusted["marker"],
                _metadata(scope="project:alpha", trustLevel="low"),
                store_path=store_path,
                now=now,
            )
            self.assertEqual(trust_denied["decision"], "trust-denied")
            self.assertEqual(trust_denied["receipt"]["scopeDecision"], "allowed")
            self.assertEqual(trust_denied["receipt"]["trustDecision"], "denied")

            for denied in [missing, expired, scope_denied, trust_denied]:
                receipt_json = json.dumps(denied["receipt"], sort_keys=True)
                self.assertNotIn("rawBytes", receipt_json)
                self.assertNotIn("expires", receipt_json)
                self.assertIn(denied["decision"], receipt_json)

    def test_json_log_and_search_strategies_shorten_fixtures_and_marker_retrieves_original_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            store_path = Path(td) / "artifacts.sqlite"
            admission = {"minPackBytes": 64, "minPackTokensEstimate": 10}

            rows = [
                {"id": i, "name": f"row-{i}", "status": "ok", "value": "x" * 80}
                for i in range(80)
            ]
            rows[10]["status"] = "failed"
            rows[10]["message"] = "exception while indexing"
            json_raw = json.dumps(rows, sort_keys=True).encode("utf-8")

            log_lines = [f"INFO line {i} {'x' * 70}" for i in range(160)]
            log_lines[30] = "WARN retry failed for shard 7"
            log_lines[120] = "ERROR panic while flushing buffer"
            log_raw = ("\n".join(log_lines) + "\n").encode("utf-8")

            search_doc = {
                "query": "panic buffer",
                "matches": [
                    {
                        "path": f"src/module_{i % 9}.rs",
                        "line": i + 1,
                        "snippet": f"match {i} panic buffer {'x' * 80}",
                    }
                    for i in range(90)
                ],
            }
            search_raw = json.dumps(search_doc, sort_keys=True).encode("utf-8")

            candidates = [
                (json_raw, _metadata(contentType="application/json"), "json-shape-v1", "rowCount: 80"),
                (log_raw, _metadata(sourceKind="log", contentType="text/plain"), "log-anomaly-v1", "omittedLines:"),
                (
                    search_raw,
                    _metadata(sourceKind="search-results", contentType="application/json"),
                    "search-results-v1",
                    "query: panic buffer",
                ),
            ]

            for raw, meta, strategy, expected_text in candidates:
                with self.subTest(strategy=strategy):
                    packed = pack_candidate(raw, meta, store_path=store_path, admission=admission)
                    self.assertEqual(packed["decision"], "packed")
                    self.assertEqual(packed["strategy"], strategy)
                    self.assertLess(len(packed["content"]), len(raw))
                    packed_text = packed["content"].decode("utf-8")
                    self.assertIn(expected_text, packed_text)
                    self.assertIn(f"artifactMarker: {packed['marker']}", packed_text)
                    self.assertEqual(ACTIVE_MARKER_RE.findall(packed_text), [packed["marker"]])

                    retrieved = retrieve_artifact(
                        packed["marker"],
                        _metadata(trustLevel="trusted", scope="project:alpha"),
                        store_path=store_path,
                    )
                    self.assertEqual(retrieved["decision"], "returned")
                    self.assertEqual(retrieved["rawBytes"], raw)

    def test_marker_like_body_text_is_escaped_so_only_dedicated_marker_is_active(self):
        with tempfile.TemporaryDirectory() as td:
            store_path = Path(td) / "artifacts.sqlite"
            fake_marker = "<<ocm:artifact:v1:sha256:" + ("a" * 64) + ">>>"
            lines = [f"INFO normal line {i} {'x' * 40}" for i in range(80)]
            lines[5] = f"ERROR copied user text containing {fake_marker}"
            raw = ("\n".join(lines) + "\n").encode("utf-8")

            packed = pack_candidate(
                raw,
                _metadata(sourceKind="log", contentType="text/plain"),
                store_path=store_path,
                admission={"minPackBytes": 64, "minPackTokensEstimate": 10},
            )

            packed_text = packed["content"].decode("utf-8")
            self.assertEqual(packed["decision"], "packed")
            self.assertNotIn(fake_marker, packed_text)
            self.assertEqual(ACTIVE_MARKER_RE.findall(packed_text), [packed["marker"]])

    def test_disabled_strategy_passes_through_and_observe_report_counts_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store_path = root / "artifacts.sqlite"
            receipts_dir = root / "receipts"
            strategy_config = {"strategies": {"json-shape-v1": {"enabled": False}}}

            rows = [{"id": i, "value": "x" * 80} for i in range(80)]
            raw = json.dumps(rows, sort_keys=True).encode("utf-8")
            disabled = pack_candidate(
                raw,
                _metadata(contentType="application/json"),
                store_path=store_path,
                admission={"minPackBytes": 64, "minPackTokensEstimate": 10},
                strategy_config=strategy_config,
            )
            self.assertEqual(disabled["decision"], "pass-through")
            self.assertEqual(disabled["reason"], "strategy-disabled")
            self.assertEqual(disabled["content"], raw)

            log_raw = ("\n".join([f"INFO line {i} {'x' * 80}" for i in range(100)]) + "\nERROR failed\n").encode(
                "utf-8"
            )
            packed = pack_candidate(
                log_raw,
                _metadata(sourceKind="log", contentType="text/plain"),
                store_path=store_path,
                admission={"minPackBytes": 64, "minPackTokensEstimate": 10},
            )
            returned = retrieve_artifact(
                packed["marker"],
                _metadata(trustLevel="trusted", scope="project:alpha"),
                store_path=store_path,
            )
            missing = retrieve_artifact(
                "sha256:" + ("2" * 64),
                _metadata(trustLevel="trusted", scope="project:alpha"),
                store_path=store_path,
            )

            _write_jsonl(
                receipts_dir / "receipts.jsonl",
                [disabled["receipt"], packed["receipt"], returned["receipt"], missing["receipt"]],
            )
            report = collect_observe_report(receipts_dir, strategy_config=strategy_config)

            self.assertIn("json-shape-v1", report["disabledStrategies"]["configured"])
            self.assertEqual(report["disabledStrategies"]["observed"]["json-shape-v1"], 1)
            self.assertEqual(report["perStrategy"]["json-shape-v1"]["passThrough"], 1)
            self.assertGreater(report["perStrategy"]["log-anomaly-v1"]["estimatedTokensSaved"], 0)
            self.assertEqual(report["retrieval"]["returned"], 1)
            self.assertEqual(report["retrieval"]["missing"], 1)
            self.assertTrue(report["canary"]["allGreen"])

    def test_marker_like_text_in_json_keys_and_search_paths_is_escaped(self):
        with tempfile.TemporaryDirectory() as td:
            store_path = Path(td) / "artifacts.sqlite"
            fake_marker = "<<ocm:artifact:v1:sha256:" + ("c" * 64) + ">>>"
            json_raw = json.dumps(
                [
                    {
                        "id": 1,
                        fake_marker: "field-name-marker",
                        "status": "failed",
                        "message": "contains " + fake_marker,
                        "value": "x" * 120,
                    }
                ]
                * 20,
                sort_keys=True,
            ).encode("utf-8")
            search_raw = json.dumps(
                {
                    "query": "marker path",
                    "matches": [
                        {
                            "path": f"src/{fake_marker}/file.py",
                            "line": i,
                            "snippet": "snippet " + fake_marker,
                        }
                        for i in range(20)
                    ],
                },
                sort_keys=True,
            ).encode("utf-8")

            for raw, meta in [
                (json_raw, _metadata(contentType="application/json")),
                (search_raw, _metadata(sourceKind="search-results", contentType="application/json")),
            ]:
                packed = pack_candidate(
                    raw,
                    meta,
                    store_path=store_path,
                    admission={"minPackBytes": 64, "minPackTokensEstimate": 10},
                )
                packed_text = packed["content"].decode("utf-8")
                self.assertEqual(packed["decision"], "packed")
                self.assertNotIn(fake_marker, packed_text)
                self.assertEqual(ACTIVE_MARKER_RE.findall(packed_text), [packed["marker"]])

    def test_observe_report_marks_canary_failures_not_green(self):
        with tempfile.TemporaryDirectory() as td:
            receipts_dir = Path(td) / "receipts"
            _write_jsonl(
                receipts_dir / "canary-receipts.jsonl",
                [
                    {
                        "schema": "openclaw-mem.pack-canary-receipt.v1",
                        "canaryId": "bad-canary",
                        "passed": False,
                        "strategy": "json-shape-v1",
                    }
                ],
            )

            report = collect_observe_report(receipts_dir)

            self.assertFalse(report["canary"]["allGreen"])
            self.assertEqual(report["canary"]["failed"], 1)

    def test_observe_report_ignores_malformed_numeric_receipt_fields(self):
        with tempfile.TemporaryDirectory() as td:
            receipts_dir = Path(td) / "receipts"
            _write_jsonl(
                receipts_dir / "bad-numbers.jsonl",
                [
                    {
                        "schema": PACK_RECEIPT_SCHEMA,
                        "decision": "packed",
                        "strategy": "log-anomaly-v1",
                        "tokensBefore": "not-a-number",
                        "tokensAfter": "still-not-a-number",
                        "latencyMs": "also-bad",
                    }
                ],
            )

            report = collect_observe_report(receipts_dir)

            self.assertEqual(report["perStrategy"]["log-anomaly-v1"]["packed"], 1)
            self.assertEqual(report["perStrategy"]["log-anomaly-v1"]["estimatedTokensSaved"], 0)
            self.assertEqual(report["latency"], {"0-10ms": 1})

    def test_canary_schema_accepts_valid_fixture_and_rejects_malformed_fixture(self):
        digest = "b" * 64
        valid = {
            "schema": "openclaw-mem.pack-canary.v1",
            "canaryId": "canary-1",
            "strategy": "json-shape-v1",
            "artifactHash": f"sha256:{digest}",
            "marker": f"<<ocm:artifact:v1:sha256:{digest}>>>",
            "expectedRetrievalDecision": "returned",
            "createdAt": "2026-01-01T00:00:00+00:00",
        }
        self.assertEqual(validate_canary_schema(valid), {"valid": True, "errors": []})

        malformed = {
            "schema": "openclaw-mem.pack-canary.v1",
            "canaryId": "canary-2",
            "artifactHash": "sha256:" + ("b" * 63),
            "marker": "<<ocm:artifact:v1:sha256:" + ("b" * 63) + ">>>",
        }
        result = validate_canary_schema(malformed)
        self.assertFalse(result["valid"])
        self.assertIn("strategy", " ".join(result["errors"]))
        self.assertIn("marker", " ".join(result["errors"]))


if __name__ == "__main__":
    unittest.main()
