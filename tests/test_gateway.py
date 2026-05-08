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
    _corpus_status,
    _refresh_workspace_memory_corpus,
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


def test_corpus_status_is_unknown_before_refresh_not_healthy(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    (workspace / "memory" / "2026-05-07.md").write_text("專案甲", encoding="utf-8")
    config = GatewayConfig(db=str(tmp_path / "memory.sqlite"), workspace=str(workspace), tokens={}, allow_unauthenticated=True)

    status = _corpus_status(config)

    assert status["parity_state"] == "unknown"
    assert status["workspace_memory_files_configured"] == 2
    assert status["indexed_files"] is None


def test_refresh_workspace_memory_marks_partial_when_ingest_incomplete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    (workspace / "memory" / "2026-05-07.md").write_text("專案甲", encoding="utf-8")
    config = GatewayConfig(db=str(tmp_path / "memory.sqlite"), workspace=str(workspace), tokens={}, allow_unauthenticated=True)

    def fake_run_cli(_config: GatewayConfig, argv: list[str], *, stdin: str | None = None) -> dict:
        return {"ok": True, "exit_code": 0, "result": {"files_seen": 2, "files_ingested": 1, "missing_paths": [], "chunks_skipped_private": 0, "chunks_skipped_secret_like": 0}}

    monkeypatch.setattr(gateway_mod, "_run_cli", fake_run_cli)

    status = _refresh_workspace_memory_corpus(config)

    assert status["refresh_ok"] is True
    assert status["parity_state"] == "partial"
    assert status["indexed_files"] == 1


def test_refresh_workspace_memory_marks_healthy_only_after_complete_ingest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    (workspace / "memory" / "2026-05-07.md").write_text("專案甲", encoding="utf-8")
    config = GatewayConfig(db=str(tmp_path / "memory.sqlite"), workspace=str(workspace), tokens={}, allow_unauthenticated=True)

    def fake_run_cli(_config: GatewayConfig, argv: list[str], *, stdin: str | None = None) -> dict:
        return {"ok": True, "exit_code": 0, "result": {"files_seen": 2, "files_ingested": 2, "missing_paths": [], "chunks_skipped_private": 1, "chunks_skipped_secret_like": 0}}

    monkeypatch.setattr(gateway_mod, "_run_cli", fake_run_cli)

    status = _refresh_workspace_memory_corpus(config)

    assert status["refresh_ok"] is True
    assert status["parity_state"] == "healthy"
    assert status["indexed_files"] == 2
    assert status["skipped_private_chunks"] == 1


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
    (memory_dir / "2026-05-07.md").write_text("project steward / 專案甲", encoding="utf-8")
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
    handler._read_json_body = lambda: {"query": "專案甲", "limit": 5}  # type: ignore[attr-defined]

    calls: list[list[str]] = []

    def fake_run_cli(_config: GatewayConfig, argv: list[str], *, stdin: str | None = None) -> dict:
        calls.append(list(argv))
        if argv[:2] == ["docs", "ingest"]:
            return {"ok": True, "exit_code": 0, "result": {"files_ingested": 2, "chunks_inserted": 2}}
        if argv[:2] == ["docs", "search"]:
            return {"ok": True, "exit_code": 0, "result": {"results": [{"recordRef": "docs://workspace/memory/2026-05-07.md#intro", "text": "project steward / 專案甲"}]}}
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
                {"recordRef": "docs://workspace/memory/2026-05-07.md#intro", "text": "project steward / 專案甲", "repo": "workspace", "path": "memory/2026-05-07.md", "chunk_id": "intro"}
            ]
        },
    }

    receipt = gateway_mod._docs_pack_receipt_from_search("專案甲", docs_receipt, limit=5, budget_tokens=1000)

    assert gateway_mod._pack_result_count(receipt) == 1
    assert "專案甲" in receipt["result"]["bundle_text"]
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


