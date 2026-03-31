import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openclaw_mem.cli import _connect, _insert_observation


def iso_days_ago(days: int) -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=days)
    ).isoformat().replace("+00:00", "Z")


def ts_days_ago(days: int) -> int:
    return int(
        (
            datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=days)
        ).timestamp()
        * 1000
    )


def main() -> None:
    outdir = Path("handoffs/receipts/2026-03-31_optimize-shadow")
    outdir.mkdir(parents=True, exist_ok=True)
    db = outdir / "optimize-shadow-smoke.sqlite"
    if db.exists():
        db.unlink()

    conn = _connect(str(db))

    _insert_observation(conn, {"ts": iso_days_ago(120), "kind": "note", "tool_name": "memory_store", "summary": "legacy rollout detail that is likely stale", "detail": {"importance": {"score": 0.55, "label": "nice_to_have"}}})
    _insert_observation(conn, {"ts": iso_days_ago(2), "kind": "task", "tool_name": "memory_store", "summary": "TODO finalize weekly benchmark checklist", "detail": {"importance": {"score": 0.6}}})
    _insert_observation(conn, {"ts": iso_days_ago(1), "kind": "task", "tool_name": "memory_store", "summary": "TODO finalize weekly benchmark checklist", "detail": {"importance": {"score": 0.61}}})
    _insert_observation(conn, {"ts": iso_days_ago(1), "kind": "tool", "tool_name": "exec", "summary": "x" * 320, "detail": {"payload": "y" * 6000}})
    _insert_observation(conn, {"ts": iso_days_ago(3), "kind": "note", "tool_name": "memory_store", "summary": "quasarflux nebula drift anomaly snapshot", "detail": {"importance": {"score": 0.4, "label": "ignore"}}})
    _insert_observation(conn, {"ts": iso_days_ago(0), "kind": "fact", "tool_name": "memory_store", "summary": "Remember Alpha memory", "detail": {"memory_backend": "openclaw-mem-engine", "memory_operation": "store", "memory_id": "11111111-1111-1111-1111-111111111111", "importance": {"score": 0.91}, "scope": "team/alpha", "category": "fact"}})
    _insert_observation(conn, {"ts": iso_days_ago(0), "kind": "note", "tool_name": "memory_store", "summary": "Remember Beta memory", "detail": {"memory_backend": "openclaw-mem-engine", "memory_operation": "store", "memory": {"lancedb_id": "22222222-2222-2222-2222-222222222222"}, "importance": {"score": 0.62}, "scope": "team/alpha", "category": "note"}})
    _insert_observation(conn, {"ts": iso_days_ago(0), "kind": "note", "tool_name": "memory_store", "summary": "No lancedb id yet", "detail": {"memory_backend": "openclaw-mem-engine", "memory_operation": "store", "scope": "team/alpha"}})
    _insert_observation(conn, {"ts": iso_days_ago(0), "kind": "note", "tool_name": "memory_store", "summary": "Legacy backend stored summary", "detail": {"memory_backend": "memory-lancedb", "memory_operation": "store", "scope": "team/alpha"}})
    _insert_observation(conn, {"ts": iso_days_ago(1), "kind": "tool", "tool_name": "memory_recall", "summary": "memory recall miss 1", "detail": {"scope": "alpha", "query": "Cache Invalidation Policy", "results": []}})
    _insert_observation(conn, {"ts": iso_days_ago(1), "kind": "tool", "tool_name": "memory_recall", "summary": "memory recall miss 2", "detail": {"scope": "alpha", "query": "Cache Invalidation Policy", "results": []}})

    for selected, citation, candidate in [(3, 3, 3), (2, 2, 3), (2, 2, 2)]:
        receipt = {
            "kind": "openclaw-mem.pack.lifecycle-shadow.v1",
            "ts": iso_days_ago(0),
            "selection": {
                "pack_selected_refs": ["obs:1", "obs:2"],
                "citation_record_refs": ["obs:1", "obs:2"],
                "trace_refreshed_record_refs": ["obs:1", "obs:2"],
                "selection_signature": "sha256:test",
            },
            "policies": {
                "trust_policy_mode": "exclude_quarantined_fail_open",
                "graph_provenance_policy_mode": "structured_only_fail_open",
            },
            "mutation": {
                "memory_mutation": "none",
                "auto_archive_applied": 0,
                "auto_mutation_applied": 0,
            },
        }
        conn.execute(
            """
            INSERT INTO pack_lifecycle_shadow_log (
                ts, query_hash, selection_signature, selected_count, citation_count, candidate_count, receipt_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (iso_days_ago(0), "sha256:q", "sha256:test", selected, citation, candidate, json.dumps(receipt, ensure_ascii=False, sort_keys=True)),
        )

    now = datetime.now(timezone.utc).replace(microsecond=0)
    events = [
        ("ev-1", ts_days_ago(3), "alpha", "s-1", "conversation.user", "Investigate latency spike in memory recall lane", {"kind": "msg"}, {"recordRef": "obs:1"}, 0),
        ("ev-2", ts_days_ago(2), "alpha", "s-1", "conversation.assistant", "Memory recall latency spike still affects the debug lane", {"kind": "msg"}, {"recordRef": "obs:2"}, 0),
        ("ev-3", ts_days_ago(1), "alpha", "s-1", "tool.result", "Recall lane latency metrics confirm spike in debug memory path", {"kind": "tool"}, {"recordRef": "obs:3"}, 0),
        ("ev-4", ts_days_ago(1), "alpha", "s-2", "conversation.user", "Need a rollback plan for memory recall latency", {"kind": "msg"}, {"recordRef": "obs:4"}, 0),
        ("ev-5", ts_days_ago(28), "alpha", "s-old", "tool.result", "ok temp note", None, None, 1),
    ]
    for event_id, ts_ms, scope, session_id, event_type, summary, payload, refs, redacted in events:
        conn.execute(
            """
            INSERT INTO episodic_events (
                event_id, ts_ms, scope, session_id, agent_id, type, summary,
                payload_json, refs_json, redacted, schema_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, ts_ms, scope, session_id, "tester", event_type, summary, json.dumps(payload, ensure_ascii=False) if payload is not None else None, json.dumps(refs, ensure_ascii=False) if refs is not None else None, redacted, "v0", now.isoformat()),
        )

    conn.commit()
    conn.close()

    state = {
        "stage": "A-live",
        "readyForStageB": True,
        "liveGreenStreak": 20,
        "lastHealthy": True,
        "lastRunAt": iso_days_ago(0),
    }
    (outdir / "sunrise_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    print(db)


if __name__ == "__main__":
    main()
