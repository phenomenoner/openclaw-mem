from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_HANDLE_RE = re.compile(r"^ocm_artifact:v1:sha256:([0-9a-f]{64})$")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_state_dir() -> Path:
    override = (os.getenv("OPENCLAW_STATE_DIR") or "").strip()
    if override:
        return Path(os.path.abspath(os.path.expanduser(override)))
    return Path(os.path.abspath(os.path.expanduser("~/.openclaw")))


def resolve_artifacts_root(root: Optional[Path] = None) -> Path:
    if root is not None:
        return Path(root)
    return _resolve_state_dir() / "memory" / "openclaw-mem" / "artifacts"


def parse_artifact_handle(handle: str) -> str:
    if not isinstance(handle, str):
        raise ValueError("artifact handle must be a string")

    # Strict ASCII only parser.
    try:
        handle.encode("ascii")
    except UnicodeEncodeError as e:
        raise ValueError("artifact handle must be ASCII") from e

    m = _HANDLE_RE.fullmatch(handle)
    if not m:
        raise ValueError("invalid artifact handle format")
    return m.group(1)


def make_artifact_handle(sha256_hex: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", str(sha256_hex or "")):
        raise ValueError("sha256 must be lowercase 64-hex")
    return f"ocm_artifact:v1:sha256:{sha256_hex}"


def _hash_dirs(sha256_hex: str) -> Tuple[str, str]:
    return sha256_hex[:2], sha256_hex[2:4]


def _blob_and_meta_paths(root: Path, sha256_hex: str) -> Tuple[Path, Path, Path]:
    a, b = _hash_dirs(sha256_hex)
    blob_dir = root / "blobs" / "sha256" / a / b
    meta_dir = root / "meta" / "sha256" / a / b
    meta_path = meta_dir / f"{sha256_hex}.json"
    return blob_dir, meta_dir, meta_path


def _secure_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _read_meta(meta_path: Path) -> Dict[str, Any]:
    raw = meta_path.read_text(encoding="utf-8")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("artifact metadata must be a JSON object")
    return obj


def _locate_blob(root: Path, sha256_hex: str, meta: Optional[Dict[str, Any]] = None) -> Tuple[Path, bool]:
    blob_dir, _meta_dir, _meta_path = _blob_and_meta_paths(root, sha256_hex)

    rel = None
    if isinstance(meta, dict):
        rel = meta.get("blob")

    if isinstance(rel, str) and rel.strip():
        p = (root / rel).resolve()
        if p.exists():
            return p, p.suffix == ".gz"

    txt = blob_dir / f"{sha256_hex}.txt"
    gz = blob_dir / f"{sha256_hex}.txt.gz"
    if txt.exists():
        return txt, False
    if gz.exists():
        return gz, True

    raise FileNotFoundError(f"artifact blob not found for sha256={sha256_hex}")


def stash_artifact(
    data: bytes,
    *,
    root: Optional[Path] = None,
    kind: str = "tool_output",
    meta: Optional[Dict[str, Any]] = None,
    compress: bool = False,
) -> Dict[str, Any]:
    raw = data if isinstance(data, (bytes, bytearray)) else bytes(data)
    sha256_hex = hashlib.sha256(raw).hexdigest()
    handle = make_artifact_handle(sha256_hex)

    artifacts_root = resolve_artifacts_root(root)
    blob_dir, _meta_dir, meta_path = _blob_and_meta_paths(artifacts_root, sha256_hex)

    existing_meta: Optional[Dict[str, Any]] = None
    if meta_path.exists():
        try:
            existing_meta = _read_meta(meta_path)
        except Exception:
            existing_meta = None

    if existing_meta is not None:
        try:
            _locate_blob(artifacts_root, sha256_hex, existing_meta)
            return {
                "schema": "openclaw-mem.artifact.stash.v1",
                "handle": handle,
                "sha256": sha256_hex,
                "bytes": int(existing_meta.get("bytes") or len(raw)),
                "createdAt": existing_meta.get("createdAt") or _utcnow_iso(),
                "kind": existing_meta.get("kind") or "tool_output",
                "meta": existing_meta.get("meta") if isinstance(existing_meta.get("meta"), dict) else {},
            }
        except Exception:
            pass

    blob_is_gzip = bool(compress)
    blob_name = f"{sha256_hex}.txt.gz" if blob_is_gzip else f"{sha256_hex}.txt"
    blob_path = blob_dir / blob_name

    blob_bytes = gzip.compress(raw, mtime=0) if blob_is_gzip else bytes(raw)
    _secure_write_bytes(blob_path, blob_bytes)

    created_at = _utcnow_iso()
    meta_payload = {
        "schema": "openclaw-mem.artifact.meta.v1",
        "handle": handle,
        "sha256": sha256_hex,
        "bytes": len(raw),
        "storedBytes": len(blob_bytes),
        "compression": "gzip" if blob_is_gzip else "none",
        "blob": str(blob_path.relative_to(artifacts_root).as_posix()),
        "createdAt": created_at,
        "kind": str(kind or "tool_output"),
        "meta": meta if isinstance(meta, dict) else {},
    }
    _secure_write_bytes(meta_path, (json.dumps(meta_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    return {
        "schema": "openclaw-mem.artifact.stash.v1",
        "handle": handle,
        "sha256": sha256_hex,
        "bytes": len(raw),
        "createdAt": created_at,
        "kind": meta_payload["kind"],
        "meta": meta_payload["meta"],
    }


def _read_artifact_bytes(*, handle: str, root: Optional[Path] = None) -> Tuple[bytes, Dict[str, Any], Path]:
    sha256_hex = parse_artifact_handle(handle)
    artifacts_root = resolve_artifacts_root(root)
    _blob_dir, _meta_dir, meta_path = _blob_and_meta_paths(artifacts_root, sha256_hex)
    if not meta_path.exists():
        raise FileNotFoundError(f"artifact metadata not found for sha256={sha256_hex}")

    meta = _read_meta(meta_path)
    blob_path, is_gzip = _locate_blob(artifacts_root, sha256_hex, meta)

    data = blob_path.read_bytes()
    if is_gzip:
        data = gzip.decompress(data)

    return data, meta, blob_path


def _bounded_text(text: str, *, mode: str, max_chars: int) -> str:
    cap = max(1, int(max_chars))
    if len(text) <= cap:
        return text

    if mode == "head":
        return text[:cap]
    if mode == "tail":
        return text[-cap:]

    marker = "\n...\n"
    if cap <= len(marker) + 2:
        return text[:cap]

    head = (cap - len(marker)) // 2
    tail = cap - len(marker) - head
    return text[:head] + marker + text[-tail:]


def fetch_artifact(
    handle: str,
    *,
    mode: str = "headtail",
    max_chars: int = 8000,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    if mode not in {"headtail", "head", "tail"}:
        raise ValueError("mode must be one of: headtail, head, tail")

    data, _meta, _blob_path = _read_artifact_bytes(handle=handle, root=root)
    text = data.decode("utf-8", errors="replace")
    bounded = _bounded_text(text, mode=mode, max_chars=max_chars)

    return {
        "schema": "openclaw-mem.artifact.fetch.v1",
        "handle": handle,
        "selector": {
            "mode": mode,
            "maxChars": max(1, int(max_chars)),
        },
        "text": bounded,
    }


def peek_artifact(
    handle: str,
    *,
    preview_chars: int = 240,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    data, meta, blob_path = _read_artifact_bytes(handle=handle, root=root)
    text = data.decode("utf-8", errors="replace")
    preview = _bounded_text(text, mode="headtail", max_chars=max(1, int(preview_chars)))

    return {
        "schema": "openclaw-mem.artifact.peek.v1",
        "handle": handle,
        "sha256": str(meta.get("sha256") or parse_artifact_handle(handle)),
        "bytes": int(meta.get("bytes") or len(data)),
        "createdAt": str(meta.get("createdAt") or _utcnow_iso()),
        "kind": str(meta.get("kind") or "tool_output"),
        "compression": str(meta.get("compression") or ("gzip" if blob_path.suffix == ".gz" else "none")),
        "meta": meta.get("meta") if isinstance(meta.get("meta"), dict) else {},
        "preview": preview,
        "previewChars": max(1, int(preview_chars)),
    }
