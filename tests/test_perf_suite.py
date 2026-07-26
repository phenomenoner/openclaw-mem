from __future__ import annotations

import copy

from benchmarks.perf.perf_suite import (
    ABSOLUTE_SLOS_MS,
    MATRIX_KIND,
    PACK_QUERY_ITERATIONS,
    SLO_METRICS,
    _percentile,
    build_thresholds,
    evaluate_absolute_slos,
    evaluate_thresholds,
    run_suite,
)


def test_perf_suite_includes_sqlite_vec_recall_and_real_pack_lanes() -> None:
    report = run_suite(50, 4)
    assert report["metrics"]["vsearch"]["sqlite_vec_p95_ms"] is not None
    assert report["metrics"]["vsearch"]["sqlite_vec_error"] is None
    assert report["metrics"]["recall"]["hybrid_vector_backend"] == "sqlite-vec"
    assert report["metrics"]["recall"]["lexical_p95_ms"] > 0
    assert report["metrics"]["pack"]["e2e_p95_ms"] > 0
    assert report["metrics"]["pack"]["graph_mode"] == "auto"
    assert report["dataset"]["pack_queries"] == PACK_QUERY_ITERATIONS
    diagnostics = report["metrics"]["pack"]["diagnostics"]
    assert diagnostics["sample_count"] == PACK_QUERY_ITERATIONS
    assert diagnostics["max_ms"] >= report["metrics"]["pack"]["e2e_p95_ms"]
    assert len(diagnostics["slowest_samples"]) == 5
    assert len(diagnostics["slowest_replays"]) == 3
    assert all(item["replay_stages_ms"] for item in diagnostics["slowest_replays"])


def test_pack_p95_ignores_one_runner_pause_but_catches_persistent_regression() -> None:
    one_runner_pause = [20.0] * (PACK_QUERY_ITERATIONS - 1) + [7_000.0]
    persistent_regression = [20.0] * (PACK_QUERY_ITERATIONS - 5) + [350.0] * 5

    assert _percentile(one_runner_pause, 0.95) == 20.0
    assert max(one_runner_pause) == 7_000.0
    assert _percentile(persistent_regression, 0.95) == 350.0


def test_thresholds_record_20_percent_gate_and_30_percent_tolerance() -> None:
    report = run_suite(20, 2)
    matrix = {"kind": MATRIX_KIND, "schema_version": 1, "tiers": {"100k": report}}
    thresholds = build_thresholds(matrix)
    assert set(thresholds["metrics"]) == set(SLO_METRICS)
    for config in thresholds["metrics"].values():
        assert config["regression_limit"] == round(config["baseline"] * 1.20, 3)
        assert config["tolerance_limit"] == round(config["baseline"] * 1.30, 3)
    assert evaluate_thresholds(report, thresholds)["ok"] is True

    regressed = copy.deepcopy(report)
    regressed["metrics"]["connect"]["stamped_p95_ms"] = (
        thresholds["metrics"]["connect.stamped_p95_ms"]["regression_limit"] + 0.001
    )
    gate = evaluate_thresholds(regressed, thresholds)
    assert gate["ok"] is False
    assert next(item for item in gate["checks"] if item["metric"] == "connect.stamped_p95_ms")["ok"] is False


def test_absolute_slo_gate_covers_every_published_product_lane() -> None:
    # Gate semantics are deterministic unit-test territory; real latency is
    # exercised by the perf jobs and must not make the functional suite flaky.
    report = {
        "metrics": {
            "connect": {"stamped_p95_ms": 29.999},
            "recall": {"lexical_p95_ms": 49.999, "hybrid_p95_ms": 199.999},
            "pack": {"e2e_p95_ms": 299.999},
            "vsearch": {"sqlite_vec_p95_ms": 29.999},
        }
    }
    gate = evaluate_absolute_slos(report, tier="test")

    assert gate["ok"] is True
    assert {item["metric"] for item in gate["checks"]} == set(ABSOLUTE_SLOS_MS)

    regressed = copy.deepcopy(report)
    regressed["metrics"]["pack"]["e2e_p95_ms"] = ABSOLUTE_SLOS_MS["pack.e2e_p95_ms"]
    gate = evaluate_absolute_slos(regressed, tier="test")
    assert gate["ok"] is False
    assert next(item for item in gate["checks"] if item["metric"] == "pack.e2e_p95_ms")["ok"] is False
