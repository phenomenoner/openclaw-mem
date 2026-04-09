from __future__ import annotations

import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, _insert_observation, build_parser
from openclaw_mem.graph.refresh import refresh_topology_file


def _run(conn, argv: list[str]) -> dict:
    args = build_parser().parse_args(argv)
    args.db = getattr(args, "db", None) or getattr(args, "db_global", None) or ":memory:"
    args.json = bool(getattr(args, "json", False) or getattr(args, "json_global", False))
    buf = io.StringIO()
    with redirect_stdout(buf):
        args.func(conn, args)
    raw = buf.getvalue().strip()
    if not raw:
        raise RuntimeError("empty CLI output")
    return json.loads(raw)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="openclaw-mem-route-auto-smoke-") as td:
        root = Path(td)
        db_path = root / "mem.sqlite"
        topology_path = root / "topology.json"
        topology_path.write_text(
            json.dumps(
                {
                    "nodes": [
                        {"id": "project.openclaw-mem", "type": "project", "tags": ["repo"], "metadata": {}},
                        {"id": "doc.route-auto", "type": "doc", "tags": ["sop"], "metadata": {}},
                    ],
                    "edges": [
                        {
                            "src": "project.openclaw-mem",
                            "dst": "doc.route-auto",
                            "type": "documents",
                            "provenance": "docs/route-auto.md",
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
        project_doc = playbook_repo / "projects" / "openclaw-mem" / "TECH_NOTES" / "route-auto-synthesis.md"
        project_doc.parent.mkdir(parents=True)
        project_doc.write_text("# route auto synthesis\n", encoding="utf-8")

        conn = _connect(str(db_path))
        try:
            _insert_observation(
                conn,
                {
                    "ts": "2026-04-10T01:00:00Z",
                    "kind": "note",
                    "tool_name": "graph.capture-md",
                    "summary": "[MD] route-auto-synthesis.md#Route auto synthesis propagation",
                    "detail": {
                        "scope": "openclaw-mem",
                        "source_path": str(project_doc),
                        "rel_path": "projects/openclaw-mem/TECH_NOTES/route-auto-synthesis.md",
                        "heading": "Route auto synthesis propagation",
                    },
                },
            )
            _insert_observation(
                conn,
                {
                    "ts": "2026-04-10T01:05:00Z",
                    "kind": "note",
                    "tool_name": "graph.capture-md",
                    "summary": "[MD] route-auto-synthesis.md#Route auto hook receipts",
                    "detail": {
                        "scope": "openclaw-mem",
                        "source_path": str(project_doc),
                        "rel_path": "projects/openclaw-mem/TECH_NOTES/route-auto-synthesis.md",
                        "heading": "Route auto hook receipts",
                    },
                },
            )
            conn.commit()

            compile_args = build_parser().parse_args(
                [
                    "--db",
                    str(db_path),
                    "graph",
                    "--json",
                    "synth",
                    "compile",
                    "--record-ref",
                    "obs:1",
                    "--record-ref",
                    "obs:2",
                    "--scope",
                    "openclaw-mem",
                    "--title",
                    "Route auto synthesis card",
                    "--summary",
                    "Route auto synthesis card",
                    "--why-it-matters",
                    "Prefer a fresh synthesis card before replaying covered raw refs.",
                ]
            )
            with redirect_stdout(io.StringIO()):
                compile_args.func(conn, compile_args)

            routed = _run(
                conn,
                [
                    "--db",
                    str(db_path),
                    "--json",
                    "route",
                    "auto",
                    "route auto synthesis",
                    "--scope",
                    "openclaw-mem",
                    "--support-window-hours",
                    "100000",
                ],
            )
        finally:
            conn.close()

    selection = routed.get("selection") or {}
    graph_consumption = selection.get("graph_consumption") or {}
    if selection.get("selected_lane") != "graph_match":
        raise SystemExit(f"expected graph_match, got {selection.get('selected_lane')!r}")
    if graph_consumption.get("preferredCardRefs") != ["obs:3"]:
        raise SystemExit(f"unexpected preferredCardRefs: {graph_consumption.get('preferredCardRefs')!r}")
    if graph_consumption.get("coveredRawRefs") != ["obs:1", "obs:2"]:
        raise SystemExit(f"unexpected coveredRawRefs: {graph_consumption.get('coveredRawRefs')!r}")

    print(json.dumps({
        "ok": True,
        "selectedLane": selection.get("selected_lane"),
        "preferredCardRefs": graph_consumption.get("preferredCardRefs"),
        "coveredRawRefs": graph_consumption.get("coveredRawRefs"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
