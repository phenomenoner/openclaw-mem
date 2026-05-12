from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str) -> dict:
    proc = subprocess.run([sys.executable, "-m", "openclaw_mem", *args], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return json.loads(proc.stdout)


def test_mutation_cli_plan_stage_apply_rollback(tmp_path: Path):
    mutations = tmp_path / "mutations.json"
    mutations.write_text(json.dumps({"mutations": [{"action": "write_file", "path": "demo.txt", "content": "hello", "risk_class": "L1"}]}), encoding="utf-8")
    plan = tmp_path / "plan.json"
    payload = run_cli("mutation", "plan", "--mutations-file", str(mutations), "--out", str(plan), "--json")
    assert payload["schema_version"] == "openclaw-mem.mutation.plan.v0"
    sandbox = tmp_path / "sandbox"
    validation = run_cli("mutation", "validate", "--plan-file", str(plan), "--allowed-root", str(sandbox), "--allow-apply", "--json")
    assert validation["ok"] is True
    stage = run_cli("mutation", "stage", "--plan-file", str(plan), "--allowed-root", str(sandbox), "--stage-root", str(tmp_path / "staged"), "--json")
    assert stage["ok"] is True
    assert stage["writes_performed"] is True
    applied = run_cli("mutation", "apply", "--plan-file", str(plan), "--allowed-root", str(sandbox), "--receipt-root", str(tmp_path / "runs"), "--json")
    assert applied["ok"] is True
    assert (sandbox / "demo.txt").read_text(encoding="utf-8") == "hello"
    receipt = Path(applied["receipt_path"])
    rollback = run_cli("mutation", "rollback", "--receipt", str(receipt), "--out-root", str(tmp_path / "rollback"), "--json")
    assert rollback["ok"] is True
    assert not (sandbox / "demo.txt").exists()


def test_mutation_cli_blocks_l4(tmp_path: Path):
    mutations = tmp_path / "mutations.json"
    mutations.write_text(json.dumps({"mutations": [{"action": "write_file", "path": "demo.txt", "content": "x", "risk_class": "L4"}]}), encoding="utf-8")
    validation = run_cli("mutation", "validate", "--mutations-file", str(mutations), "--allowed-root", str(tmp_path / "sandbox"), "--allow-apply", "--json")
    assert validation["ok"] is False
    assert "manual approval" in " ".join(validation["errors"])
