#!/usr/bin/env python3
"""Portable governed pack capsule helpers.

This module powers both:
- first-class `openclaw-mem capsule ...` subcommands
- compatibility wrapper `openclaw-mem-pack-capsule ...` and tools/pack_capsule.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
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


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def normalize_text(value: Any) -> str:
    text = str(value or "")
    return " ".join(text.split()).strip()


def item_signature(kind: Any, summary: Any) -> str:
    return f"{normalize_text(kind).lower()}\t{normalize_text(summary)}"


def default_db_path() -> str:
    env_path = (os.environ.get("OPENCLAW_MEM_DB") or "").strip()
    if env_path:
        return str(Path(env_path).expanduser())
    return str(Path("~/.openclaw/memory/openclaw-mem.sqlite").expanduser())


def _openclaw_mem_cmd_prefix() -> List[str]:
    return [sys.executable, "-m", "openclaw_mem"]


def _run_json_command(cmd: List[str], *, stdin_text: Optional[str] = None) -> Dict[str, Any]:
    proc = subprocess.run(
        cmd,
        input=stdin_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(cmd)} :: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not return JSON: {' '.join(cmd)}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"command JSON must be an object: {' '.join(cmd)}")
    return payload


def add_shared_seal_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--db", help="Optional SQLite DB path passed through to openclaw-mem")
    p.add_argument("--query-en", default="", help="Optional English query passed through to pack")
    p.add_argument("--limit", type=int, default=12, help="Pack item limit (default: 12)")
    p.add_argument("--budget-tokens", type=int, default=1200, help="Pack token budget (default: 1200)")
    p.add_argument("--use-graph", choices=["off", "auto", "on"], default="off", help="Graphic Memory posture for pack (default: off)")
    p.add_argument("--graph-scope", default="", help="Optional graph scope hint")
    p.add_argument(
        "--pack-trust-policy",
        choices=["off", "exclude_quarantined_fail_open"],
        default="off",
        help="Pack trust policy (default: off)",
    )
    p.add_argument("--stash-artifact", action="store_true", help="Also stash the full bundle JSON into the artifact sidecar")
    p.add_argument("--gzip-artifact", action="store_true", help="When stashing, gzip the artifact blob")
    p.add_argument("--label", default="capsule", help="Label slug used in the output directory name")


def _add_capsule_subcommands(sub: argparse._SubParsersAction, *, for_integrated_cli: bool) -> None:
    seal = sub.add_parser("seal", help="Build a capsule directory from openclaw-mem pack")
    seal.add_argument("--query", required=True, help="Pack query text")
    seal.add_argument("--out", required=True, type=Path, help="Output root directory; creates a timestamped capsule under it")
    add_shared_seal_args(seal)
    seal.set_defaults(capsule_handler=cmd_seal)

    verify = sub.add_parser("verify", help="Verify capsule file presence + sha256 integrity")
    verify.add_argument("capsule", type=Path, help="Path to capsule directory")
    verify.set_defaults(capsule_handler=cmd_verify)

    inspect = sub.add_parser("inspect", help="Inspect capsule metadata and contents without touching any store")
    inspect.add_argument("capsule", type=Path, help="Path to capsule directory")
    inspect.add_argument("--json", action="store_true", help="Emit structured JSON instead of markdown-like text")
    inspect.set_defaults(capsule_handler=cmd_inspect)

    diff = sub.add_parser("diff", help="Compare capsule items against a target governed store (read-only)")
    diff.add_argument("capsule", type=Path, help="Path to capsule directory")
    diff.add_argument("--db", help="Target SQLite DB path (default: OPENCLAW_MEM_DB or host default)")
    diff.add_argument("--write-receipt", action="store_true", help="Write diff.latest.json into the capsule directory")
    diff.add_argument("--write-report-md", action="store_true", help="Write diff.latest.md into the capsule directory")
    diff.set_defaults(capsule_handler=cmd_diff)

    export_canonical = sub.add_parser(
        "export-canonical",
        help="Manifest-only canonical export contract preview (restore not supported yet)",
    )
    export_canonical.add_argument(
        "--db",
        help="SQLite DB path to inspect (default: inherited --db / OPENCLAW_MEM_DB / host default)",
    )
    export_canonical.add_argument(
        "--dry-run",
        action="store_true",
        help="Required in this slice. Emits manifest contract preview only; writes nothing.",
    )
    export_canonical.add_argument(
        "--to",
        help="Planned output path for a future archive/manifest write (recorded in dry-run receipt only)",
    )
    export_canonical.add_argument(
        "--json",
        action="store_true",
        help="Structured JSON output (for machine ingestion)",
    )
    export_canonical.set_defaults(capsule_handler=cmd_export_canonical)

    if for_integrated_cli:
        # Keep the parent command routed through cmd_capsule for thin parser edge in openclaw_mem.cli.
        pass


def add_capsule_parser_to_cli(sub: argparse._SubParsersAction) -> None:
    """Attach `capsule` command family under `openclaw-mem` parser."""

    sp = sub.add_parser(
        "capsule",
        help="Portable governed pack capsule helpers (seal/inspect/verify/diff/export-canonical)",
    )
    csub = sp.add_subparsers(dest="capsule_cmd", required=True)
    _add_capsule_subcommands(csub, for_integrated_cli=True)
    sp.set_defaults(func=cmd_capsule)


def build_standalone_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openclaw-mem-pack-capsule",
        description="Seal and verify portable governed pack capsules",
    )
    sub = p.add_subparsers(dest="command", required=True)
    _add_capsule_subcommands(sub, for_integrated_cli=False)
    return p


def run_pack(args: argparse.Namespace) -> Dict[str, Any]:
    cmd: List[str] = [*_openclaw_mem_cmd_prefix()]
    if getattr(args, "db", None):
        cmd.extend(["--db", str(args.db)])
    cmd.extend(
        [
            "pack",
            "--json",
            "--trace",
            "--query",
            str(args.query),
            "--limit",
            str(args.limit),
            "--budget-tokens",
            str(args.budget_tokens),
            "--use-graph",
            str(args.use_graph),
            "--pack-trust-policy",
            str(args.pack_trust_policy),
        ]
    )
    if str(getattr(args, "query_en", "") or "").strip():
        cmd.extend(["--query-en", str(args.query_en).strip()])
    if str(getattr(args, "graph_scope", "") or "").strip():
        cmd.extend(["--graph-scope", str(args.graph_scope).strip()])

    payload = _run_json_command(cmd)
    return {"command": cmd, "payload": payload}


def run_artifact_stash(bundle_json: str, *, gzip_artifact: bool, db_path: Optional[str]) -> Dict[str, Any]:
    cmd = [*_openclaw_mem_cmd_prefix()]
    if db_path:
        cmd.extend(["--db", db_path])
    cmd.extend(["artifact", "stash", "--json"])
    if gzip_artifact:
        cmd.append("--gzip")
    payload = _run_json_command(cmd, stdin_text=bundle_json)
    return {"command": cmd, "payload": payload}


def file_set_integrity_hash(file_entries: List[Dict[str, Any]]) -> str:
    lines = []
    for entry in sorted(file_entries, key=lambda item: str(item.get("name") or "")):
        lines.append(f"{entry.get('name')}\t{entry.get('sha256')}\t{entry.get('bytes')}")
    return "sha256:" + sha256_text("\n".join(lines))


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
    created_at = utc_now()
    return {
        "schema": "openclaw-mem.pack-capsule.v1",
        "capsule_version": 0,
        "capsule_id": final_dir.name,
        "created_at": created_at,
        "exported_at": created_at,
        "label": args.label,
        "query": args.query,
        "query_en": args.query_en or None,
        "db": getattr(args, "db", None),
        "pack_config": {
            "limit": args.limit,
            "budget_tokens": args.budget_tokens,
            "use_graph": args.use_graph,
            "graph_scope": args.graph_scope or None,
            "pack_trust_policy": args.pack_trust_policy,
        },
        "files": file_entries,
        "integrity_hash": file_set_integrity_hash(file_entries),
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
            artifact = run_artifact_stash(
                bundle_json_path.read_text(encoding="utf-8"),
                gzip_artifact=args.gzip_artifact,
                db_path=getattr(args, "db", None),
            )
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


def verify_capsule(capsule_dir: Path) -> Dict[str, Any]:
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
    return {
        "schema": "openclaw-mem.pack-capsule.verify.v1",
        "ok": ok,
        "command": "verify",
        "capsule_dir": str(capsule_dir),
        "checks": checks,
    }


def render_inspect_report(summary: Dict[str, Any]) -> str:
    manifest = summary.get("manifest") if isinstance(summary.get("manifest"), dict) else {}
    stats = manifest.get("stats") if isinstance(manifest.get("stats"), dict) else {}
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    preview = str(summary.get("bundle_text_preview") or "")

    lines: List[str] = []
    lines.append("# Pack Capsule Inspect")
    lines.append("")
    lines.append(f"- Capsule: `{summary.get('capsule_dir')}`")
    lines.append(f"- Schema: `{manifest.get('schema')}`")
    lines.append(f"- Capsule version: `{manifest.get('capsule_version')}`")
    lines.append(f"- Exported at: `{manifest.get('exported_at')}`")
    lines.append(f"- Integrity hash: `{manifest.get('integrity_hash')}`")
    lines.append(f"- Restorable: `{summary.get('restorable')}`")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- Items: {stats.get('items', 0)}")
    lines.append(f"- Citations: {stats.get('citations', 0)}")
    lines.append(f"- Bundle chars: {stats.get('bundle_text_chars', 0)}")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    for entry in files:
        if isinstance(entry, dict):
            lines.append(f"- `{entry.get('name')}` bytes={entry.get('bytes')} sha256={entry.get('sha256')}")
    if not files:
        lines.append("- none")
    lines.append("")
    lines.append("## Bundle preview")
    lines.append("")
    lines.append(preview if preview else "- empty")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Current pack capsules are portable audit artifacts, not canonical restore artifacts.")
    lines.append("- A future restore CLI requires a stronger artifact contract with observation-level detail/provenance.")
    return "\n".join(lines) + "\n"


def render_diff_report(summary: Dict[str, Any]) -> str:
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
    receipt = summary.get("receipt") if isinstance(summary.get("receipt"), dict) else {}
    present = summary.get("present") if isinstance(summary.get("present"), list) else []
    missing = summary.get("missing") if isinstance(summary.get("missing"), list) else []

    lines: List[str] = []
    lines.append("# Pack Capsule Diff Report")
    lines.append("")
    lines.append(f"- Capsule: `{summary.get('capsule_dir')}`")
    lines.append(f"- Target DB: `{summary.get('db')}`")
    lines.append(f"- Match rule: {receipt.get('match_rule')}")
    lines.append(f"- Target store status: `{receipt.get('target_store_table_status')}`")
    lines.append(f"- Mutation: `{receipt.get('mutation')}`")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- Capsule items: {counts.get('capsule_items', 0)}")
    lines.append(f"- Store observations: {counts.get('store_observations', 0)}")
    lines.append(f"- Present: {counts.get('present', 0)}")
    lines.append(f"- Missing: {counts.get('missing', 0)}")
    lines.append("")

    lines.append("## Present")
    lines.append("")
    if present:
        for item in present:
            lines.append(f"- [{item.get('recordRef')}] `{item.get('kind')}` {item.get('summary')}")
            matches = item.get("matches") if isinstance(item.get("matches"), list) else []
            for match in matches[:5]:
                if isinstance(match, dict):
                    lines.append(f"  - match obs:{match.get('id')} ts={match.get('ts')} :: {match.get('summary')}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Missing")
    lines.append("")
    if missing:
        for item in missing:
            lines.append(f"- [{item.get('recordRef')}] `{item.get('kind')}` {item.get('summary')}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This is a read-only audit report. It does not mutate the target store.")
    lines.append("- A future restore/import line must prove canonical observation fidelity first; this report does not claim restore safety.")
    return "\n".join(lines) + "\n"


def cmd_inspect(args: argparse.Namespace) -> int:
    capsule_dir = args.capsule.expanduser().resolve()
    verify_summary = verify_capsule(capsule_dir)
    if not bool(verify_summary.get("ok")):
        print(json.dumps(verify_summary, ensure_ascii=False, indent=2))
        return 1

    manifest = load_json(capsule_dir / "manifest.json")
    bundle = load_json(capsule_dir / "bundle.json")
    out = {
        "schema": "openclaw-mem.pack-capsule.inspect.v1",
        "ok": True,
        "command": "inspect",
        "capsule_dir": str(capsule_dir),
        "verify": verify_summary,
        "manifest": manifest,
        "bundle_text_preview": str(bundle.get("bundle_text") or "")[:600],
        "restorable": False,
        "reason": "pack capsule v0 preserves pack-level selection output, not canonical observation-level restore detail",
    }
    if getattr(args, "json", False):
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(render_inspect_report(out), end="")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    capsule_dir = args.capsule.expanduser().resolve()
    summary = verify_capsule(capsule_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if bool(summary.get("ok")) else 1


def cmd_diff(args: argparse.Namespace) -> int:
    capsule_dir = args.capsule.expanduser().resolve()
    verify_summary = verify_capsule(capsule_dir)
    if not bool(verify_summary.get("ok")):
        print(json.dumps(verify_summary, ensure_ascii=False, indent=2))
        return 1

    bundle = load_json(capsule_dir / "bundle.json")
    items_raw = bundle.get("items")
    items = items_raw if isinstance(items_raw, list) else []

    db_path = str(Path(args.db).expanduser()) if getattr(args, "db", None) else default_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    table_status = "ok"
    try:
        try:
            rows = conn.execute("SELECT id, kind, summary, ts FROM observations").fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                rows = []
                table_status = "missing_observations_table"
            else:
                raise
    finally:
        conn.close()

    store_index: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        sig = item_signature(row["kind"], row["summary"])
        store_index.setdefault(sig, []).append(
            {
                "id": int(row["id"]),
                "kind": row["kind"],
                "summary": row["summary"],
                "ts": row["ts"],
            }
        )

    present: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sig = item_signature(item.get("kind"), item.get("summary"))
        record = {
            "recordRef": item.get("recordRef"),
            "kind": item.get("kind"),
            "summary": item.get("summary"),
            "signature": sig,
        }
        matches = store_index.get(sig) or []
        if matches:
            record["matches"] = matches[:20]
            present.append(record)
        else:
            missing.append(record)

    summary = {
        "schema": "openclaw-mem.pack-capsule.diff.v1",
        "ok": True,
        "command": "diff",
        "capsule_dir": str(capsule_dir),
        "db": db_path,
        "verify": verify_summary,
        "counts": {
            "capsule_items": len([item for item in items if isinstance(item, dict)]),
            "store_observations": len(rows),
            "present": len(present),
            "missing": len(missing),
        },
        "present": present,
        "missing": missing,
        "receipt": {
            "match_rule": "normalized kind + summary exact match",
            "mutation": "none",
            "topology": "unchanged",
            "target_store_table_status": table_status,
        },
    }
    if getattr(args, "write_receipt", False):
        write_json(capsule_dir / "diff.latest.json", summary)
        summary["diff_receipt_path"] = str(capsule_dir / "diff.latest.json")
    if getattr(args, "write_report_md", False):
        report_path = capsule_dir / "diff.latest.md"
        report_path.write_text(render_diff_report(summary), encoding="utf-8")
        summary["diff_report_path"] = str(report_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _canonical_manifest_preview(db_path: str, *, planned_path: Optional[str]) -> Dict[str, Any]:
    table_status = "ok"
    observations_count = 0
    oldest_ts = None
    newest_ts = None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt, MIN(ts) AS oldest_ts, MAX(ts) AS newest_ts FROM observations"
            ).fetchone()
            observations_count = int(row["cnt"] if row else 0)
            oldest_ts = row["oldest_ts"] if row else None
            newest_ts = row["newest_ts"] if row else None
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                table_status = "missing_observations_table"
            else:
                raise
    finally:
        conn.close()

    return {
        "schema": "openclaw-mem.pack-capsule.canonical-manifest.v1",
        "generated_at": utc_now(),
        "contract_mode": "manifest_only_dry_run",
        "source": {
            "db": db_path,
            "table_status": table_status,
            "observations_count": observations_count,
            "oldest_ts": oldest_ts,
            "newest_ts": newest_ts,
        },
        "planned_output": {
            "path": planned_path,
            "archive_written": False,
            "manifest_written": False,
        },
        "restore": {
            "supported": False,
            "reason": "restore/import is not implemented yet for capsule canonical lane",
        },
    }


def _render_export_canonical_text(summary: Dict[str, Any]) -> str:
    manifest = summary.get("manifest") if isinstance(summary.get("manifest"), dict) else {}
    src = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    restore = manifest.get("restore") if isinstance(manifest.get("restore"), dict) else {}
    lines = [
        "# Capsule Export Canonical (dry-run)",
        "",
        f"- OK: {summary.get('ok')}",
        f"- DB: {summary.get('db')}",
        f"- Table status: {src.get('table_status')}",
        f"- Observations: {src.get('observations_count')}",
        f"- Planned output path: {summary.get('planned_output') or '-'}",
        "",
        "## Restore status",
        "",
        f"- Supported: {restore.get('supported')}",
        f"- Reason: {restore.get('reason')}",
        "",
        "## Notes",
        "",
        "- This command currently emits a manifest contract preview only.",
        "- Archive writing is intentionally not implemented in this slice.",
    ]
    return "\n".join(lines) + "\n"


def cmd_export_canonical(args: argparse.Namespace) -> int:
    dry_run = bool(getattr(args, "dry_run", False))
    db_path = str(Path(getattr(args, "db", None) or default_db_path()).expanduser())
    planned_path = str(Path(args.to).expanduser()) if getattr(args, "to", None) else None

    if not dry_run:
        out = {
            "schema": "openclaw-mem.pack-capsule.export-canonical.v1",
            "ok": False,
            "command": "export-canonical",
            "error": "dry_run_required",
            "message": "Only --dry-run is supported in this slice; archive writing is not implemented.",
            "restore_supported": False,
        }
        if bool(getattr(args, "json", False)):
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print("ERROR: Only --dry-run is supported in this slice; archive writing is not implemented.", file=sys.stderr)
        return 2

    manifest = _canonical_manifest_preview(db_path, planned_path=planned_path)
    out = {
        "schema": "openclaw-mem.pack-capsule.export-canonical.v1",
        "ok": True,
        "command": "export-canonical",
        "dry_run": True,
        "db": db_path,
        "planned_output": planned_path,
        "manifest": manifest,
        "restore_supported": False,
        "restore_message": "restore/import is not implemented yet",
        "archive_written": False,
        "topology": "unchanged",
    }
    if bool(getattr(args, "json", False)):
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(_render_export_canonical_text(out), end="")
    return 0


def cmd_capsule(_conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    handler = getattr(args, "capsule_handler", None)
    if handler is None:
        raise RuntimeError("capsule subcommand handler missing")
    rc = int(handler(args))
    if rc != 0:
        raise SystemExit(rc)


def standalone_main(argv: Optional[List[str]] = None) -> int:
    parser = build_standalone_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "capsule_handler", None)
    if handler is None:
        raise RuntimeError("capsule command handler missing")
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(standalone_main())
