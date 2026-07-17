from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from openclaw_mem.cli import (
    _connect,
    _insert_observation,
    _run_handler_with_deprecation,
    build_parser,
)
from openclaw_mem.core.curation import rollback_optimize_assist


TARGETS = ("memory", "episodes", "skills", "facts")
VERBS = ("scan", "review", "apply", "verify", "rollback")


def _run(conn, argv: list[str]) -> dict:
    args = build_parser().parse_args([*argv, "--json"])
    args.json = True
    output = io.StringIO()
    with redirect_stdout(output):
        args.func(conn, args)
    return json.loads(output.getvalue())


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("target", TARGETS)
def test_every_verb_target_combination_emits_stable_wrapper(tmp_path: Path, verb: str, target: str) -> None:
    conn = _connect(":memory:")
    empty_recommendation = tmp_path / "recommendation.json"
    empty_recommendation.write_text(
        json.dumps({"kind": "openclaw-mem.optimize.evolution-review.v0", "items": []}),
        encoding="utf-8",
    )
    empty_governor = tmp_path / "governor.json"
    empty_governor.write_text(
        json.dumps({"kind": "openclaw-mem.optimize.governor-review.v0", "items": []}),
        encoding="utf-8",
    )

    argv = ["curate", verb, "--target", target]
    if verb == "scan" and target == "skills":
        argv.extend(["--skill-root", str(Path("skills"))])
    if verb == "scan" and target == "facts":
        argv.extend(["--source-root", str(tmp_path)])
    if verb == "review" and target == "memory":
        argv.extend(["--from-file", str(empty_recommendation)])
    if verb == "apply" and target == "memory":
        argv.extend(["--from-file", str(empty_governor), "--run-dir", str(tmp_path / "assist")])
    if verb == "verify" and target != "skills":
        argv.extend(["--run-dir", str(tmp_path / "assist")])
    if verb == "rollback" and target == "memory":
        argv.extend(["--receipt", str(tmp_path / "missing-rollback.json")])

    out = _run(conn, argv)
    assert out["kind"] == f"openclaw-mem.curate.{verb}.v1"
    assert out["verb"] == verb
    assert out["target"] == target
    assert isinstance(out["ok"], bool)
    assert isinstance(out["writes_performed"], bool)
    assert "inner" in out
    conn.close()


def test_deprecation_receipt_is_additive_and_non_json_stdout_is_unchanged() -> None:
    conn = _connect(":memory:")

    def emit_json(_conn, _args) -> None:
        print(json.dumps({"kind": "fixture", "nested": {"value": 7}}, ensure_ascii=False))

    json_args = build_parser().parse_args(["optimize", "review", "--json"])
    json_args.json = True
    json_args.func = emit_json
    output = io.StringIO()
    with redirect_stdout(output):
        _run_handler_with_deprecation(conn, json_args)
    payload = json.loads(output.getvalue())
    assert payload == {
        "kind": "fixture",
        "nested": {"value": 7},
        "deprecated": {
            "use": "curate scan --target memory",
            "since": "2.0.0",
            "removal": None,
        },
    }

    def emit_text(_conn, _args) -> None:
        print("original output")

    text_args = build_parser().parse_args(["optimize", "review"])
    text_args.json = False
    text_args.func = emit_text
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        _run_handler_with_deprecation(conn, text_args)
    assert stdout.getvalue() == "original output\n"
    assert stderr.getvalue().count("deprecated:") == 1
    assert "curate scan --target memory" in stderr.getvalue()
    conn.close()


def test_old_review_alias_matches_curate_inner_except_deprecation_and_timestamps() -> None:
    conn = _connect(":memory:")
    old_args = build_parser().parse_args(["optimize", "review", "--json"])
    old_args.json = True
    output = io.StringIO()
    with redirect_stdout(output):
        _run_handler_with_deprecation(conn, old_args)
    old = json.loads(output.getvalue())
    deprecated = old.pop("deprecated")

    new = _run(conn, ["curate", "scan", "--target", "memory"])
    inner = new["inner"][0]["receipt"]
    assert deprecated["use"] == "curate scan --target memory"
    assert old["kind"] == inner["kind"]
    assert old["version"] == inner["version"]
    assert old["source"] == inner["source"]
    assert old["signals"] == inner["signals"]
    assert old["policy"] == inner["policy"]
    assert old["recommendations"] == inner["recommendations"]
    conn.close()


