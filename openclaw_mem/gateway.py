"""Authenticated local HTTP gateway for openclaw-mem.

This module intentionally uses the Python standard library so the gateway can be
started from an existing checkout without installing a web framework.  It is a
small governed HTTP wrapper around the existing CLI contracts; the CLI remains
the store/pack/observe implementation owner.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import urlparse

ROLE_RANK = {"read": 1, "write": 2, "admin": 3}
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_MAX_BODY_BYTES = 128 * 1024
DEFAULT_EXPORT_ROOT = os.path.expanduser("~/.openclaw/workspace/.state/openclaw-mem-gateway-exports")
MIN_TOKEN_CHARS = 24
DEFAULT_AUDIT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_IDEMPOTENCY_TTL_SEC = 24 * 60 * 60


class GatewayConfig:
    def __init__(
        self,
        *,
        db: Optional[str],
        workspace: Optional[str],
        tokens: Mapping[str, str],
        allow_unauthenticated: bool = False,
        allow_direct_store: bool = False,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        cli_timeout_sec: float = 45.0,
        export_root: Optional[str] = None,
        audit_log: Optional[str] = None,
        audit_max_bytes: int = DEFAULT_AUDIT_MAX_BYTES,
        idempotency_ttl_sec: int = DEFAULT_IDEMPOTENCY_TTL_SEC,
    ) -> None:
        self.db = db
        self.workspace = workspace
        self.tokens = dict(tokens)
        self.allow_unauthenticated = bool(allow_unauthenticated)
        self.allow_direct_store = bool(allow_direct_store)
        self.max_body_bytes = int(max_body_bytes)
        self.cli_timeout_sec = float(cli_timeout_sec)
        self.export_root = export_root or DEFAULT_EXPORT_ROOT
        self.audit_log = audit_log
        self.audit_max_bytes = int(audit_max_bytes)
        self.idempotency_ttl_sec = int(idempotency_ttl_sec)


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_tokens(raw_multi: Optional[str], raw_single: Optional[str]) -> Dict[str, str]:
    """Parse token config without ever returning token text in receipts.

    Supported:
    - OPENCLAW_MEM_GATEWAY_TOKENS='tokenA:read,tokenB:write,tokenC:admin'
    - OPENCLAW_MEM_GATEWAY_TOKEN='one-token' (admin role)
    """

    out: Dict[str, str] = {}
    for item in str(raw_multi or "").split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            token, role = item.rsplit(":", 1)
        elif "=" in item:
            token, role = item.rsplit("=", 1)
        else:
            token, role = item, "read"
        token = token.strip()
        role = role.strip().lower()
        if token and role in ROLE_RANK:
            out[token] = role
    single = str(raw_single or "").strip()
    if single:
        out[single] = "admin"
    return out


def config_from_env(args: argparse.Namespace) -> GatewayConfig:
    tokens = _parse_tokens(
        os.getenv("OPENCLAW_MEM_GATEWAY_TOKENS"),
        os.getenv("OPENCLAW_MEM_GATEWAY_TOKEN"),
    )
    allow_unauth = bool(args.allow_unauthenticated) or _truthy(os.getenv("OPENCLAW_MEM_GATEWAY_ALLOW_UNAUTHENTICATED"))
    if not tokens and not allow_unauth:
        raise SystemExit(
            "refusing to start without auth: set OPENCLAW_MEM_GATEWAY_TOKEN "
            "or OPENCLAW_MEM_GATEWAY_TOKENS, or pass --allow-unauthenticated for local dev only"
        )
    weak = [role for token, role in tokens.items() if len(token) < MIN_TOKEN_CHARS]
    if weak and not allow_unauth:
        raise SystemExit(f"refusing weak gateway token: minimum {MIN_TOKEN_CHARS} characters")
    return GatewayConfig(
        db=args.db or os.getenv("OPENCLAW_MEM_DB"),
        workspace=args.workspace or os.getenv("OPENCLAW_MEM_WORKSPACE"),
        tokens=tokens,
        allow_unauthenticated=allow_unauth,
        allow_direct_store=bool(args.allow_direct_store) or _truthy(os.getenv("OPENCLAW_MEM_GATEWAY_ALLOW_DIRECT_STORE")),
        max_body_bytes=int(args.max_body_bytes),
        cli_timeout_sec=float(args.cli_timeout_sec),
        export_root=args.export_root or os.getenv("OPENCLAW_MEM_GATEWAY_EXPORT_ROOT") or DEFAULT_EXPORT_ROOT,
        audit_log=args.audit_log or os.getenv("OPENCLAW_MEM_GATEWAY_AUDIT_LOG"),
        audit_max_bytes=int(os.getenv("OPENCLAW_MEM_GATEWAY_AUDIT_MAX_BYTES", str(DEFAULT_AUDIT_MAX_BYTES))),
        idempotency_ttl_sec=int(os.getenv("OPENCLAW_MEM_GATEWAY_IDEMPOTENCY_TTL_SEC", str(DEFAULT_IDEMPOTENCY_TTL_SEC))),
    )


def _token_id(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _digest_payload(payload: Mapping[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _coerce_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 500) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _coerce_float(value: Any, *, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _require_text(body: Mapping[str, Any], key: str, *, max_chars: int = 12000) -> str:
    value = str(body.get(key) or "").strip()
    if not value:
        raise ValueError(f"missing required field: {key}")
    if len(value) > max_chars:
        raise ValueError(f"field too large: {key}")
    return value


def _optional_text(body: Mapping[str, Any], key: str, *, max_chars: int = 12000) -> Optional[str]:
    if key not in body or body.get(key) is None:
        return None
    value = str(body.get(key) or "").strip()
    if not value:
        return None
    if len(value) > max_chars:
        raise ValueError(f"field too large: {key}")
    return value


def _run_cli(config: GatewayConfig, argv: Iterable[str], *, stdin: Optional[str] = None) -> Dict[str, Any]:
    cmd = [sys.executable, "-m", "openclaw_mem", *list(argv)]
    env = os.environ.copy()
    if config.workspace:
        env.setdefault("OPENCLAW_MEM_WORKSPACE", config.workspace)
    proc = subprocess.run(
        cmd,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=config.cli_timeout_sec,
        env=env,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parsed: Any = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = {"text": stdout}
    receipt: Dict[str, Any] = {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "result": parsed,
    }
    if stderr:
        # Never echo CLI stderr to remote clients; it can contain local paths or internals.
        safe_tail = stderr[-2000:].replace("\n", "\\n")
        sys.stderr.write(f"openclaw-mem-gateway cli stderr tail: {safe_tail}\n")
    if proc.returncode != 0:
        raise RuntimeError(json.dumps({"ok": False, "exit_code": proc.returncode}, ensure_ascii=False))
    return receipt


class MemoryGatewayHandler(BaseHTTPRequestHandler):
    server_version = "openclaw-mem-gateway/0.1"

    @property
    def config(self) -> GatewayConfig:
        return getattr(self.server, "gateway_config")  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover - stdlib hook
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def _role_and_token_id(self) -> Tuple[Optional[str], Optional[str]]:
        if self.config.allow_unauthenticated:
            return "admin", "dev-unauthenticated"
        auth = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not auth.startswith(prefix):
            return None, None
        token = auth[len(prefix) :].strip()
        matched_role: Optional[str] = None
        for configured_token, configured_role in self.config.tokens.items():
            if hmac.compare_digest(token, configured_token):
                matched_role = configured_role
        if matched_role is None:
            return None, None
        return matched_role, _token_id(token)

    def _require_role(self, required: str) -> Optional[str]:
        role, _token = self._role_and_token_id()
        if role is None:
            _json_response(self, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "missing_or_invalid_bearer_token"})
            return None
        if ROLE_RANK.get(role, 0) < ROLE_RANK[required]:
            _json_response(self, HTTPStatus.FORBIDDEN, {"ok": False, "error": "insufficient_role", "required": required})
            return None
        return role

    def _read_json_body(self) -> Dict[str, Any]:
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > self.config.max_body_bytes:
            raise ValueError("request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON body: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("JSON body must be an object")
        return parsed

    def _write_audit(self, *, endpoint: str, action: str, body: Mapping[str, Any], ok: bool, result: str) -> None:
        audit_log = self.config.audit_log
        if not audit_log:
            return
        role, token_id = self._role_and_token_id()
        row = {
            "schema": "openclaw-mem.gateway.audit.v1",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "endpoint": endpoint,
            "action": action,
            "role": role,
            "token_id": token_id,
            "payload_sha256": _digest_payload(body),
            "ok": bool(ok),
            "result": result,
        }
        path = Path(audit_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._append_jsonl(path, row)

    def _append_jsonl(self, path: Path, row: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and self.config.audit_max_bytes > 0 and path.stat().st_size > self.config.audit_max_bytes:
            rotated = path.with_suffix(path.suffix + ".1")
            try:
                rotated.unlink()
            except FileNotFoundError:
                pass
            path.rename(rotated)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _resolve_export_to(self, raw: str) -> str:
        root = Path(self.config.export_root).expanduser().resolve()
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError("export path outside configured export root")
        return str(resolved)

    def _idempotency_store_path(self) -> Optional[Path]:
        if not self.config.audit_log:
            return None
        return Path(self.config.audit_log).with_name("idempotency.jsonl")

    def _idempotency_lookup(self, *, endpoint: str, body: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        key = (self.headers.get("Idempotency-Key") or "").strip()
        if not key:
            return None
        if len(key) > 200:
            raise ValueError("Idempotency-Key too large")
        path = self._idempotency_store_path()
        if path is None or not path.exists():
            return None
        _role, token_id = self._role_and_token_id()
        request_id = hashlib.sha256(f"{endpoint}\0{token_id}\0{key}".encode("utf-8")).hexdigest()
        payload_hash = _digest_payload(body)
        now = time.time()
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            try:
                row_ts = float(row.get("created_unix", 0))
            except Exception:
                row_ts = 0.0
            if self.config.idempotency_ttl_sec > 0 and row_ts and now - row_ts > self.config.idempotency_ttl_sec:
                continue
            if row.get("request_id") == request_id:
                if row.get("payload_sha256") != payload_hash:
                    raise ValueError("Idempotency-Key reused with different payload")
                response = row.get("response")
                if isinstance(response, dict):
                    return response
        return None

    def _idempotency_record(self, *, endpoint: str, body: Mapping[str, Any], response: Mapping[str, Any]) -> None:
        key = (self.headers.get("Idempotency-Key") or "").strip()
        if not key:
            return
        path = self._idempotency_store_path()
        if path is None:
            return
        _role, token_id = self._role_and_token_id()
        request_id = hashlib.sha256(f"{endpoint}\0{token_id}\0{key}".encode("utf-8")).hexdigest()
        row = {
            "schema": "openclaw-mem.gateway.idempotency.v1",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "created_unix": time.time(),
            "request_id": request_id,
            "endpoint": endpoint,
            "token_id": token_id,
            "payload_sha256": _digest_payload(body),
            "response": response,
        }
        self._append_jsonl(path, row)

    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/health":
            _json_response(self, HTTPStatus.OK, {"ok": True, "service": "openclaw-mem-gateway"})
            return
        if path == "/v1/status":
            role = self._require_role("read")
            if role is None:
                return
            payload = {
                "ok": True,
                "service": "openclaw-mem-gateway",
                "auth": "enabled" if not self.config.allow_unauthenticated else "disabled-dev",
                "role": role,
                "db_configured": bool(self.config.db),
                "workspace_configured": bool(self.config.workspace),
                "direct_store_enabled": self.config.allow_direct_store,
            }
            _json_response(self, HTTPStatus.OK, payload)
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib method name
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/v1/search":
                self._handle_search()
            elif path == "/v1/pack":
                self._handle_pack()
            elif path == "/v1/episodes/query":
                self._handle_episodes_query()
            elif path == "/v1/episodes/append":
                self._handle_episodes_append()
            elif path == "/v1/store/propose":
                self._handle_store_propose()
            elif path == "/v1/store":
                self._handle_store()
            elif path == "/v1/archive/export-canonical":
                self._handle_archive_export_canonical()
            else:
                _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except ValueError as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except subprocess.TimeoutExpired:
            _json_response(self, HTTPStatus.GATEWAY_TIMEOUT, {"ok": False, "error": "cli_timeout"})
        except RuntimeError:
            _json_response(self, HTTPStatus.BAD_GATEWAY, {"ok": False, "error": "cli_failed"})
        except Exception as exc:  # pragma: no cover - defensive boundary
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": type(exc).__name__})

    def _handle_search(self) -> None:
        if self._require_role("read") is None:
            return
        body = self._read_json_body()
        query = _require_text(body, "query", max_chars=2000)
        limit = _coerce_int(body.get("limit"), default=10, maximum=100)
        argv = ["search", "--limit", str(limit), "--json"]
        if self.config.db:
            argv.extend(["--db", self.config.db])
        argv.extend(["--", query])
        receipt = _run_cli(self.config, argv)
        _json_response(self, HTTPStatus.OK, {"ok": True, "receipt": receipt})

    def _handle_pack(self) -> None:
        if self._require_role("read") is None:
            return
        body = self._read_json_body()
        query = _require_text(body, "query", max_chars=4000)
        argv = [
            "pack",
            "--json",
            "--query",
            query,
            "--limit",
            str(_coerce_int(body.get("limit"), default=12, maximum=50)),
            "--budget-tokens",
            str(_coerce_int(body.get("budget_tokens"), default=1200, maximum=20000)),
        ]
        query_en = _optional_text(body, "query_en", max_chars=4000)
        if query_en:
            argv.extend(["--query-en", query_en])
        graph_scope = _optional_text(body, "graph_scope", max_chars=200)
        if graph_scope:
            argv.extend(["--graph-scope", graph_scope])
        if self.config.db:
            argv.extend(["--db", self.config.db])
        receipt = _run_cli(self.config, argv)
        _json_response(self, HTTPStatus.OK, {"ok": True, "receipt": receipt})

    def _handle_episodes_query(self) -> None:
        if self._require_role("read") is None:
            return
        body = self._read_json_body()
        argv = ["episodes", "query", "--json", "--limit", str(_coerce_int(body.get("limit"), default=50, maximum=500))]
        scope = _optional_text(body, "scope", max_chars=200)
        if scope:
            argv.extend(["--scope", scope])
        elif body.get("global") is True:
            argv.append("--global")
        else:
            raise ValueError("missing required field: scope")
        session_id = _optional_text(body, "session_id", max_chars=500)
        if session_id:
            argv.extend(["--session-id", session_id])
        for typ in body.get("types") or []:
            argv.extend(["--type", str(typ)])
        if body.get("include_payload") is True:
            argv.append("--include-payload")
        if self.config.db:
            argv.extend(["--db", self.config.db])
        receipt = _run_cli(self.config, argv)
        _json_response(self, HTTPStatus.OK, {"ok": True, "receipt": receipt})

    def _handle_episodes_append(self) -> None:
        if self._require_role("write") is None:
            return
        body = self._read_json_body()
        cached = self._idempotency_lookup(endpoint="/v1/episodes/append", body=body)
        if cached is not None:
            _json_response(self, HTTPStatus.OK, cached)
            return
        argv = [
            "episodes",
            "append",
            "--json",
            "--scope",
            _require_text(body, "scope", max_chars=200),
            "--session-id",
            _require_text(body, "session_id", max_chars=500),
            "--agent-id",
            _require_text(body, "agent_id", max_chars=200),
            "--type",
            _require_text(body, "type", max_chars=80),
            "--summary",
            _require_text(body, "summary", max_chars=2000),
        ]
        if "payload" in body:
            argv.extend(["--payload-json", json.dumps(body.get("payload"), ensure_ascii=False)])
        if "refs" in body:
            argv.extend(["--refs-json", json.dumps(body.get("refs"), ensure_ascii=False)])
        if self.config.db:
            argv.extend(["--db", self.config.db])
        receipt = _run_cli(self.config, argv)
        response = {"ok": True, "receipt": receipt}
        self._idempotency_record(endpoint="/v1/episodes/append", body=body, response=response)
        self._write_audit(endpoint="/v1/episodes/append", action="episodes.append", body=body, ok=True, result="ok")
        _json_response(self, HTTPStatus.OK, response)

    def _handle_store_propose(self) -> None:
        if self._require_role("write") is None:
            return
        body = self._read_json_body()
        cached = self._idempotency_lookup(endpoint="/v1/store/propose", body=body)
        if cached is not None:
            _json_response(self, HTTPStatus.OK, cached)
            return
        scope = _require_text(body, "scope", max_chars=200)
        agent_id = _require_text(body, "agent_id", max_chars=200)
        text = _require_text(body, "text", max_chars=8000)
        category = str(body.get("category") or "other").strip().lower()
        if category not in {"fact", "preference", "decision", "entity", "task", "other"}:
            raise ValueError("invalid category")
        detail = {
            "schema": "openclaw-mem.gateway.store-proposal.v0",
            "scope": scope,
            "agent_id": agent_id,
            "category": category,
            "importance": _coerce_float(body.get("importance"), default=0.5),
            "text": text,
            "provenance": body.get("provenance") if isinstance(body.get("provenance"), dict) else {},
            "created_ms": int(time.time() * 1000),
        }
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "kind": "memory.proposal",
            "tool_name": "gateway.store.propose",
            "summary": f"[{scope}] {text[:500]}",
            "detail": detail,
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False) as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            temp_path = fh.name
        try:
            argv = ["ingest", "--file", temp_path, "--json"]
            if self.config.db:
                argv.extend(["--db", self.config.db])
            receipt = _run_cli(self.config, argv)
        finally:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
        response = {"ok": True, "mode": "proposal", "receipt": receipt}
        self._idempotency_record(endpoint="/v1/store/propose", body=body, response=response)
        self._write_audit(endpoint="/v1/store/propose", action="store.propose", body=body, ok=True, result="ok")
        _json_response(self, HTTPStatus.OK, response)

    def _handle_store(self) -> None:
        if self._require_role("admin") is None:
            return
        if not self.config.allow_direct_store:
            _json_response(
                self,
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "direct_store_disabled", "hint": "set OPENCLAW_MEM_GATEWAY_ALLOW_DIRECT_STORE=1"},
            )
            return
        body = self._read_json_body()
        text = _require_text(body, "text", max_chars=8000)
        category = str(body.get("category") or "fact").strip().lower()
        if category not in {"fact", "preference", "decision", "entity", "task", "other"}:
            raise ValueError("invalid category")
        argv = [
            "store",
            text,
            "--category",
            category,
            "--importance",
            str(_coerce_float(body.get("importance"), default=0.6)),
            "--json",
        ]
        text_en = _optional_text(body, "text_en", max_chars=8000)
        if text_en:
            argv.extend(["--text-en", text_en])
        lang = _optional_text(body, "lang", max_chars=20)
        if lang:
            argv.extend(["--lang", lang])
        workspace = _optional_text(body, "workspace", max_chars=2000) or self.config.workspace
        if workspace:
            argv.extend(["--workspace", workspace])
        if self.config.db:
            argv.extend(["--db", self.config.db])
        receipt = _run_cli(self.config, argv)
        self._write_audit(endpoint="/v1/store", action="store.direct", body=body, ok=True, result="ok")
        _json_response(self, HTTPStatus.OK, {"ok": True, "mode": "direct_store", "receipt": receipt})

    def _handle_archive_export_canonical(self) -> None:
        if self._require_role("admin") is None:
            return
        body = self._read_json_body()
        dry_run = body.get("dry_run", True) is not False
        argv = ["capsule", "export-canonical", "--json"]
        if dry_run:
            argv.append("--dry-run")
        to_path = _optional_text(body, "to", max_chars=2000)
        if to_path:
            argv.extend(["--to", self._resolve_export_to(to_path)])
        if self.config.db:
            argv.extend(["--db", self.config.db])
        receipt = _run_cli(self.config, argv)
        self._write_audit(endpoint="/v1/archive/export-canonical", action="archive.export_canonical", body=body, ok=True, result="dry_run" if dry_run else "ok")
        _json_response(self, HTTPStatus.OK, {"ok": True, "dry_run": dry_run, "receipt": receipt})


def build_server(host: str, port: int, config: GatewayConfig) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, int(port)), MemoryGatewayHandler)
    setattr(server, "gateway_config", config)
    return server


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Authenticated HTTP gateway for openclaw-mem")
    parser.add_argument("--host", default=os.getenv("OPENCLAW_MEM_GATEWAY_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("OPENCLAW_MEM_GATEWAY_PORT", str(DEFAULT_PORT))))
    parser.add_argument("--db", default=None, help="SQLite DB path (default: OPENCLAW_MEM_DB / CLI default)")
    parser.add_argument("--workspace", default=None, help="Workspace root for direct store markdown append")
    parser.add_argument("--max-body-bytes", type=int, default=int(os.getenv("OPENCLAW_MEM_GATEWAY_MAX_BODY_BYTES", str(DEFAULT_MAX_BODY_BYTES))))
    parser.add_argument("--cli-timeout-sec", type=float, default=float(os.getenv("OPENCLAW_MEM_GATEWAY_CLI_TIMEOUT_SEC", "45")))
    parser.add_argument("--allow-direct-store", action="store_true", help="Enable admin-only /v1/store durable writes")
    parser.add_argument("--export-root", default=None, help="Allowlisted root for admin canonical exports")
    parser.add_argument("--audit-log", default=None, help="Append-only JSONL audit log for gateway write/admin actions")
    parser.add_argument("--allow-unauthenticated", action="store_true", help="INSECURE local dev only; disables bearer auth")
    args = parser.parse_args(argv)

    config = config_from_env(args)
    if args.host not in {"127.0.0.1", "localhost", "::1"} and config.allow_unauthenticated:
        raise SystemExit("refusing unauthenticated non-local bind")
    server = build_server(args.host, args.port, config)
    print(
        json.dumps(
            {
                "ok": True,
                "service": "openclaw-mem-gateway",
                "bind": f"{args.host}:{args.port}",
                "auth": "enabled" if not config.allow_unauthenticated else "disabled-dev",
                "direct_store_enabled": config.allow_direct_store,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
