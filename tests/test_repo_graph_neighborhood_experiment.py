import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "repo_graph_neighborhood_experiment.py"
spec = importlib.util.spec_from_file_location("repo_graph_neighborhood_experiment", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

FIXTURE = Path(__file__).parent / "data" / "repo_graph_ingest"


def test_run_experiment_writes_schema_and_metrics(tmp_path):
    result = mod.run_experiment(
        FIXTURE / "knowledge-graph.json",
        FIXTURE,
        tmp_path,
        ["backend resolver", "pack observe boundaries"],
        k=5,
        depth=1,
    )

    comparison = result["comparison"]
    assert comparison["schema"] == "openclaw.experiment.repo_graph_neighborhood.v0"
    assert comparison["validation"]["ok"] is True
    assert len(comparison["comparisons"]) == 2
    assert (tmp_path / "pack.json").is_file()
    assert (tmp_path / "comparison.json").is_file()
    assert (tmp_path / "manifest.json").is_file()
    assert (tmp_path / "report.md").is_file()

    pack = json.loads((tmp_path / "pack.json").read_text())
    assert pack["schema"] == "openclaw.context_pack.repo_graph_ingest.v0"
    assert pack["stats"]["nodes"] == 5
    assert pack["stats"]["validationOk"] is True


def test_graph_neighborhood_adds_neighbor_paths(tmp_path):
    result = mod.run_experiment(
        FIXTURE / "knowledge-graph.json",
        FIXTURE,
        tmp_path,
        ["build pack"],
        k=5,
        depth=1,
    )
    item = result["comparison"]["comparisons"][0]
    graph_paths = mod.paths_from_graph(item["graph"])
    assert "notes.md" in graph_paths
    assert item["metrics"]["graphPathCountIncludingNeighbors"] >= 1


def test_deterministic_ordering_for_graph_hits():
    graph = mod.load_graph(FIXTURE / "knowledge-graph.json")
    first = mod.graph_hits(graph, "pack", k=10, depth=1)
    second = mod.graph_hits(graph, "pack", k=10, depth=1)
    assert first == second
