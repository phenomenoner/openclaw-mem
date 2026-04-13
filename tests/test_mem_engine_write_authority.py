import json
from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "index.ts"
PLUGIN_JSON = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "openclaw.plugin.json"
MEM_ENGINE_DOC = Path(__file__).resolve().parents[1] / "docs" / "mem-engine.md"


def test_single_write_path_markers_present_in_ts_and_schema():
    ts = INDEX_TS.read_text("utf-8")
    plugin = json.loads(PLUGIN_JSON.read_text("utf-8"))

    assert "only canonical durable-memory write lane" in ts
    assert "autoCapture disabled (readOnly=" in ts
    assert 'tool: "memory_store"' in ts
    assert 'tool: "memory_forget"' in ts
    assert 'tool: "memory_import"' in ts
    assert 'tool: "memory_docs_ingest"' in ts
    assert "Refusing to import memories: openclaw-mem-engine is running in read-only mode." in ts
    assert "Re-run with dryRun/validateOnly if you only need validation." in ts
    assert "Refusing to ingest docs: openclaw-mem-engine is running in read-only mode." in ts

    help_text = plugin["uiHints"]["readOnly"]["help"]
    assert "only canonical slot owner" in help_text
    assert "sidecar/docs/graph as read-or-observe lanes" in help_text


def test_readonly_enforcement_covers_import_docs_and_startup_ingest_paths():
    ts = INDEX_TS.read_text("utf-8")

    # Non-dry-run imports must be rejected when readOnly is on, but validation stays allowed.
    assert "const effectiveDryRun = Boolean(parsed.dryRun) || Boolean(parsed.validateOnly);" in ts
    assert "if (readOnlyEnabled && !effectiveDryRun) {" in ts

    # Manual docs ingest must be blocked in readOnly mode.
    assert 'name: "memory_docs_ingest"' in ts
    assert "if (readOnlyEnabled) {" in ts
    assert "Refusing to ingest docs: openclaw-mem-engine is running in read-only mode." in ts

    # Startup docs ingest must also stay off under readOnly so the boundary is single-write-path, not tool-only.
    assert "if (docsColdLaneResolved.enabled && docsColdLaneResolved.ingestOnStart && !readOnlyEnabled) {" in ts


def test_mem_engine_docs_state_single_write_path_posture():
    doc = MEM_ENGINE_DOC.read_text("utf-8")

    assert "Single-write-path posture" in doc
    assert "only canonical durable-memory write path" in doc
    assert "graph/docs/synthesis lanes may improve recall or packing" in doc
    assert "do not become competing durable-memory writers" in doc
