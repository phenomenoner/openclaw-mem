#!/usr/bin/env python3
"""Deterministic, offline performance smoke suite for openclaw-mem.

The corpus, queries, and fake embeddings are generated from a fixed seed. The
reported timings are observations, not pass/fail thresholds, so the suite is
safe to run across different developer machines without creating flaky gates.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import platform
import random
import sqlite3
import statistics
import sys
import tempfile
import time
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from openclaw_mem.cli import _connect, _insert_observation, _invoke_cli_json  # noqa: E402
from openclaw_mem.core.recall import recall as core_recall  # noqa: E402
from openclaw_mem.core.vector_index import (  # noqa: E402
    NumpyIndex,
    PurePythonIndex,
    SqliteVecIndex,
    rebuild_sqlite_vec_indexes,
)
from openclaw_mem.vector import l2_norm, pack_f32  # noqa: E402


KIND = "openclaw-mem.perf.report.v1"
MATRIX_KIND = "openclaw-mem.perf.matrix.v1"
THRESHOLD_KIND = "openclaw-mem.perf.thresholds.v1"
SEED = 20260716
MODEL = "perf-fake-v1"
VOCABULARY = (
    "agent memory graph retrieval policy receipt session observation context "
    "store pack search vector durable local evidence rollback migration"
).split()

SLO_METRICS = {
    "connect.stamped_p95_ms": ("metrics", "connect", "stamped_p95_ms"),
    "recall.lexical_p95_ms": ("metrics", "recall", "lexical_p95_ms"),
    "recall.hybrid_p95_ms": ("metrics", "recall", "hybrid_p95_ms"),
    "pack.e2e_p95_ms": ("metrics", "pack", "e2e_p95_ms"),
    "vsearch.sqlite_vec_p95_ms": ("metrics", "vsearch", "sqlite_vec_p95_ms"),
}
ABSOLUTE_SLOS_MS = {
    "connect.stamped_p95_ms": 30.0,
    "recall.lexical_p95_ms": 50.0,
    "recall.hybrid_p95_ms": 200.0,
    "pack.e2e_p95_ms": 300.0,
    "vsearch.sqlite_vec_p95_ms": 30.0,
}


class _PerfEmbeddingProvider:
    provider_name = "perf-fixed-seed"
    model_id = MODEL

    def __init__(self, dim: int):
        self.dim = int(dim)

    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        del model
        vectors = []
        for text in texts:
            digest = hashlib.sha256(str(text).encode("utf-8")).digest()
            seed = SEED + int.from_bytes(digest[:8], "big")
            rng = random.Random(seed)
            vectors.append([rng.uniform(-1.0, 1.0) for _ in range(self.dim)])
        return vectors


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _latencies_ms(iterations: int, fn: Callable[[int], Any]) -> list[float]:
    values: list[float] = []
    for index in range(iterations):
        started = time.perf_counter()
        fn(index)
        values.append((time.perf_counter() - started) * 1000.0)
    return values


def _observation(index: int, rng: random.Random) -> dict[str, Any]:
    words = rng.sample(VOCABULARY, 7)
    return {
        "ts": f"2026-01-{(index % 28) + 1:02d}T{index % 24:02d}:{index % 60:02d}:00Z",
        "kind": "perf.synthetic",
        "summary": f"{' '.join(words)} sample-{index:05d}",
        "summary_en": f"{' '.join(reversed(words))} sample-{index:05d}",
        "lang": "en",
        "tool_name": f"perf-tool-{index % 8}",
        "detail": {"seed": SEED, "ordinal": index, "bucket": index % 32},
    }


def _fts_rows(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT o.id, o.summary, observations_fts.rank AS score
        FROM observations_fts
        JOIN observations o ON o.id = observations_fts.rowid
        WHERE observations_fts MATCH ?
        ORDER BY observations_fts.rank ASC
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()


def _measure_connect(workdir: Path) -> dict[str, float]:
    legacy_path = workdir / "legacy.sqlite"
    sqlite3.connect(legacy_path).close()
    started = time.perf_counter()
    conn = _connect(str(legacy_path))
    conn.close()
    legacy_ms = (time.perf_counter() - started) * 1000.0

    stamped_path = workdir / "stamped.sqlite"
    conn = _connect(str(stamped_path))
    conn.close()

    def connect_stamped(_index: int) -> None:
        stamped = _connect(str(stamped_path))
        stamped.close()

    stamped_values = _latencies_ms(20, connect_stamped)
    return {
        "legacy_first_connect_ms": round(legacy_ms, 3),
        "stamped_p50_ms": round(_percentile(stamped_values, 0.50), 3),
        "stamped_p95_ms": round(_percentile(stamped_values, 0.95), 3),
    }


def run_suite(rows: int, vector_dim: int) -> dict[str, Any]:
    if rows < 1:
        raise ValueError("--rows must be positive")
    if vector_dim < 1:
        raise ValueError("--vector-dim must be positive")

    rng = random.Random(SEED)
    with tempfile.TemporaryDirectory(prefix="openclaw-mem-perf-") as raw_tmp:
        workdir = Path(raw_tmp)
        connect_metrics = _measure_connect(workdir)
        db_path = workdir / "perf.sqlite"
        conn = _connect(str(db_path))

        started = time.perf_counter()
        with conn:
            for index in range(rows):
                _insert_observation(conn, _observation(index, rng))
        ingest_seconds = max(time.perf_counter() - started, 1e-9)

        broad_query_terms = [VOCABULARY[index % len(VOCABULARY)] for index in range(50)]
        product_queries = [
            " ".join(VOCABULARY[(index + offset) % len(VOCABULARY)] for offset in range(3))
            for index in range(50)
        ]
        search_values = _latencies_ms(50, lambda index: _fts_rows(conn, broad_query_terms[index]))

        vector_rng = random.Random(SEED + 1)
        with conn:
            for observation_id in range(1, rows + 1):
                vector = [vector_rng.uniform(-1.0, 1.0) for _ in range(vector_dim)]
                conn.execute(
                    """
                    INSERT INTO observation_embeddings
                        (observation_id, model, dim, vector, norm, created_at)
                    VALUES (?, ?, ?, ?, ?, '2026-01-01T00:00:00Z')
                    """,
                    (observation_id, MODEL, vector_dim, pack_f32(vector), l2_norm(vector)),
                )
        query_vectors = [
            [vector_rng.uniform(-1.0, 1.0) for _ in range(vector_dim)] for _ in range(20)
        ]
        sqlite_vec_values: list[float] = []
        sqlite_vec_version: str | None = None
        sqlite_vec_error: str | None = None
        try:
            vec_reindex = rebuild_sqlite_vec_indexes(conn)
            conn.commit()
            sqlite_vec_version = str(vec_reindex["sqlite_vec_version"])
            sqlite_vec_index = SqliteVecIndex()
            sqlite_vec_index.search(conn, query_vectors[0], model=MODEL, limit=20)
            sqlite_vec_values = _latencies_ms(
                20,
                lambda index: sqlite_vec_index.search(
                    conn,
                    query_vectors[index],
                    model=MODEL,
                    limit=20,
                ),
            )
        except Exception as exc:
            sqlite_vec_error = f"{type(exc).__name__}: {exc}"

        provider = _PerfEmbeddingProvider(vector_dim)
        provider_factory = lambda **_kwargs: provider
        core_recall(conn, product_queries[0], mode="lexical", limit=20)
        recall_lexical_values = _latencies_ms(
            50,
            lambda index: core_recall(
                conn,
                product_queries[index],
                mode="lexical",
                limit=20,
            ),
        )
        core_recall(
            conn,
            product_queries[0],
            mode="hybrid",
            limit=20,
            model=MODEL,
            vector_backend="auto",
            provider_factory=provider_factory,
        )
        recall_hybrid_values = _latencies_ms(
            20,
            lambda index: core_recall(
                conn,
                product_queries[index],
                mode="hybrid",
                limit=20,
                model=MODEL,
                vector_backend="auto",
                provider_factory=provider_factory,
            ),
        )

        def build_pack(index: int) -> str:
            hits = _fts_rows(conn, product_queries[index % len(product_queries)], limit=12)
            return json.dumps(
                {
                    "query": product_queries[index % len(product_queries)],
                    "items": [
                        {"recordRef": f"obs:{row['id']}", "summary": row["summary"]}
                        for row in hits
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )

        synthetic_pack_values = _latencies_ms(20, build_pack)

        def build_e2e_pack(index: int) -> dict[str, Any]:
            with redirect_stderr(io.StringIO()):
                return _invoke_cli_json(
                    conn,
                    [
                        "pack",
                        "--query",
                        product_queries[index % len(product_queries)],
                        "--limit",
                        "12",
                        "--budget-tokens",
                        "1200",
                        "--use-graph",
                        "auto",
                        "--vector-backend",
                        "auto",
                    ],
                )

        build_e2e_pack(0)
        e2e_pack_values = _latencies_ms(20, build_e2e_pack)

        # Keep the allocation-heavy exact backends after the product SLO lanes.
        # Pure Python materializes every embedding row per query and would
        # otherwise distort sqlite-vec/recall/pack timings through allocator
        # pressure rather than product-path work.
        python_index = PurePythonIndex()
        python_vector_values = _latencies_ms(
            20,
            lambda index: python_index.search(
                conn,
                query_vectors[index],
                model=MODEL,
                limit=20,
            ),
        )
        numpy_vector_values: list[float] = []
        try:
            numpy_index = NumpyIndex()
        except RuntimeError:
            numpy_index = None
        if numpy_index is not None:
            numpy_index.search(conn, query_vectors[0], model=MODEL, limit=20)
            numpy_vector_values = _latencies_ms(
                20,
                lambda index: numpy_index.search(
                    conn,
                    query_vectors[index],
                    model=MODEL,
                    limit=20,
                ),
            )
        conn.close()

    return {
        "kind": KIND,
        "schema_version": 1,
        "dataset": {
            "rows": rows,
            "seed": SEED,
            "vector_dim": vector_dim,
            "search_queries": 50,
            "recall_queries": {"lexical": 50, "hybrid": 20},
            "vector_queries": 20,
            "pack_queries": 20,
            "query_profile": "three-token-and-v1",
        },
        "metrics": {
            "ingest": {
                "elapsed_ms": round(ingest_seconds * 1000.0, 3),
                "rows_per_second": round(rows / ingest_seconds, 3),
            },
            "search": {
                "p50_ms": round(_percentile(search_values, 0.50), 3),
                "p95_ms": round(_percentile(search_values, 0.95), 3),
            },
            "vsearch": {
                "p95_ms": round(_percentile(python_vector_values, 0.95), 3),
                "python_p95_ms": round(_percentile(python_vector_values, 0.95), 3),
                "numpy_p95_ms": (
                    round(_percentile(numpy_vector_values, 0.95), 3)
                    if numpy_vector_values
                    else None
                ),
                "numpy_speedup": (
                    round(
                        _percentile(python_vector_values, 0.95)
                        / max(_percentile(numpy_vector_values, 0.95), 1e-9),
                        3,
                    )
                    if numpy_vector_values
                    else None
                ),
                "sqlite_vec_p95_ms": (
                    round(_percentile(sqlite_vec_values, 0.95), 3)
                    if sqlite_vec_values
                    else None
                ),
                "sqlite_vec_version": sqlite_vec_version,
                "sqlite_vec_error": sqlite_vec_error,
            },
            "recall": {
                "lexical_p50_ms": round(_percentile(recall_lexical_values, 0.50), 3),
                "lexical_p95_ms": round(_percentile(recall_lexical_values, 0.95), 3),
                "hybrid_p50_ms": round(_percentile(recall_hybrid_values, 0.50), 3),
                "hybrid_p95_ms": round(_percentile(recall_hybrid_values, 0.95), 3),
                "hybrid_vector_backend": "sqlite-vec" if sqlite_vec_values else "numpy",
            },
            "pack": {
                "p95_ms": round(_percentile(e2e_pack_values, 0.95), 3),
                "e2e_p50_ms": round(_percentile(e2e_pack_values, 0.50), 3),
                "e2e_p95_ms": round(_percentile(e2e_pack_values, 0.95), 3),
                "synthetic_render_p95_ms": round(_percentile(synthetic_pack_values, 0.95), 3),
                "graph_mode": "auto",
            },
            "connect": connect_metrics,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "sqlite": sqlite3.sqlite_version,
        },
        "notes": [
            "Fixed-seed synthetic data; no network or embedding API calls.",
            "Timing values are observational baselines and are not CI thresholds.",
            "Search reports the broad single-token diagnostic; recall and pack SLO lanes use deterministic three-token product queries.",
            "Pack timing covers deterministic lexical retrieval and compact rendering.",
            "Vector timing compares the exact Python and NumPy VectorIndex backends after NumPy cache warmup.",
            "sqlite-vec timing uses the persisted cosine vec0 index after an explicit rebuild.",
            "Recall hybrid uses a fixed-seed in-process embedding provider; pack e2e uses the real CLI handler without network access.",
        ],
    }


def run_matrix(vector_dim: int, tiers: tuple[int, ...] = (10_000, 100_000)) -> dict[str, Any]:
    return {
        "kind": MATRIX_KIND,
        "schema_version": 1,
        "tiers": {f"{rows // 1000}k": run_suite(rows, vector_dim) for rows in tiers},
    }


def _metric_value(report: dict[str, Any], path: tuple[str, ...]) -> float:
    value: Any = report
    for part in path:
        value = value[part]
    if value is None:
        raise ValueError(f"required performance metric unavailable: {'.'.join(path)}")
    return float(value)


def build_thresholds(matrix: dict[str, Any], tier: str = "100k") -> dict[str, Any]:
    report = matrix["tiers"][tier]
    metrics = {}
    for name, path in SLO_METRICS.items():
        baseline = _metric_value(report, path)
        metrics[name] = {
            "direction": "max",
            "baseline": round(baseline, 3),
            "regression_ratio": 0.20,
            "regression_limit": round(baseline * 1.20, 3),
            "tolerance_limit": round(baseline * 1.30, 3),
            "unit": "ms",
        }
    return {
        "kind": THRESHOLD_KIND,
        "schema_version": 1,
        "tier": tier,
        "source": "RUN-B-numbers.json",
        "policy": "fail when a latency metric regresses by more than 20%; retain a 1.3x published tolerance band",
        "metrics": metrics,
    }


def evaluate_thresholds(report: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    checks = []
    for name, config in thresholds["metrics"].items():
        path = SLO_METRICS[name]
        actual = _metric_value(report, path)
        limit = float(config["regression_limit"])
        checks.append(
            {
                "metric": name,
                "actual": round(actual, 3),
                "limit": limit,
                "ok": actual <= limit,
            }
        )
    return {
        "kind": "openclaw-mem.perf.gate.v1",
        "ok": all(item["ok"] for item in checks),
        "tier": thresholds["tier"],
        "checks": checks,
    }


def evaluate_absolute_slos(report: dict[str, Any], *, tier: str) -> dict[str, Any]:
    checks = []
    for name, limit in ABSOLUTE_SLOS_MS.items():
        actual = _metric_value(report, SLO_METRICS[name])
        checks.append(
            {
                "metric": name,
                "actual": round(actual, 3),
                "limit": limit,
                "ok": actual < limit,
            }
        )
    return {
        "kind": "openclaw-mem.perf.slo-gate.v1",
        "ok": all(item["ok"] for item in checks),
        "tier": tier,
        "checks": checks,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--vector-dim", type=int, default=16)
    parser.add_argument("--matrix", action="store_true", help="Run the fixed 10k and 100k tiers")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON on stdout")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Write the report to this path (10k runs default to BASELINE-10k.json)",
    )
    parser.add_argument("--write-thresholds", type=Path, help="Write thresholds derived from the 100k matrix tier")
    parser.add_argument("--check-thresholds", type=Path, help="Fail if the report regresses over the stored 20%% limits")
    parser.add_argument("--check-slos", action="store_true", help="Fail if the selected tier misses a published absolute SLO")
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = run_matrix(args.vector_dim) if args.matrix else run_suite(args.rows, args.vector_dim)
    if args.write_thresholds:
        if report.get("kind") != MATRIX_KIND:
            raise ValueError("--write-thresholds requires --matrix")
        thresholds = build_thresholds(report)
        args.write_thresholds.parent.mkdir(parents=True, exist_ok=True)
        args.write_thresholds.write_text(
            json.dumps(thresholds, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    gate = None
    if args.check_thresholds:
        thresholds = json.loads(args.check_thresholds.read_text(encoding="utf-8"))
        target = report["tiers"][thresholds["tier"]] if report.get("kind") == MATRIX_KIND else report
        gate = evaluate_thresholds(target, thresholds)
    target_tier = "100k" if args.matrix else f"{args.rows // 1000}k"
    target = report["tiers"][target_tier] if report.get("kind") == MATRIX_KIND else report
    slo_gate = evaluate_absolute_slos(target, tier=target_tier) if args.check_slos else None
    payload = dict(report)
    if gate is not None:
        payload["gate"] = gate
    if slo_gate is not None:
        payload["slo_gate"] = slo_gate
    baseline = args.baseline
    if baseline is None and not args.matrix and args.rows == 10_000:
        baseline = Path(__file__).with_name("BASELINE-10k.json")
    if baseline is not None:
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) if args.json else json.dumps(payload, ensure_ascii=False, indent=2))
    requested_gates = [item for item in (gate, slo_gate) if item is not None]
    return 0 if all(item["ok"] for item in requested_gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
