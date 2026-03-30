#!/usr/bin/env python3
"""Seal and verify portable governed pack capsules for openclaw-mem.

Thin helper boundary only:
- wraps `openclaw-mem pack --json --trace`
- optionally wraps `openclaw-mem artifact stash`
- writes a portable capsule directory with integrity manifest
- verifies capsule contents by sha256
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_slug(value: str) -> str:
    raw = (value or "capsule").strip()
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in raw)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe or "capsule"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def add_shared_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--db", help="Optional SQLite DB path passed through to openclaw-mem")
    p.add_argument("--query-en", default="", help="Optional English query passed through to pack")
    p.add_argument("--limit", type=int, default=12, help="Pack item limit (default: 12)")
    p.add_argument("--budget-tokens", type=int, default=1200, help="Pack token budget (default: 1200)")
    p.add_argument("--use-graph", choices=["off", "auto", "on"], default="off", help="Graphic Memory posture for pack (default: off)")
    p.add_argument("--graph-scope", default="", help="Optional graph scope hint")
    p.add_argument("--pack-trust-policy", choices=["off", "exclude_quarantined_fail_open"], default="off", help="Pack trust policy (default: off)")
    p.add_argument("--stash-artifact", action="store_true", help="Also stash the full bundle JSON into the artifact sidecar")
    p.add_argument("--gzip-artifact", action="store_true", help="When stashing, gzip the artifact blob")
    p.add_argument("--label", default="capsule", help="Label slug used in the output directory name")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seal and verify portable governed pack capsules")
    sub = p.add_subparsers(dest="command", required=True)

    seal = sub.add_parser("seal", help="Build a capsule directory from openclaw-mem pack")
    seal.add_argument("--query", required=True, help="Pack query text")
    seal.add_argument("--out", required=True, type=Path, help="Output root directory; helper creates a timestamped capsule under it")
    add_shared_args(seal)

    verify = sub.add_parser("verify", help="Verify capsule file presence + sha256 integrity")
    verify.add_argument("capsule", type=Path, help="Path to capsule directory")

    return p.parse_args()


def run_pack(args: argparse.Namespace) -> Dict[str, Any]:
    cmd: List[str] = ["openclaw-mem"]
    if args.db:
        cmd.extend(["--db", args.db])
    cmd.extend(
        [
            "pack",
            "--json",
            "--trace",
            "--query",
            args.query,
            "--limit",
            str(args.limit),
            "--budget-tokens",
            str(args.budget_tokens),
            "--use-graph",
            args.use_graph,
            "--pack-trust-policy",
            args.pack_trust_policy,
        ]
    )
    if args.query_en.strip():
        cmd.extend(["--query-en", args.query_en.strip()])
    if args.graph_scope.strip():
        cmd.extend(["--graph-scope", args.graph_scope.strip()])

    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"pack failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}")
    payload = json.loads(proc.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("pack JSON must be an object")
    return {"command": cmd, "payload": payload}


def run_artifact_stash(bundle_json: str, *, gzip_artifact: bool) -> Dict[str, Any]:
    cmd = ["openclaw-mem", "artifact", "stash", "--json"]
    if gzip_artifact:
        cmd.append("--gzip")
    proc = subprocess.run(cmd, input=bundle_json, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"artifact stash failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}")
    payload = json.loads(proc.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("artifact stash JSON must be an object")
    return {"command": cmd, "payload": payload}


def build_manifest(
    *,
    args: argparse.Namespace,
    final_dir: Path,
    pack_command: List[str],
    payload: Dict[str, Any],
    artifact_receipt: Optional[Dict[str, Any]],
    artifact_cmd: Optional[List[str]],
    file_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    citations = payload.get("citations") if isinstance(payload.get("citations"), list) else []
    return {
        "schema": "openclaw-mem.pack-capsule.v1",
        "capsule_id": final_dir.name,
        "created_at": utc_now(),
        "label": args.label,
        "query": args.query,
        "query_en": args.query_en or None,
        "db": args.db,
        "pack_config": {
            "limit": args.limit,
            "budget_tokens": args.budget_tokens,
            "use_graph": args.use_graph,
            "graph_scope": args.graph_scope or None,
            "pack_trust_policy": args.pack_trust_policy,
        },
        "files": file_entries,
        "stats": {
            "items": len(items),
            "citations": len(citations),
            "bundle_text_chars": len(str(payload.get("bundle_text") or "")),
        },
        "artifact": artifact_receipt,
        "receipt": {
            "pack_command": pack_command,
            "artifact_stash_command": artifact_cmd,
            "rollback": [
                "delete the capsule directory if you no longer want the portable artifact",
                "if artifact stash was used, keep the sidecar artifact as historical receipt or prune it manually out-of-band",
            ],
            "topology": "unchanged",
        },
    }


def cmd_seal(args: argparse.Namespace) -> int:
    out_root = args.out.expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    capsule_name = f"{stamp()}_{safe_slug(args.label)}"
    final_dir = out_root / capsule_name
    tmp_dir = out_root / f".{capsule_name}.tmp"

    if final_dir.exists() or tmp_dir.exists():
        raise RuntimeError(f"capsule path already exists: {final_dir}")

    pack = run_pack(args)
    payload = pack["payload"]

    try:
        tmp_dir.mkdir(parents=False, exist_ok=False)

        bundle_json_path = tmp_dir / "bundle.json"
        bundle_text_path = tmp_dir / "bundle_text.md"
        trace_path = tmp_dir / "trace.json"
        artifact_receipt_path = tmp_dir / "artifact_stash.json"
        manifest_path = tmp_dir / "manifest.json"

        write_json(bundle_json_path, payload)
        bundle_text_path.write_text(str(payload.get("bundle_text") or "") + "\n", encoding="utf-8")

        trace_payload = payload.get("trace")
        if isinstance(trace_payload, dict):
            write_json(trace_path, trace_payload)

        artifact_receipt = None
        artifact_cmd = None
        if args.stash_artifact:
            artifact = run_artifact_stash(bundle_json_path.read_text(encoding="utf-8"), gzip_artifact=args.gzip_artifact)
            artifact_receipt = artifact["payload"]
            artifact_cmd = artifact["command"]
            write_json(artifact_receipt_path, artifact_receipt)

        file_entries: List[Dict[str, Any]] = []
        for path in [bundle_json_path, bundle_text_path, trace_path, artifact_receipt_path]:
            if not path.exists():
                continue
            file_entries.append(
                {
                    "name": path.name,
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )

        manifest = build_manifest(
            args=args,
            final_dir=final_dir,
            pack_command=pack["command"],
            payload=payload,
            artifact_receipt=artifact_receipt,
            artifact_cmd=artifact_cmd,
            file_entries=file_entries,
        )
        write_json(manifest_path, manifest)

        tmp_dir.rename(final_dir)
    except Exception:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        raise

    summary = {
        "schema": "openclaw-mem.pack-capsule.summary.v1",
        "ok": True,
        "command": "seal",
        "capsule_dir": str(final_dir),
        "manifest": str(final_dir / "manifest.json"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    capsule_dir = args.capsule.expanduser().resolve()
    manifest_path = capsule_dir / "manifest.json"
    manifest = load_json(manifest_path)
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise RuntimeError("manifest files list is missing or empty")

    checks: List[Dict[str, Any]] = []
    ok = True
    for entry in files:
        if not isinstance(entry, dict):
            raise RuntimeError("manifest file entry must be an object")
        name = str(entry.get("name") or "").strip()
        expected_sha = str(entry.get("sha256") or "").strip()
        expected_bytes = int(entry.get("bytes") or 0)
        if not name or not expected_sha:
            raise RuntimeError("manifest file entry missing name/sha256")
        path = capsule_dir / name
        exists = path.exists() and path.is_file()
        actual_sha = sha256_file(path) if exists else None
        actual_bytes = path.stat().st_size if exists else None
        match = bool(exists and actual_sha == expected_sha and actual_bytes == expected_bytes)
        ok = ok and match
        checks.append(
            {
                "name": name,
                "exists": exists,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "expected_bytes": expected_bytes,
                "actual_bytes": actual_bytes,
                "ok": match,
            }
        )

    summary = {
        "schema": "openclaw-mem.pack-capsule.verify.v1",
        "ok": ok,
        "command": "verify",
        "capsule_dir": str(capsule_dir),
        "checks": checks,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main() -> int:
    args = parse_args()
    if args.command == "seal":
        return cmd_seal(args)
    if args.command == "verify":
        return cmd_verify(args)
    raise RuntimeError(f"unknown command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
