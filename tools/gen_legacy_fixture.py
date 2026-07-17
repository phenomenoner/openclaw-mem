#!/usr/bin/env python3
"""Generate deterministic legacy SQLite fixtures with historical releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


TAGS = ("v1.9.26", "v1.9.31")
FIXED_CREATED_AT = "2026-01-15T00:00:00+00:00"
GOLDEN_QUERIES = (
    {"lane": "observations", "query": "legacy anchor", "expected_ids": list(range(1, 9))},
    {"lane": "observations", "query": "舊版錨點", "expected_ids": list(range(9, 17))},
    {"lane": "observations", "query": "translated", "expected_ids": list(range(9, 17))},
    {"lane": "observations", "query": "legacy anchor memory 3", "expected_ids": [4]},
    {"lane": "episodes", "query": "bounded", "expected_ids": list(range(1, 5))},
)


def _run(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {argv!r}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _observation_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(8):
        rows.append(
            {
                "ts": f"2026-01-{index + 1:02d}T00:00:00Z",
                "kind": "fact" if index % 2 == 0 else "preference",
                "summary": f"legacy anchor memory {index}",
                "summary_en": f"legacy anchor memory {index}",
                "lang": "en",
                "tool_name": "legacy-fixture",
                "detail": {"scope": "fixture", "ordinal": index},
            }
        )
    for index in range(8):
        rows.append(
            {
                "ts": f"2026-02-{index + 1:02d}T00:00:00Z",
                "kind": "decision" if index % 2 == 0 else "task",
                "summary": f"舊版錨點 記憶 {index}",
                "text_en": f"legacy translated memory {index}",
                "lang": "zh",
                "tool_name": "legacy-fixture",
                "detail": {"scope": "fixture", "ordinal": index + 8},
            }
        )
    return rows


def _episodic_rows() -> list[dict[str, Any]]:
    types = ("conversation.user", "conversation.assistant", "ops.decision", "tool.result")
    return [
        {
            "schema": "openclaw-mem.episodes.spool.v0",
            "event_id": f"legacy-event-{index + 1}",
            "ts_ms": 1_768_435_200_000 + index,
            "scope": "fixture",
            "session_id": "legacy-session",
            "agent_id": "fixture-agent",
            "type": event_type,
            "summary": f"legacy episode {index + 1}",
            "payload": {"ordinal": index + 1, "note": "bounded fixture payload"},
            "refs": {"recordRef": f"obs:{index + 1}"},
        }
        for index, event_type in enumerate(types)
    ]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _normalize_fixture(path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(path)
    try:
        conn.execute("UPDATE episodic_events SET created_at = ?", (FIXED_CREATED_AT,))
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("VACUUM")
        observations = int(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0])
        episodes = int(conn.execute("SELECT COUNT(*) FROM episodic_events").fetchone()[0])
        sqlite_version = str(conn.execute("SELECT sqlite_version()").fetchone()[0])
    finally:
        conn.close()
    if observations != 16 or episodes != 4:
        raise RuntimeError(
            f"unexpected fixture counts for {path.name}: observations={observations}, episodes={episodes}"
        )
    return {
        "observations": observations,
        "episodic_events": episodes,
        "total_records": observations + episodes,
        "sqlite_version": sqlite_version,
        "user_version": 0,
    }


def _generate_one(
    *, repo_root: Path, output_dir: Path, tag: str, python: Path
) -> dict[str, Any]:
    commit = _run(["git", "rev-parse", tag], cwd=repo_root).strip()
    with tempfile.TemporaryDirectory(prefix=f"openclaw-mem-{tag}-") as raw_temp:
        temp = Path(raw_temp)
        worktree = temp / "source"
        _run(["git", "worktree", "add", "--detach", str(worktree), tag], cwd=repo_root)
        try:
            observations = temp / "observations.jsonl"
            episodes = temp / "episodes.jsonl"
            state = temp / "episodes-state.json"
            database = output_dir / f"{tag}.sqlite"
            _write_jsonl(observations, _observation_rows())
            _write_jsonl(episodes, _episodic_rows())
            if database.exists():
                database.unlink()
            env = os.environ.copy()
            env.update(
                {
                    "PYTHONPATH": str(worktree),
                    "PYTHONUTF8": "1",
                    "OPENCLAW_MEM_IMPORTANCE_SCORER": "off",
                    "OPENAI_API_KEY": "",
                }
            )
            _run(
                [
                    str(python),
                    "-m",
                    "openclaw_mem.cli",
                    "--db",
                    str(database),
                    "ingest",
                    "--file",
                    str(observations),
                    "--importance-scorer",
                    "off",
                    "--json",
                ],
                cwd=worktree,
                env=env,
            )
            _run(
                [
                    str(python),
                    "-m",
                    "openclaw_mem.cli",
                    "--db",
                    str(database),
                    "episodes",
                    "ingest",
                    "--file",
                    str(episodes),
                    "--state",
                    str(state),
                    "--json",
                ],
                cwd=worktree,
                env=env,
            )
            metadata = _normalize_fixture(database)
        finally:
            _run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo_root)
            _run(["git", "worktree", "prune"], cwd=repo_root)

    return {
        "tag": tag,
        "commit": commit,
        "file": f"{tag}.sqlite",
        "sha256": _sha256(output_dir / f"{tag}.sqlite"),
        **metadata,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()

    repo_root = args.repo_root.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else repo_root / "tests" / "fixtures" / "legacy_dbs"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    fixtures = [
        _generate_one(
            repo_root=repo_root,
            output_dir=output_dir,
            tag=tag,
            python=args.python.expanduser().resolve(),
        )
        for tag in TAGS
    ]
    manifest = {
        "kind": "openclaw-mem.legacy-fixtures.v1",
        "generator": "tools/gen_legacy_fixture.py",
        "record_contract": {"observations": 16, "episodic_events": 4, "total": 20},
        "golden_queries": list(GOLDEN_QUERIES),
        "fixtures": fixtures,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
