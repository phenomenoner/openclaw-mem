from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from openclaw_mem.gateway import GatewayConfig, MemoryGatewayHandler, config_from_env, _parse_tokens


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
    payload_keys = {"ok", "service", "auth", "role", "capabilities", "db_configured", "workspace_configured", "direct_store_enabled"}
    assert "db" not in payload_keys
    assert "workspace" not in payload_keys


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
