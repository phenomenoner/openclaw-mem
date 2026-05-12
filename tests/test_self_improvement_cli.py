from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str, cwd: Path | None = None) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "openclaw_mem", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return json.loads(proc.stdout)


def test_goal_pack_cli(tmp_path: Path):
    goal = tmp_path / "goal.json"
    goal.write_text(
        json.dumps(
            {
                "goal": {
                    "goal_id": "cli-goal",
                    "objective": "Survive compaction",
                    "status": "active",
                    "next_gate": "pack",
                    "continuation_owner": "operator",
                }
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "goal-pack.json"
    payload = run_cli("goal", "pack", "--file", str(goal), "--out", str(out), "--json")
    assert payload["context"]["writes_performed"] is False
    assert "active-line:cli-goal" in payload["context"]["context_pack_fragment"]["bundle_text"]
    assert out.exists()


def test_skill_capture_cli_writes_staged_artifact(tmp_path: Path):
    out = tmp_path / "proposal.json"
    payload = run_cli(
        "skill-capture",
        "propose",
        "--text",
        "Refresh uv.lock after version bumps.",
        "--target-skill",
        "ck-software-engineering-ops",
        "--rationale",
        "CI freshness",
        "--out",
        str(out),
        "--json",
    )
    assert payload["ok"] is True
    assert payload["writes_performed"] is True
    assert payload["write_scope"] == "staged_proposal_artifact"
    stored = json.loads(out.read_text(encoding="utf-8"))
    assert stored["schema_version"] == "openclaw-mem.skill-capture.proposal.v0"


def test_skill_curator_cli_no_write_payload_only(tmp_path: Path):
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo skill\n---\n\n" + "Body " * 80,
        encoding="utf-8",
    )
    out_root = tmp_path / "runs"
    payload = run_cli(
        "skill-curator",
        "review",
        "--skill-root",
        str(skill_root),
        "--out-root",
        str(out_root),
        "--no-write",
        "--json",
    )
    assert payload["mode"] == "review_only"
    assert payload["writes_performed"] == 0
    assert payload["artifacts"] == {}
    assert not out_root.exists()


def test_mem_system_status_cli(tmp_path: Path):
    payload = run_cli("mem-system", "status", "--workspace-root", ".", "--state-root", str(tmp_path), "--json")
    assert payload["ok"] is True
    assert payload["writes_performed"] is False
    assert payload["topology_changed"] is False
    assert "Store" in payload["planes"]
