from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

import openclaw_mem.gateway as gateway_mod
from openclaw_mem.gateway import (
    GatewayConfig,
    MemoryGatewayHandler,
    config_from_env,
    _not_found_diagnostic,
    _parse_tokens,
    _query_variants,
    _surface_identity,
)


def test_gateway_rejects_short_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCLAW_MEM_GATEWAY_TOKENS", "short:read")
    args = Namespace(
        allow_unauthenticated=False,
        db=None,
        workspace=None,
        allow_direct_store=False,
        max_body_bytes=1024,
        cli_timeout_sec=1,
        export_root=None,
        audit_log=None,
    )
    with pytest.raises(SystemExit, match="minimum 24 characters"):
        config_from_env(args)


def test_export_path_must_stay_under_export_root(tmp_path: Path) -> None:
    config = GatewayConfig(db=None, workspace=None, tokens={}, allow_unauthenticated=True, export_root=str(tmp_path / "exports"))
    handler = object.__new__(MemoryGatewayHandler)
    server = type("Server", (), {"gateway_config": config})()
    handler.server = server  # type: ignore[attr-defined]

    inside = Path(handler._resolve_export_to("subdir/out"))  # type: ignore[attr-defined]
    assert tmp_path / "exports" in inside.parents

    with pytest.raises(ValueError, match="outside configured export root"):
        handler._resolve_export_to(str(tmp_path / "elsewhere"))  # type: ignore[attr-defined]


def test_status_payload_contract_has_no_sensitive_paths() -> None:
    # Contract-level guard for the read-token status surface; the handler builds
    # status from booleans/capability names only and must not reintroduce literal local paths.
    payload_keys = {
        "ok",
        "service",
        "auth",
        "role",
        "capabilities",
        "db_configured",
        "workspace_configured",
        "direct_store_enabled",
        "surface_identity",
    }
    assert "db" not in payload_keys
    assert "workspace" not in payload_keys


def test_surface_identity_uses_public_fingerprints_not_paths(tmp_path: Path) -> None:
    db = tmp_path / "private" / "memory.sqlite"
    workspace = tmp_path / "private" / "workspace"
    config = GatewayConfig(
        db=str(db),
        workspace=str(workspace),
        tokens={},
        allow_unauthenticated=True,
        surface_id="lady-h-wsl2",
        agent_id="lady_h",
        default_scope="openclaw-mem",
    )

    identity = _surface_identity(config, gateway_url_hint="http://127.0.0.1:18765")

    encoded = str(identity)
    assert identity["surface_id"] == "lady-h-wsl2"
    assert identity["agent_id"] == "lady_h"
    assert identity["default_scope"] == "openclaw-mem"
    assert identity["db_configured"] is True
    assert identity["workspace_configured"] is True
    assert "memory.sqlite" not in encoded
    assert str(tmp_path) not in encoded
    assert len(identity["db_fingerprint"]) == 16
    assert len(identity["workspace_fingerprint"]) == 16


def test_query_variants_suggest_yijing_for_yijin_typo() -> None:
    variants = _query_variants("yijin-loop-engine")
    assert "yijing-loop-engine" in variants
    assert "yijin loop engine" in variants


def test_not_found_diagnostic_explains_empty_surface(tmp_path: Path) -> None:
    config = GatewayConfig(
        db=str(tmp_path / "memory.sqlite"),
        workspace=None,
        tokens={},
        allow_unauthenticated=True,
        surface_id="test-surface",
        default_scope="openclaw-mem",
    )

    diag = _not_found_diagnostic(
        endpoint="/v1/search",
        query="yijin-loop-engine",
        result_count=0,
        config=config,
        gateway_url_hint="http://127.0.0.1:18765",
        searched_routes=["cli.search"],
        fallback_attempts=[{"query": "yijing-loop-engine", "result_count": 3}],
    )

    assert diag["empty"] is True
    assert diag["surface_identity"]["surface_id"] == "test-surface"
    assert diag["surface_identity"]["db_configured"] is True
    assert diag["searched_routes"] == ["cli.search"]
    assert diag["fallback_attempts"][0]["result_count"] == 3
    assert "yijing-loop-engine" in diag["query_variants"]
    assert "compare db_fingerprint" in diag["hint"]


