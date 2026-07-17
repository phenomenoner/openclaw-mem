import json
import subprocess
import sys
from pathlib import Path

from openclaw_mem.symbolic_canvas import build_symbolic_canvas


def test_build_symbolic_canvas_is_deterministic_and_traceable(tmp_path: Path):
    evidence = tmp_path / "refs" / "fetch.md"
    evidence.parent.mkdir()
    evidence.write_text("raw fetch output", encoding="utf-8")
    trace = {
        "task_id": "absorb-tdai",
        "nodes": [
            {"id": "fetch", "label": "Fetch README", "state": "done", "refs": ["refs/fetch.md"]},
            {"id": "analyze", "label": "Analyze value items", "state": "running", "result_ref": "refs/missing.md"},
        ],
        "edges": [["fetch", "analyze", "evidence"]],
    }

    first = build_symbolic_canvas(trace, base_dir=tmp_path)
    second = build_symbolic_canvas(trace, base_dir=tmp_path)

    assert first == second
    assert first["kind"] == "openclaw-mem.symbolic-canvas.v0"
    assert first["topology"] == "unchanged"
    assert "fetch[\"Fetch README" in first["mermaid"]
    assert "fetch -- \"evidence\" --> analyze" in first["mermaid"]
    assert first["nodes"][0]["refs"] == ["refs/fetch.md"]
    assert first["stats"] == {"nodes": 2, "edges": 1, "refs": 2, "missing_refs": 1}
    assert any(w["code"] == "missing_refs" and w["node_id"] == "analyze" for w in first["warnings"])


def test_build_symbolic_canvas_generates_stable_ids_without_source_ids():
    trace = {
        "steps": [
            {"label": "Run focused tests", "state": "done"},
            {"label": "Write receipt", "state": "pending"},
        ],
    }

    result = build_symbolic_canvas(trace)

    assert result["nodes"][0]["node_id"].startswith("n001_run_focused_tests_")
    assert result["nodes"][1]["node_id"].startswith("n002_write_receipt_")
    assert "class " in result["mermaid"]


def test_symbolic_canvas_cli_writes_receipts(tmp_path: Path):
    trace_path = tmp_path / "trace.json"
    out_path = tmp_path / "canvas.json"
    mmd_path = tmp_path / "canvas.mmd"
    trace_path.write_text(
        json.dumps(
            {
                "task_id": "cli-smoke",
                "nodes": [{"id": "n1", "label": "One", "state": "done"}],
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "openclaw_mem",
            "symbolic-canvas",
            "build",
            "--from-file",
            str(trace_path),
            "--out",
            str(out_path),
            "--mermaid-out",
            str(mmd_path),
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True, encoding="utf-8", errors="replace",
        capture_output=True,
        check=True,
    )

    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["written"]["json"] == str(out_path)
    assert payload["written"]["mermaid"] == str(mmd_path)
    assert json.loads(out_path.read_text(encoding="utf-8"))["task_id"] == "cli-smoke"
    assert "n1[\"One" in mmd_path.read_text(encoding="utf-8")


def test_symbolic_canvas_rejects_duplicate_source_ids():
    trace = {
        "nodes": [
            {"id": "same", "label": "First"},
            {"id": "same", "label": "Second"},
        ],
        "edges": [["same", "same"]],
    }

    try:
        build_symbolic_canvas(trace)
    except ValueError as exc:
        assert "duplicate node source id: same" in str(exc)
    else:
        raise AssertionError("expected duplicate source id to fail closed")


def test_symbolic_canvas_warns_on_unknown_edge_endpoint():
    result = build_symbolic_canvas({"nodes": [{"id": "known", "label": "Known"}], "edges": [["known", "missing"]]})

    assert any(w["code"] == "edge_unknown_node" for w in result["warnings"])
    assert "known --> missing" in result["mermaid"]


def test_symbolic_canvas_cli_rejects_malformed_trace(tmp_path: Path):
    trace_path = tmp_path / "bad.json"
    trace_path.write_text(json.dumps({"nodes": {"not": "a list"}}), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "openclaw_mem",
            "symbolic-canvas",
            "build",
            "--from-file",
            str(trace_path),
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True, encoding="utf-8", errors="replace",
        capture_output=True,
    )

    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert "nodes, steps, or events" in payload["error"]


def test_symbolic_canvas_cli_accepts_stdin():
    proc = subprocess.run(
        [sys.executable, "-m", "openclaw_mem", "symbolic-canvas", "build", "--json"],
        cwd=Path(__file__).resolve().parents[1],
        input=json.dumps({"nodes": [{"id": "stdin", "label": "From stdin", "state": "done"}]}),
        text=True, encoding="utf-8", errors="replace",
        capture_output=True,
        check=True,
    )

    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["nodes"][0]["node_id"] == "stdin"