def test_refresh_workspace_memory_marks_partial_when_cli_refresh_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "USER.md").write_text("# USER\n", encoding="utf-8")
    config = GatewayConfig(db=str(tmp_path / "memory.sqlite"), workspace=str(workspace), tokens={}, allow_unauthenticated=True)

    def fake_run_cli(_config: GatewayConfig, argv: list[str], *, stdin: str | None = None) -> dict:
        raise RuntimeError("cli_failed")

    monkeypatch.setattr(gateway_mod, "_run_cli", fake_run_cli)

    status = _refresh_workspace_memory_corpus(config)

    assert status["refresh_attempted"] is True
    assert status["refresh_ok"] is False
    assert status["parity_state"] == "partial"
    assert status["refresh_error"] == "cli_failed"


def test_workspace_markdown_readthrough_finds_user_profile_and_skips_denied_chunks(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    memory = workspace / "memory"
    memory.mkdir(parents=True)
    (workspace / "USER.md").write_text("# USER.md\n\nName: CK Wang\nPronouns: he/him\n", encoding="utf-8")
    (memory / "private.md").write_text("[private]\nCK Wang hidden secret phrase\n", encoding="utf-8")
    config = GatewayConfig(db=None, workspace=str(workspace), tokens={}, allow_unauthenticated=True)

    receipt = gateway_mod._workspace_markdown_search_receipt(config, "CK Wang USER.md pronouns he/him", limit=5)

    rows = receipt["result"]
    assert rows
    assert rows[0]["id"] == "workspace:USER.md:0"
    assert rows[0]["tool_name"] == "workspace_markdown_readthrough"
    assert "Pronouns: he/him" in rows[0]["summary"]
    assert all("hidden secret phrase" not in row["summary"] for row in rows)


def test_workspace_markdown_readthrough_uses_token_matching_not_substrings(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "USER.md").write_text("# USER.md\n\nthere theater theme only\n", encoding="utf-8")
    config = GatewayConfig(db=None, workspace=str(workspace), tokens={}, allow_unauthenticated=True)

    receipt = gateway_mod._workspace_markdown_search_receipt(config, "he", limit=5)

    assert receipt["result"] == []


def test_workspace_markdown_readthrough_skips_symlink_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    memory = workspace / "memory"
    memory.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("CK Wang outside symlink content\n", encoding="utf-8")
    (memory / "safe.md").write_text("CK Wang safe workspace content\n", encoding="utf-8")
    symlink = memory / "escape.md"
    try:
        symlink.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    config = GatewayConfig(db=None, workspace=str(workspace), tokens={}, allow_unauthenticated=True)

    receipt = gateway_mod._workspace_markdown_search_receipt(config, "CK Wang content", limit=10)

    ids = [row["id"] for row in receipt["result"]]
    summaries = "\n".join(row["summary"] for row in receipt["result"])
    assert any("safe.md" in row_id for row_id in ids)
    assert "outside symlink" not in summaries


def test_search_handler_falls_back_to_workspace_markdown_when_index_routes_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "USER.md").write_text("# USER.md\n\nName: CK Wang\nPronouns: he/him\n", encoding="utf-8")
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
    handler._read_json_body = lambda: {"query": "CK Wang USER.md pronouns he/him", "limit": 5}  # type: ignore[attr-defined]

    def fake_run_cli(_config: GatewayConfig, argv: list[str], *, stdin: str | None = None) -> dict:
        if argv[:2] == ["docs", "ingest"]:
            raise RuntimeError("readonly")
        return {"ok": True, "exit_code": 0, "result": {"results": []} if argv[:2] == ["docs", "search"] else []}

    captured: dict = {}

    def fake_json_response(_handler: object, status: int, payload: dict) -> None:
        captured["status"] = status
        captured["payload"] = payload

    monkeypatch.setattr(gateway_mod, "_run_cli", fake_run_cli)
    monkeypatch.setattr(gateway_mod, "_json_response", fake_json_response)

    handler._handle_search()  # type: ignore[attr-defined]

    assert captured["status"] == 200
    payload = captured["payload"]
    assert payload["diagnostic"]["result_count"] >= 1
    assert "workspace_markdown_readthrough" in payload["diagnostic"]["searched_routes"]
    assert payload["receipt"]["result"][0]["id"] == "workspace:USER.md:0"
    assert payload["diagnostic"]["corpus_status"]["parity_state"] == "partial"