def test_scan_review_apply_verify_rollback_soft_archive_e2e(tmp_path: Path) -> None:
    conn = _connect(":memory:")
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    original_detail = {"scope": "team/alpha", "importance": {"score": 0.2, "label": "ignore"}}
    observation_id = _insert_observation(
        conn,
        {
            "ts": stale_ts,
            "kind": "note",
            "tool_name": "memory_store",
            "summary": "Old low-priority candidate",
            "detail": original_detail,
        },
    )
    original_detail = json.loads(
        conn.execute(
            "SELECT detail_json FROM observations WHERE id = ?", (observation_id,)
        ).fetchone()["detail_json"]
    )

    scan = _run(conn, ["curate", "scan", "--target", "memory"])
    assert scan["ok"] is True
    assert scan["writes_performed"] is False

    recommendation = {
        "kind": "openclaw-mem.optimize.evolution-review.v0",
        "items": [
            {
                "candidate_id": f"soft-archive-candidate-{observation_id}",
                "action": "set_soft_archive_candidate",
                "risk_level": "low",
                "auto_apply_eligible": False,
                "target": {"observationId": observation_id, "recordRef": f"obs:{observation_id}"},
                "patch": {
                    "lifecycle": {
                        "soft_archive_candidate": True,
                        "set_archived_at": True,
                        "archive_reason_code": "stale_low_importance",
                    }
                },
                "evidence_refs": [f"obs:{observation_id}"],
            }
        ],
    }
    recommendation_path = tmp_path / "recommendation.json"
    recommendation_path.write_text(json.dumps(recommendation), encoding="utf-8")
    reviewed = _run(
        conn,
        [
            "curate",
            "review",
            "--target",
            "memory",
            "--from-file",
            str(recommendation_path),
            "--approve-soft-archive",
        ],
    )
    assert reviewed["ok"] is True
    assert reviewed["inner"]["counts"]["approvedForApply"] == 1
    governor_path = tmp_path / "governor.json"
    governor_path.write_text(json.dumps(reviewed["inner"]), encoding="utf-8")

    run_dir = tmp_path / "assist"
    applied = _run(
        conn,
        [
            "curate",
            "apply",
            "--target",
            "memory",
            "--from-file",
            str(governor_path),
            "--run-dir",
            str(run_dir),
        ],
    )
    assert applied["ok"] is True
    assert applied["writes_performed"] is True
    rollback_ref = applied["inner"]["artifacts"]["rollback_ref"]
    changed = json.loads(conn.execute("SELECT detail_json FROM observations WHERE id = ?", (observation_id,)).fetchone()["detail_json"])
    assert changed["lifecycle"]["soft_archive_candidate"] is True

    verified = _run(conn, ["curate", "verify", "--target", "memory", "--run-dir", str(run_dir)])
    assert verified["kind"] == "openclaw-mem.curate.verify.v1"
    assert verified["inner"]["kind"] == "openclaw-mem.optimize.verifier-bundle.v0"

    rolled_back = _run(
        conn,
        ["curate", "rollback", "--target", "memory", "--receipt", rollback_ref, "--actor", "test"],
    )
    assert rolled_back["ok"] is True
    assert rolled_back["inner"]["restored_observation_ids"] == [observation_id]
    restored = json.loads(conn.execute("SELECT detail_json FROM observations WHERE id = ?", (observation_id,)).fetchone()["detail_json"])
    assert restored == original_detail
    conn.close()


