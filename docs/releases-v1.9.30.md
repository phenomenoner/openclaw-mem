# openclaw-mem v1.9.30 draft notes

Date: 2026-06-18
Status: draft

## Harness support-plane recovery

- `--harness-home` now resolves DB, credentials, config, and runtime state-file reporting under the explicit harness home.
- `graph topology-extract --harness-home <home> --workspace <workspace>` can emit the default harness support-plane artifact:
  - `<home>/state/memory/graph/topology-extract-full.json`
- Added file-only readiness probes:
  - `service-store init|status`
  - `writeback-store init|status`
- Service-store readiness aligns with Agent Harness core's active store path:
  - `<home>/memory/openclaw-mem-service-store.jsonl`
- Writeback readiness remains support-plane state:
  - `<home>/state/memory/openclaw-mem-writeback.jsonl`
- Store readiness `init` commands create empty JSONL files only; they do not append memory facts or promote ownership.
- `qdrant recall --vector <json-array>` can attempt a bounded Qdrant Edge bridge call when a shard and dependency are present, and remains fail-closed otherwise.
- Package metadata is bumped to `1.9.30` in `pyproject.toml`, `openclaw_mem/__init__.py`, and `uv.lock`.

## Verification

Targeted tests:

```bash
uv run --python 3.13 pytest tests/test_cli.py::TestCliM0::test_status_harness_home_reports_state_files_under_harness_home tests/test_cli.py::TestCliM0::test_service_and_writeback_store_init_status_are_file_only tests/test_cli.py::TestCliM0::test_status_harness_env_bridge_redacts_secret_values -q
uv run --python 3.13 pytest tests/test_cli.py::TestCliM0::test_service_and_qdrant_contract_probes_are_shadow_only -q
uv run --python 3.13 pytest tests/test_graph_topology_extract.py -q
```
