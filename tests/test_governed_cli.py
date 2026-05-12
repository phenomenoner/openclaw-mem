from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str) -> dict:
    proc = subprocess.run([sys.executable, "-m", "openclaw_mem", *args], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return json.loads(proc.stdout)


def test_governed_apply_review_cli(tmp_path: Path):
    mutations = tmp_path / "mutations.json"
    mutations.write_text(json.dumps({"mutations": [{"action": "write_file", "path": "x.txt", "content": "x", "risk_class": "L2"}]}), encoding="utf-8")
    plan = tmp_path / "plan.json"
    run_cli("mutation", "plan", "--mutations-file", str(mutations), "--out", str(plan), "--json")
    blocked = run_cli("governed", "apply-review", "--plan-file", str(plan), "--allowed-root", str(tmp_path / "sandbox"), "--json")
    assert blocked["ok"] is False
    assert "l2_requires_config_gate" in blocked["reasons"]
    allowed = run_cli("governed", "apply-review", "--plan-file", str(plan), "--allowed-root", str(tmp_path / "sandbox"), "--l2-enabled", "--json")
    assert allowed["ok"] is True
    assert allowed["decision"] == "advisory_allow_l2_local_apply"


def test_governed_release_check_cli(tmp_path: Path):
    root = tmp_path
    (root / "openclaw_mem").mkdir()
    (root / "docs").mkdir()
    (root / "pyproject.toml").write_text('version = "9.9.9"\n', encoding="utf-8")
    (root / "openclaw_mem" / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    (root / "uv.lock").write_text('[[package]]\nname = "openclaw-context-pack"\nversion = "9.9.9"\n', encoding="utf-8")
    (root / "CHANGELOG.md").write_text('## [9.9.9] - 2026-05-12\n', encoding="utf-8")
    (root / "docs" / "2026-05-12_self-improvement-slice-7-receipt.md").write_text("receipt\n", encoding="utf-8")
    (root / "docs" / "self-improvement-slice-7.md").write_text("public safe\n", encoding="utf-8")
    payload = run_cli("governed", "release-check", "--repo-root", str(root), "--expected-version", "9.9.9", "--json")
    assert payload["ok"] is True
    assert payload["writes_performed"] is False