def test_memory_rollback_is_atomic_when_any_target_drifted(tmp_path: Path) -> None:
    conn = _connect(":memory:")
    ids = []
    before_values = []
    after_values = []
    for index in range(2):
        before = {"scope": "atomic", "value": index}
        after = {"scope": "atomic", "value": index + 10}
        observation_id = _insert_observation(
            conn,
            {"kind": "note", "summary": f"atomic {index}", "detail": after},
            taxonomy_enabled=False,
        )
        ids.append(observation_id)
        before_values.append(before)
        after_values.append(after)
    receipt = {
        "kind": "openclaw-mem.optimize.assist.rollback.v1",
        "run_id": "atomic-fixture",
        "mutations": [
            {
                "observation_id": observation_id,
                "before_detail_json": before,
                "before_sha256": _sha(before),
                "after_detail_json": after,
                "after_sha256": _sha(after),
            }
            for observation_id, before, after in zip(ids, before_values, after_values)
        ],
    }
    receipt_path = tmp_path / "rollback.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    conn.execute(
        "UPDATE observations SET detail_json = ? WHERE id = ?",
        (_canonical({"scope": "atomic", "value": 999}), ids[1]),
    )
    conn.commit()

    out = rollback_optimize_assist(conn, receipt_path)
    assert out["ok"] is False
    assert out["writes_performed"] is False
    first = json.loads(conn.execute("SELECT detail_json FROM observations WHERE id = ?", (ids[0],)).fetchone()["detail_json"])
    second = json.loads(conn.execute("SELECT detail_json FROM observations WHERE id = ?", (ids[1],)).fetchone()["detail_json"])
    assert first == after_values[0]
    assert second["value"] == 999
    conn.close()


def test_importance_drift_scan_governor_apply_records_before_after(tmp_path: Path) -> None:
    conn = _connect(":memory:")
    observation_id = _insert_observation(
        conn,
        {
            "kind": "fact",
            "summary": "Importance drift calibration fixture",
            "detail": {"importance": {"score": 0.92, "label": "ignore"}},
        },
    )
    before = json.loads(
        conn.execute(
            "SELECT detail_json FROM observations WHERE id = ?", (observation_id,)
        ).fetchone()["detail_json"]
    )

    scan = _run(conn, ["curate", "scan", "--target", "memory", "--top", "20"])
    evolution = scan["inner"][1]["receipt"]
    candidates = [
        item
        for item in evolution["items"]
        if item.get("action") == "adjust_importance_score"
        and item.get("target", {}).get("observationId") == observation_id
    ]
    assert candidates
    assert evolution["importance_drift_policy"]["metrics"]["score_label_mismatch_count"] >= 1

    recommendation_path = tmp_path / "importance-drift.json"
    recommendation_path.write_text(json.dumps(evolution), encoding="utf-8")
    reviewed = _run(
        conn,
        [
            "curate",
            "review",
            "--target",
            "memory",
            "--from-file",
            str(recommendation_path),
            "--approve-importance",
        ],
    )
    approved = [
        item
        for item in reviewed["inner"]["items"]
        if item.get("target", {}).get("observationId") == observation_id
        and item.get("decision") == "approved_for_apply"
    ]
    assert approved
    governor_path = tmp_path / "importance-governor.json"
    governor_path.write_text(json.dumps({**reviewed["inner"], "items": approved}), encoding="utf-8")

    applied = _run(
        conn,
        [
            "curate",
            "apply",
            "--target",
            "memory",
            "--from-file",
            str(governor_path),
            "--run-dir",
            str(tmp_path / "assist"),
        ],
    )
    rollback = json.loads(
        Path(applied["inner"]["artifacts"]["rollback_ref"]).read_text(encoding="utf-8")
    )
    mutation = rollback["mutations"][0]
    after = json.loads(
        conn.execute(
            "SELECT detail_json FROM observations WHERE id = ?", (observation_id,)
        ).fetchone()["detail_json"]
    )

    assert applied["inner"]["applied_action_counts"]["adjust_importance_score"] == 1
    assert mutation["before_detail_json"] == before
    assert mutation["after_detail_json"] == after
    assert after["importance"]["label"] == "must_remember"
    conn.close()
