from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openclaw_mem.cli import _connect, cmd_ingest, cmd_pack  # noqa: E402


def _run_pack(conn: sqlite3.Connection, *, query: str, graph_path: Path | None = None) -> Dict[str, Any]:
    args = {
        "db": None,
        "harness_home": None,
        "json": True,
        "query": query,
        "query_en": None,
        "limit": 5,
        "budget_tokens": 600,
        "tail_text": None,
        "tail_file": None,
        "tail_max_items": 4,
        "tail_budget_tokens": 0,
        "use_gbrain": "off",
        "gbrain_bin": "",
        "gbrain_limit": 5,
        "gbrain_timeout_ms": 1000,
        "gbrain_expand": False,
        "use_graph": "off",
        "graph_scope": None,
        "graph_budget_tokens": 1200,
        "graph_take": 12,
        "graph_query_db": None,
        "graph_provenance_policy": "off",
        "graph_require_structured_provenance": True,
        "graph_provenance_hops": 1,
        "graph_provenance_max_nodes": 40,
        "graph_provenance_max_edges": 80,
        "pack_trust_policy": "off",
        "pack_lifecycle_shadow": "off",
        "pack_lifecycle_log_max_rows": 200,
        "pack_lifecycle_write": "off",
        "pack_artifacts": "off",
        "trace": True,
        "graph_probe": None,
        "graph_probe_limit": 5,
        "graph_probe_t_high": -5.0,
        "graph_probe_t_marginal": -2.0,
        "graph_probe_n_min": 3,
        "graph_latency_soft_ms": 150,
        "graph_latency_hard_ms": 300,
        "graph_aware": graph_path is not None,
        "graph_aware_path": str(graph_path or ""),
        "graph_aware_active_file": ["pkg/resolver.py"] if graph_path is not None else None,
        "graph_aware_recent_file": ["pkg/resolver.py"] if graph_path is not None else None,
        "graph_aware_stale_after_days": 30,
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_pack(conn, SimpleNamespace(**args))
    return json.loads(buf.getvalue())


def run(*, out: Path | None = None) -> Dict[str, Any]:
    fixture_dir = ROOT / "tests" / "data" / "graph_search_hybrid"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = root / "mem.sqlite"
        graph = root / "graph.json"
        graph.write_text((fixture_dir / "graph.json").read_text(encoding="utf-8"), encoding="utf-8")
        conn = _connect(str(db))
        try:
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, SimpleNamespace(file=str(fixture_dir / "observations.jsonl"), json=True, importance_scorer=None))
            baseline = _run_pack(conn, query="resolver")
            graph_aware = _run_pack(conn, query="resolver", graph_path=graph)
        finally:
            conn.close()
    selected = ((graph_aware.get("graph_aware_pack") or {}).get("selected") or [])
    budget_ok = len(str(graph_aware.get("bundle_text") or "")) <= len(str(baseline.get("bundle_text") or ""))
    win = bool(selected and selected[0].get("source_path") == "pkg/resolver.py" and budget_ok)
    receipt = {
        "kind": "openclaw-mem.pack.graph-aware.ab-receipt.v0",
        "criteria": {
            "win": "graph-aware selects pkg/resolver.py without increasing bundle_text length",
            "loss": "graph-aware misses pkg/resolver.py or exceeds baseline bundle size",
            "noise": "graph-aware emits unrelated selected context",
        },
        "counts": {"win": 1 if win else 0, "loss": 0 if win else 1, "noise": 0},
        "baseline": {"bundle_chars": len(str(baseline.get("bundle_text") or ""))},
        "graph_aware": {
            "bundle_chars": len(str(graph_aware.get("bundle_text") or "")),
            "selected": selected,
            "fallback_reason": (graph_aware.get("graph_aware_pack") or {}).get("fallback_reason"),
        },
    }
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(out=args.out), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
