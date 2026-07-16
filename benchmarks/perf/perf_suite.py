#!/usr/bin/env python3
"""Deterministic, offline performance smoke suite for openclaw-mem.

The corpus, queries, and fake embeddings are generated from a fixed seed. The
reported timings are observations, not pass/fail thresholds, so the suite is
safe to run across different developer machines without creating flaky gates.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import random
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from openclaw_mem.cli import _connect, _insert_observation  # noqa: E402
from openclaw_mem.core.vector_index import NumpyIndex, PurePythonIndex  # noqa: E402
from openclaw_mem.vector import l2_norm, pack_f32  # noqa: E402


KIND = "openclaw-mem.perf.report.v1"
SEED = 20260716
VOCABULARY = (
    "agent memory graph retrieval policy receipt session observation context "
    "store pack search vector durable local evidence rollback migration"
).split()


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
        SELECT o.id, o.summary, bm25(observations_fts) AS score
        FROM observations_fts
        JOIN observations o ON o.id = observations_fts.rowid
        WHERE observations_fts MATCH ?
        ORDER BY score ASC
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

        query_terms = [VOCABULARY[index % len(VOCABULARY)] for index in range(50)]
        search_values = _latencies_ms(50, lambda index: _fts_rows(conn, query_terms[index]))

        vector_rng = random.Random(SEED + 1)
        with conn:
            for observation_id in range(1, rows + 1):
                vector = [vector_rng.uniform(-1.0, 1.0) for _ in range(vector_dim)]
                conn.execute(
                    """
                    INSERT INTO observation_embeddings
                        (observation_id, model, dim, vector, norm, created_at)
                    VALUES (?, 'perf-fake-v1', ?, ?, ?, '2026-01-01T00:00:00Z')
                    """,
                    (observation_id, vector_dim, pack_f32(vector), l2_norm(vector)),
                )
        query_vectors = [
            [vector_rng.uniform(-1.0, 1.0) for _ in range(vector_dim)] for _ in range(20)
        ]
        python_index = PurePythonIndex()
        python_vector_values = _latencies_ms(
            20,
            lambda index: python_index.search(
                conn,
                query_vectors[index],
                model="perf-fake-v1",
                limit=20,
            ),
        )
        numpy_vector_values: list[float] = []
        try:
            numpy_index = NumpyIndex()
        except RuntimeError:
            numpy_index = None
        if numpy_index is not None:
            numpy_index.search(
                conn, query_vectors[0], model="perf-fake-v1", limit=20
            )
            numpy_vector_values = _latencies_ms(
                20,
                lambda index: numpy_index.search(
                    conn,
                    query_vectors[index],
                    model="perf-fake-v1",
                    limit=20,
                ),
            )

        def build_pack(index: int) -> str:
            hits = _fts_rows(conn, query_terms[index % len(query_terms)], limit=12)
            return json.dumps(
                {
                    "query": query_terms[index % len(query_terms)],
                    "items": [
                        {"recordRef": f"obs:{row['id']}", "summary": row["summary"]}
                        for row in hits
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )

        pack_values = _latencies_ms(20, build_pack)
        conn.close()

    return {
        "kind": KIND,
        "schema_version": 1,
        "dataset": {
            "rows": rows,
            "seed": SEED,
            "vector_dim": vector_dim,
            "search_queries": 50,
            "vector_queries": 20,
            "pack_queries": 20,
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
            },
            "pack": {"p95_ms": round(_percentile(pack_values, 0.95), 3)},
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
            "Pack timing covers deterministic lexical retrieval and compact rendering.",
            "Vector timing compares the exact Python and NumPy VectorIndex backends after NumPy cache warmup.",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--vector-dim", type=int, default=16)
    parser.add_argument("--json", action="store_true", help="Emit compact JSON on stdout")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Write the report to this path (10k runs default to BASELINE-10k.json)",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = run_suite(args.rows, args.vector_dim)
    baseline = args.baseline
    if baseline is None and args.rows == 10_000:
        baseline = Path(__file__).with_name("BASELINE-10k.json")
    if baseline is not None:
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")) if args.json else json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