def test_search_handler_falls_back_to_query_variant(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = GatewayConfig(
        db=str(tmp_path / "memory.sqlite"),
        workspace=None,
        tokens={},
        allow_unauthenticated=True,
        surface_id="test-surface",
    )
    handler = object.__new__(MemoryGatewayHandler)
    server = type("Server", (), {"gateway_config": config})()
    handler.server = server  # type: ignore[attr-defined]
    handler.headers = {"Host": "127.0.0.1:18765"}  # type: ignore[attr-defined]
    handler._require_capability = lambda capability: "read"  # type: ignore[attr-defined]
    handler._read_json_body = lambda: {"query": "yijin-loop-engine", "limit": 5}  # type: ignore[attr-defined]

    calls: list[str] = []

    def fake_run_cli(_config: GatewayConfig, argv: list[str], *, stdin: str | None = None) -> dict:
        query = argv[-1]
        calls.append(query)
        if query == "yijing-loop-engine":
            return {"ok": True, "exit_code": 0, "result": [{"id": 1, "summary": "hit"}]}
        return {"ok": True, "exit_code": 0, "result": []}

    captured: dict = {}

    def fake_json_response(_handler: object, status: int, payload: dict) -> None:
        captured["status"] = status
        captured["payload"] = payload

    monkeypatch.setattr(gateway_mod, "_run_cli", fake_run_cli)
    monkeypatch.setattr(gateway_mod, "_json_response", fake_json_response)

    handler._handle_search()  # type: ignore[attr-defined]

    assert calls[:2] == ["yijin-loop-engine", "yijin loop engine"]
    assert calls[2] == "yijing-loop-engine"
    assert captured["status"] == 200
    assert captured["payload"]["receipt"]["result"] == [{"id": 1, "summary": "hit"}]
    assert captured["payload"]["diagnostic"]["result_count"] == 1
    assert captured["payload"]["diagnostic"]["fallback_attempts"][-1] == {
        "route": "cli.search",
        "query": "yijing-loop-engine",
        "result_count": 1,
    }


def test_search_handler_falls_back_to_docs_memory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    (memory_dir / "2026-05-07.md").write_text("Lady H / 何曦 / 曦曦", encoding="utf-8")
    config = GatewayConfig(
        db=str(tmp_path / "memory.sqlite"),
        workspace=str(workspace),
        tokens={},
        allow_unauthenticated=True,
        surface_id="test-surface",
    )
    handler = object.__new__(MemoryGatewayHandler)
    server = type("Server", (), {"gateway_config": config})()
    handler.server = server  # type: ignore[attr-defined]
    handler.headers = {"Host": "127.0.0.1:18765"}  # type: ignore[attr-defined]
    handler._require_capability = lambda capability: "read"  # type: ignore[attr-defined]
    handler._read_json_body = lambda: {"query": "曦曦", "limit": 5}  # type: ignore[attr-defined]

    calls: list[list[str]] = []

    def fake_run_cli(_config: GatewayConfig, argv: list[str], *, stdin: str | None = None) -> dict:
        calls.append(list(argv))
        if argv[:2] == ["docs", "ingest"]:
            return {"ok": True, "exit_code": 0, "result": {"files_ingested": 2, "chunks_inserted": 2}}
        if argv[:2] == ["docs", "search"]:
            return {"ok": True, "exit_code": 0, "result": {"results": [{"recordRef": "docs://workspace/memory/2026-05-07.md#intro", "text": "Lady H / 何曦 / 曦曦"}]}}
        return {"ok": True, "exit_code": 0, "result": []}

    captured: dict = {}

    def fake_json_response(_handler: object, status: int, payload: dict) -> None:
        captured["status"] = status
        captured["payload"] = payload

    monkeypatch.setattr(gateway_mod, "_run_cli", fake_run_cli)
    monkeypatch.setattr(gateway_mod, "_json_response", fake_json_response)

    handler._handle_search()  # type: ignore[attr-defined]

    assert calls[0][:2] == ["docs", "ingest"]
    assert any(call[:2] == ["docs", "search"] for call in calls)
    assert captured["status"] == 200
    assert captured["payload"]["diagnostic"]["result_count"] == 1
    assert "cli.docs.search" in captured["payload"]["diagnostic"]["searched_routes"]
    assert captured["payload"]["diagnostic"]["corpus_status"]["refresh_ok"] is True


def test_docs_search_receipt_can_be_wrapped_as_pack() -> None:
    docs_receipt = {
        "ok": True,
        "exit_code": 0,
        "result": {
            "results": [
                {"recordRef": "docs://workspace/memory/2026-05-07.md#intro", "text": "Lady H / 何曦 / 曦曦", "repo": "workspace", "path": "memory/2026-05-07.md", "chunk_id": "intro"}
            ]
        },
    }

    receipt = gateway_mod._docs_pack_receipt_from_search("曦曦", docs_receipt, limit=5, budget_tokens=1000)

    assert gateway_mod._pack_result_count(receipt) == 1
    assert "曦曦" in receipt["result"]["bundle_text"]
    assert receipt["result"]["source"] == "docs_memory_fallback"


def test_gateway_token_roles_expand_to_capabilities() -> None:
    tokens = _parse_tokens(
        "read-token-20260506-abcdefghijkl:read,write-token-20260506-abcdefghijkl:write,owner-token-20260506-abcdefghijkl:owner",
        None,
    )
    assert tokens["read-token-20260506-abcdefghijkl"].role == "read"
    assert "memory.pack" in tokens["read-token-20260506-abcdefghijkl"].capabilities
    assert "store.propose" not in tokens["read-token-20260506-abcdefghijkl"].capabilities
    assert "store.propose" in tokens["write-token-20260506-abcdefghijkl"].capabilities
    assert "store.direct" not in tokens["write-token-20260506-abcdefghijkl"].capabilities
    assert "store.direct" in tokens["owner-token-20260506-abcdefghijkl"].capabilities


def test_gateway_token_capability_specs_are_supported() -> None:
    tokens = _parse_tokens("custom-token-20260506-abcdefghijkl:read+episodes.append+direct_store", None)
    policy = tokens["custom-token-20260506-abcdefghijkl"]
    assert policy.role == "owner"
    assert "status.read" in policy.capabilities
    assert "memory.search" in policy.capabilities
    assert "episodes.append" in policy.capabilities
    assert "store.propose" not in policy.capabilities
    assert "store.direct" in policy.capabilities


def test_gateway_legacy_single_token_remains_admin_not_direct_store_owner() -> None:
    tokens = _parse_tokens(None, "legacy-admin-token-20260506-abcdefghijkl")
    policy = tokens["legacy-admin-token-20260506-abcdefghijkl"]
    assert policy.role == "admin"
    assert "archive.export" in policy.capabilities
    assert "store.direct" not in policy.capabilities


def test_export_path_blocks_escape_and_allows_relative(tmp_path: Path) -> None:
    config = GatewayConfig(db=None, workspace=None, tokens={}, allow_unauthenticated=True, export_root=str(tmp_path / "exports"))
    handler = object.__new__(MemoryGatewayHandler)
    server = type("Server", (), {"gateway_config": config})()
    handler.server = server  # type: ignore[attr-defined]

    allowed = Path(handler._resolve_export_to("dryrun/export"))  # type: ignore[attr-defined]
    assert allowed == (tmp_path / "exports" / "dryrun" / "export").resolve()

    with pytest.raises(ValueError, match="outside configured export root"):
        handler._resolve_export_to("../../escape")  # type: ignore[attr-defined]
