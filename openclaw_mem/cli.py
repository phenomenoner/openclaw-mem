#!/usr/bin/env python3
"""openclaw-mem CLI

AI-native design:
- Non-interactive (no prompts)
- Structured output via --json
- Rich examples in help
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional

from openclaw_mem.vector import l2_norm, pack_f32, rank_cosine, rank_rrf

DEFAULT_INDEX_PATH = os.path.expanduser("~/.openclaw/memory/openclaw-mem/observations-index.md")

DEFAULT_DB = os.path.expanduser("~/.openclaw/memory/openclaw-mem.sqlite")
DEFAULT_WORKSPACE = Path.cwd()  # Fallback if not in openclaw workspace
_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def _read_openclaw_config() -> Dict[str, Any]:
    """Read ~/.openclaw/openclaw.json (cached)."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    try:
        config_path = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                _CONFIG_CACHE = json.load(f)
                return _CONFIG_CACHE
    except Exception:
        pass
    
    _CONFIG_CACHE = {}
    return _CONFIG_CACHE


def _connect(db_path: str) -> sqlite3.Connection:
    # Allow in-memory DB and relative paths without a directory component.
    # (Useful for unit tests and quick experiments.)
    dir_ = os.path.dirname(db_path)
    if db_path not in (":memory:", "") and dir_:
        os.makedirs(dir_, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    _init_db(conn)
    return conn



def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            kind TEXT,
            summary TEXT,
            summary_en TEXT,
            lang TEXT,
            tool_name TEXT,
            detail_json TEXT
        );
        """
    )

    # Backward-compatible migration for existing DBs.
    obs_cols = {r[1] for r in conn.execute("PRAGMA table_info(observations)").fetchall()}
    if "summary_en" not in obs_cols:
        conn.execute("ALTER TABLE observations ADD COLUMN summary_en TEXT")
    if "lang" not in obs_cols:
        conn.execute("ALTER TABLE observations ADD COLUMN lang TEXT")

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts
        USING fts5(summary, summary_en, tool_name, detail_json, content='observations', content_rowid='id');
        """
    )

    # If this DB already had an older FTS schema, rebuild once with summary_en included.
    fts_cols = [r[1] for r in conn.execute("PRAGMA table_info(observations_fts)").fetchall()]
    if "summary_en" not in fts_cols:
        conn.execute("DROP TABLE IF EXISTS observations_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE observations_fts
            USING fts5(summary, summary_en, tool_name, detail_json, content='observations', content_rowid='id');
            """
        )
        conn.execute(
            """
            INSERT INTO observations_fts(rowid, summary, summary_en, tool_name, detail_json)
            SELECT id, summary, summary_en, tool_name, detail_json
            FROM observations;
            """
        )

    # Phase 3: vector embeddings (stored as float32 BLOB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observation_embeddings (
            observation_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            norm REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_observation_embeddings_model ON observation_embeddings(model);")

    # Backward-compatible parallel table for English embeddings.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observation_embeddings_en (
            observation_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            norm REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_observation_embeddings_en_model ON observation_embeddings_en(model);")

    conn.commit()


def _insert_observation(conn: sqlite3.Connection, obs: Dict[str, Any]) -> int:
    ts = obs.get("ts") or datetime.utcnow().isoformat()
    kind = obs.get("kind")
    summary = obs.get("summary")
    summary_en = obs.get("summary_en") or obs.get("text_en")
    lang = obs.get("lang")
    tool_name = obs.get("tool_name") or obs.get("tool")
    detail = obs.get("detail") or obs.get("detail_json") or {}
    detail_json = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)

    cur = conn.execute(
        "INSERT INTO observations (ts, kind, summary, summary_en, lang, tool_name, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ts, kind, summary, summary_en, lang, tool_name, detail_json),
    )
    rowid = cur.lastrowid
    conn.execute(
        "INSERT INTO observations_fts (rowid, summary, summary_en, tool_name, detail_json) VALUES (?, ?, ?, ?, ?)",
        (rowid, summary, summary_en, tool_name, detail_json),
    )
    return int(rowid)


def _iter_jsonl(fp) -> Iterable[Dict[str, Any]]:
    for line in fp:
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def cmd_status(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    row = conn.execute("SELECT COUNT(*) AS n, MIN(ts) AS min_ts, MAX(ts) AS max_ts FROM observations").fetchone()
    emb_row = conn.execute("SELECT COUNT(*) AS n FROM observation_embeddings").fetchone()
    emb_models = conn.execute(
        "SELECT model, COUNT(*) AS n FROM observation_embeddings GROUP BY model ORDER BY n DESC"
    ).fetchall()
    emb_en_row = conn.execute("SELECT COUNT(*) AS n FROM observation_embeddings_en").fetchone()
    emb_en_models = conn.execute(
        "SELECT model, COUNT(*) AS n FROM observation_embeddings_en GROUP BY model ORDER BY n DESC"
    ).fetchall()

    data = {
        "db": args.db,
        "count": row["n"],
        "min_ts": row["min_ts"],
        "max_ts": row["max_ts"],
        "embeddings": {
            "count": emb_row["n"],
            "models": [{"model": r["model"], "count": r["n"]} for r in emb_models],
        },
        "embeddings_en": {
            "count": emb_en_row["n"],
            "models": [{"model": r["model"], "count": r["n"]} for r in emb_en_models],
        },
    }
    _emit(data, args.json)


def cmd_ingest(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    if args.file:
        fp = open(args.file, "r", encoding="utf-8")
    else:
        fp = sys.stdin

    inserted: List[int] = []
    for obs in _iter_jsonl(fp):
        inserted.append(_insert_observation(conn, obs))

    conn.commit()
    if args.file:
        fp.close()

    _emit({"inserted": len(inserted), "ids": inserted[:50]}, args.json)


def cmd_search(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    q = args.query.strip()
    if not q:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    rows = conn.execute(
        """
        SELECT o.id, o.ts, o.kind, o.tool_name, o.summary, o.summary_en, o.lang,
               snippet(observations_fts, 0, '[', ']', '…', 12) AS snippet,
               snippet(observations_fts, 1, '[', ']', '…', 12) AS snippet_en,
               bm25(observations_fts) AS score
        FROM observations_fts
        JOIN observations o ON o.id = observations_fts.rowid
        WHERE observations_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?;
        """,
        (q, args.limit),
    ).fetchall()

    out = [dict(r) for r in rows]
    _emit(out, args.json)


def cmd_get(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    ids = args.ids
    rows = conn.execute(
        f"SELECT * FROM observations WHERE id IN ({','.join(['?']*len(ids))}) ORDER BY id",
        ids,
    ).fetchall()
    _emit([dict(r) for r in rows], args.json)


def cmd_timeline(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    window = args.window
    seen = set()
    out = []
    for id_ in args.ids:
        lo, hi = id_ - window, id_ + window
        rows = conn.execute(
            "SELECT * FROM observations WHERE id BETWEEN ? AND ? ORDER BY id",
            (lo, hi),
        ).fetchall()
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            out.append(dict(r))
    out.sort(key=lambda x: x["id"])
    _emit(out, args.json)


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, list):
        for item in payload:
            _print_row(item)
        return
    if isinstance(payload, dict):
        for k, v in payload.items():
            print(f"{k}: {v}")
        return
    print(payload)


def _print_row(item: Dict[str, Any]) -> None:
    _id = item.get("id")
    ts = item.get("ts")
    kind = item.get("kind")
    tool = item.get("tool_name")
    summary = item.get("summary") or item.get("snippet")
    print(f"#{_id} {ts} [{kind}] {tool} :: {summary}")


def _get_api_key(env_var: str = "OPENAI_API_KEY") -> Optional[str]:
    """Get API key from env or ~/.openclaw/openclaw.json."""
    # 1. Try env
    api_key = os.environ.get(env_var)
    if api_key:
        return api_key

    # 2. Try config file
    data = _read_openclaw_config()
    # Traversing: agents -> defaults -> memorySearch -> remote -> apiKey
    key = (
        data.get("agents", {})
        .get("defaults", {})
        .get("memorySearch", {})
        .get("remote", {})
        .get("apiKey")
    )
    if key and isinstance(key, str):
        return key

    return None


def _get_gateway_config(args: argparse.Namespace, *, want_v1: bool = True) -> Dict[str, str]:
    """Resolve Gateway connection details (URL, token, agent_id).

    want_v1:
      - True: returns base URL ending with /v1
      - False: returns raw gateway base URL (no forced /v1)
    """
    config = _read_openclaw_config()

    # 1. URL
    url = getattr(args, "gateway_url", None)
    if not url:
        url = os.environ.get("OPENCLAW_GATEWAY_URL")
    if not url:
        # Construct from config port
        port = config.get("gateway", {}).get("http", {}).get("port") or config.get("gateway", {}).get("port", 18789)
        url = f"http://127.0.0.1:{port}"

    url = url.rstrip("/")
    if want_v1 and not url.endswith("/v1"):
        url = f"{url}/v1"

    # 2. Token
    token = getattr(args, "gateway_token", None)
    if not token:
        token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if not token:
        token = config.get("gateway", {}).get("auth", {}).get("token")

    # 3. Agent ID
    agent_id = getattr(args, "agent_id", None)
    if not agent_id:
        agent_id = os.environ.get("OPENCLAW_AGENT_ID", "main")

    return {
        "url": url,
        "token": token or "",
        "agent_id": agent_id,
    }


def _gateway_tools_invoke(
    args: argparse.Namespace,
    *,
    tool: str,
    tool_args: Dict[str, Any],
    session_key: str = "main",
    timeout: int = 120,
) -> Any:
    """Call OpenClaw Gateway `POST /tools/invoke`.

    This is the recommended black-box path for embeddings/memorySearch.
    """
    gw = _get_gateway_config(args, want_v1=False)
    if not gw["token"]:
        raise RuntimeError("Gateway token not found (set OPENCLAW_GATEWAY_TOKEN or configure gateway.auth.token)")

    url = gw["url"].rstrip("/") + "/tools/invoke"
    payload = {
        "tool": tool,
        "args": tool_args,
        "sessionKey": session_key,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {gw['token']}",
            "Content-Type": "application/json",
            "x-openclaw-agent-id": gw["agent_id"],
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gateway tools/invoke error ({e.code}): {err_body}") from e
    except Exception as e:
        raise RuntimeError(f"Error calling Gateway tools/invoke: {e}") from e

    data = json.loads(body)
    if not isinstance(data, dict) or not data.get("ok"):
        raise RuntimeError(f"tools/invoke returned error: {body[:2000]}")
    return data.get("result")


def cmd_summarize(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Run AI compression on observations (requires compress_memory.py)."""
    try:
        # Import compress_memory module
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from compress_memory import OpenAIClient, compress_daily_note, CompressError
    except ImportError as e:
        _emit({"error": f"Failed to import compress_memory: {e}"}, args.json)
        sys.exit(1)

    use_gateway = bool(getattr(args, "gateway", False) or os.environ.get("OPENCLAW_MEM_USE_GATEWAY") == "1")
    
    api_key: Optional[str] = None
    base_url: str = "https://api.openai.com/v1"
    extra_headers: Dict[str, str] = {}
    model = args.model if hasattr(args, "model") else "gpt-5.2"

    if use_gateway:
        gw_conf = _get_gateway_config(args)
        base_url = gw_conf["url"]
        api_key = gw_conf["token"]
        extra_headers["x-openclaw-agent-id"] = gw_conf["agent_id"]
        
        # Switch default model if user didn't override it (heuristic: check against default)
        # We assume if it's "gpt-5.2" (the parser default), we can switch to "openclaw:<agent>"
        if model == "gpt-5.2":
             model = f"openclaw:{gw_conf['agent_id']}"
             
        if not api_key:
             _emit({"error": "Gateway token not found (check ~/.openclaw/openclaw.json or use --gateway-token)"}, args.json)
             sys.exit(1)
    else:
        # Get API key (standard OpenAI path)
        api_key = _get_api_key()
        if not api_key:
            _emit({"error": "OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json"}, args.json)
            sys.exit(1)
        base_url = args.base_url if hasattr(args, "base_url") else "https://api.openai.com/v1"

    # Determine workspace
    workspace = Path(args.workspace) if hasattr(args, "workspace") and args.workspace else DEFAULT_WORKSPACE

    memory_dir = workspace / "memory"
    memory_file = workspace / "MEMORY.md"
    prompt_file = workspace / "scripts/prompts/compress_memory.txt"

    # Determine date
    if args.date:
        target_date = args.date
    else:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Create client
    client = OpenAIClient(
        api_key=api_key,
        base_url=base_url,
        extra_headers=extra_headers,
    )

    # Run compression
    try:
        result = compress_daily_note(
            date=target_date,
            memory_dir=memory_dir,
            memory_file=memory_file,
            prompt_file=prompt_file,
            client=client,
            model=model,
            max_tokens=args.max_tokens if hasattr(args, "max_tokens") else 700,
            temperature=args.temperature if hasattr(args, "temperature") else 0.2,
            dry_run=args.dry_run if hasattr(args, "dry_run") else False,
        )
        _emit(result, args.json)
    except CompressError as e:
        _emit({"error": str(e)}, args.json)
        sys.exit(1)


def _atomic_append_file(path_: Path, content: str) -> None:
    """Append to a file atomically (write-to-temp + replace)."""
    path_.parent.mkdir(parents=True, exist_ok=True)
    existing = path_.read_text(encoding="utf-8") if path_.exists() else ""

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path_.parent,
        delete=False,
        prefix=".tmp_",
        suffix=path_.suffix or ".txt",
    ) as tmp:
        tmp.write(existing + content)
        tmp_path = Path(tmp.name)

    tmp_path.replace(path_)


def cmd_export(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Export observations to a file (Markdown by default).

    Safety:
    - Writing to MEMORY.md requires --yes.
    """
    out_path = Path(args.to)

    # Safety: exporting to MEMORY.md requires explicit confirmation
    if out_path.name == "MEMORY.md" and not args.yes:
        _emit(
            {
                "error": "Export to MEMORY.md requires --yes flag",
                "hint": "See docs/privacy-export-rules.md",
            },
            args.json,
        )
        sys.exit(2)

    ids: Optional[List[int]] = getattr(args, "ids", None)
    limit: int = int(getattr(args, "limit", 50))
    include_detail: bool = bool(getattr(args, "include_detail", False))

    if ids:
        q = f"SELECT * FROM observations WHERE id IN ({','.join(['?']*len(ids))}) ORDER BY id"
        rows = conn.execute(q, ids).fetchall()
    else:
        rows = conn.execute("SELECT * FROM observations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        rows = list(reversed(rows))

    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    header = f"\n\n## Exported observations ({ts})\n"

    md = [header]
    for r in rows:
        rid = r["id"]
        rts = r["ts"]
        kind = r["kind"] or ""
        tool = r["tool_name"] or ""
        summary = (r["summary"] or "").strip()
        md.append(f"- #{rid} {rts} [{kind}] {tool} :: {summary}\n")
        if include_detail:
            md.append("\n```json\n")
            md.append((r["detail_json"] or "{}").strip() + "\n")
            md.append("```\n")

    _atomic_append_file(out_path, "".join(md))

    _emit(
        {
            "ok": True,
            "exported": len(rows),
            "to": str(out_path),
            "include_detail": include_detail,
        },
        args.json,
    )


class OpenAIEmbeddingsClient:
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def embed(self, texts: List[str], model: str) -> List[List[float]]:
        url = self.base_url + "/embeddings"
        payload = {"model": model, "input": texts}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI embeddings API error ({e.code}): {err_body}") from e
        except Exception as e:
            raise RuntimeError(f"Error calling OpenAI embeddings API: {e}") from e

        data = json.loads(body)
        out: List[List[float]] = []
        for item in data.get("data", []):
            out.append(item["embedding"])
        return out


def _embed_targets(field: str) -> List[Dict[str, str]]:
    if field == "original":
        return [{"name": "original", "text_col": "summary", "table": "observation_embeddings"}]
    if field == "english":
        return [{"name": "english", "text_col": "summary_en", "table": "observation_embeddings_en"}]
    return [
        {"name": "original", "text_col": "summary", "table": "observation_embeddings"},
        {"name": "english", "text_col": "summary_en", "table": "observation_embeddings_en"},
    ]


def cmd_embed(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Compute/store embeddings for observations."""
    api_key = _get_api_key()
    if not api_key:
        _emit({"error": "OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json"}, args.json)
        sys.exit(1)

    model = args.model
    limit = int(args.limit)
    batch = int(args.batch)
    base_url = args.base_url
    field = getattr(args, "field", "original")

    client = OpenAIEmbeddingsClient(api_key=api_key, base_url=base_url)

    per_field: Dict[str, Dict[str, Any]] = {}
    inserted_total = 0
    ids: List[int] = []
    now = datetime.utcnow().isoformat()

    for target in _embed_targets(field):
        rows = conn.execute(
            f"""
            SELECT id, tool_name, {target['text_col']} AS text_value
            FROM observations
            WHERE id NOT IN (
                SELECT observation_id FROM {target['table']} WHERE model = ?
            )
            AND trim(coalesce({target['text_col']}, '')) <> ''
            ORDER BY id
            LIMIT ?
            """,
            (model, limit),
        ).fetchall()

        todo = [dict(r) for r in rows]
        inserted = 0
        field_ids: List[int] = []

        for i in range(0, len(todo), batch):
            chunk = todo[i : i + batch]
            texts = []
            chunk_ids = []
            for r in chunk:
                tid = int(r["id"])
                tool = (r.get("tool_name") or "").strip()
                summary = (r.get("text_value") or "").strip()
                text = f"{tool}: {summary}".strip(": ")
                texts.append(text)
                chunk_ids.append(tid)

            vecs = client.embed(texts, model=model)
            for tid, vec in zip(chunk_ids, vecs):
                blob = pack_f32(vec)
                norm = l2_norm(vec)
                dim = len(vec)
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {target['table']}
                    (observation_id, model, dim, vector, norm, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (tid, model, dim, blob, norm, now),
                )
                inserted += 1
                inserted_total += 1
                field_ids.append(tid)
                ids.append(tid)

            conn.commit()

        per_field[target["name"]] = {
            "embedded": inserted,
            "ids": field_ids[:50],
            "total_candidates": len(todo),
        }

    _emit(
        {
            "ok": True,
            "model": model,
            "field": field,
            "embedded": inserted_total,
            "ids": ids[:50],
            "per_field": per_field,
        },
        args.json,
    )


def cmd_vsearch(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Vector search over stored embeddings (cosine similarity)."""
    model = args.model
    limit = int(args.limit)

    # Get query vector from file/json or via OpenAI API
    query_vec: Optional[List[float]] = None

    if getattr(args, "query_vector_json", None):
        query_vec = json.loads(args.query_vector_json)
    elif getattr(args, "query_vector_file", None):
        query_vec = json.loads(Path(args.query_vector_file).read_text(encoding="utf-8"))
    else:
        api_key = _get_api_key()
        if not api_key:
            _emit({"error": "OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json (or provide --query-vector-json/--query-vector-file)"}, args.json)
            sys.exit(1)
        client = OpenAIEmbeddingsClient(api_key=api_key, base_url=args.base_url)
        query_vec = client.embed([args.query], model=model)[0]

    # Load embeddings
    items = conn.execute(
        "SELECT observation_id, vector, norm FROM observation_embeddings WHERE model = ?",
        (model,),
    ).fetchall()

    ranked = rank_cosine(
        query_vec=query_vec,
        items=((int(r[0]), r[1], float(r[2])) for r in items),
        limit=limit,
    )

    if not ranked:
        _emit([], args.json)
        return

    ids = [rid for rid, _ in ranked]
    q = f"SELECT id, ts, kind, tool_name, summary FROM observations WHERE id IN ({','.join(['?']*len(ids))})"
    rows = conn.execute(q, ids).fetchall()
    obs_map = {int(r["id"]): dict(r) for r in rows}

    out = []
    for rid, score in ranked:
        r = obs_map.get(rid)
        if not r:
            continue
        r["score"] = score
        out.append(r)

    _emit(out, args.json)


def cmd_hybrid(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Hybrid search (FTS + Vector) using RRF."""
    model = args.model
    limit = int(args.limit)
    k = int(args.k)
    query = args.query
    query_en = (getattr(args, "query_en", None) or "").strip() or None

    api_key = _get_api_key()
    if not api_key:
        _emit({"error": "OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json"}, args.json)
        sys.exit(1)

    client = OpenAIEmbeddingsClient(api_key=api_key, base_url=args.base_url)
    try:
        embed_inputs = [query] + ([query_en] if query_en else [])
        embed_vecs = client.embed(embed_inputs, model=model)
        query_vec = embed_vecs[0]
        query_en_vec = embed_vecs[1] if query_en else None
    except Exception as e:
        _emit({"error": str(e)}, args.json)
        sys.exit(1)

    vec_rows = conn.execute(
        "SELECT observation_id, vector, norm FROM observation_embeddings WHERE model = ?",
        (model,),
    ).fetchall()

    vec_ranked = rank_cosine(
        query_vec=query_vec,
        items=((int(r[0]), r[1], float(r[2])) for r in vec_rows),
        limit=limit * 2,
    )
    vec_ids = [rid for rid, _ in vec_ranked]

    vec_en_ids: List[int] = []
    if query_en_vec is not None:
        vec_en_rows = conn.execute(
            "SELECT observation_id, vector, norm FROM observation_embeddings_en WHERE model = ?",
            (model,),
        ).fetchall()

        # Backward-compatible fallback when dedicated EN table is not populated.
        search_rows = vec_en_rows if vec_en_rows else vec_rows

        vec_en_ranked = rank_cosine(
            query_vec=query_en_vec,
            items=((int(r[0]), r[1], float(r[2])) for r in search_rows),
            limit=limit * 2,
        )
        vec_en_ids = [rid for rid, _ in vec_en_ranked]

    fts_rows = conn.execute(
        """
        SELECT rowid
        FROM observations_fts
        WHERE observations_fts MATCH ?
        ORDER BY bm25(observations_fts) ASC
        LIMIT ?;
        """,
        (query, limit * 2),
    ).fetchall()
    fts_ids = [int(r["rowid"]) for r in fts_rows]

    ranked_lists = [fts_ids, vec_ids]
    if vec_en_ids:
        ranked_lists.append(vec_en_ids)

    final_ranking = rank_rrf(ranked_lists, k=k, limit=limit)

    if not final_ranking:
        _emit([], args.json)
        return

    final_ids = [rid for rid, _ in final_ranking]

    q_sql = f"SELECT id, ts, kind, tool_name, summary, summary_en, lang FROM observations WHERE id IN ({','.join(['?']*len(final_ids))})"
    rows = conn.execute(q_sql, final_ids).fetchall()
    obs_map = {int(r["id"]): dict(r) for r in rows}

    out = []
    for rid, score in final_ranking:
        r = obs_map.get(rid)
        if not r:
            continue
        r["rrf_score"] = score
        r["match"] = []
        if rid in fts_ids:
            r["match"].append("text")
        if rid in vec_ids:
            r["match"].append("vector")
        if rid in vec_en_ids:
            r["match"].append("vector_en")
        out.append(r)

    _emit(out, args.json)


def _atomic_write(path_: Path, content: str) -> None:
    path_.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path_.parent,
        delete=False,
        prefix=".tmp_",
        suffix=path_.suffix or ".txt",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path_)


def _format_index_line(row: sqlite3.Row) -> str:
    rid = int(row["id"])
    ts = (row["ts"] or "").strip()
    tool = (row["tool_name"] or "").strip()
    kind = (row["kind"] or "").strip()
    summary = (row["summary"] or "").replace("\n", " ").strip()
    return f"- obs#{rid} {ts} [{kind}] {tool} :: {summary}\n"


def _build_index(conn: sqlite3.Connection, out_path: Path, limit: int) -> int:
    rows = conn.execute(
        "SELECT id, ts, kind, tool_name, summary FROM observations ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    rows = list(reversed(rows))

    header = (
        "# openclaw-mem observations index\n\n"
        "This file is auto-generated. It is safe to embed and search via OpenClaw memorySearch.\n\n"
    )
    body = "".join(_format_index_line(r) for r in rows)
    _atomic_write(out_path, header + body)
    return len(rows)


def cmd_index(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Build a Markdown index file that OpenClaw memorySearch can embed (Route A)."""
    out_path = Path(args.to or DEFAULT_INDEX_PATH)
    limit = int(args.limit)

    n = _build_index(conn, out_path, limit)
    _emit({"ok": True, "to": str(out_path), "rows": n}, args.json)


def _extract_obs_ids(text: str) -> List[int]:
    import re

    ids = set()
    for m in re.finditer(r"\bobs#(\d+)\b", text or ""):
        try:
            ids.add(int(m.group(1)))
        except Exception:
            continue
    return sorted(ids)


def _tokenize_query(q: str) -> List[str]:
    import re

    q = (q or "").lower().strip()
    if not q:
        return []
    parts = re.split(r"[^a-z0-9_#]+", q)
    toks = [p for p in parts if len(p) >= 3 or p.startswith("obs#")]
    return toks[:20]


def _rank_obs_ids_from_snippet(snippet: str, query: str, base_score: float = 0.0) -> List[tuple[int, float]]:
    """Heuristically map a memory_search snippet back to obs IDs.

    memory_search returns chunk-level matches; a snippet may contain multiple obs lines.
    We score each obs line by simple token overlap with the query.
    """
    import re

    toks = _tokenize_query(query)
    if not snippet:
        return []

    ranked: List[tuple[int, float]] = []
    for line in str(snippet).splitlines():
        m = re.search(r"\bobs#(\d+)\b", line)
        if not m:
            continue
        try:
            oid = int(m.group(1))
        except Exception:
            continue

        line_l = line.lower()
        overlap = sum(1 for t in toks if t in line_l)
        # Strongly prefer exact obs# queries
        exact = 5 if f"obs#{oid}" in (query or "").lower() else 0
        score = overlap + exact + (base_score * 2.0)
        ranked.append((oid, float(score)))

    # Highest score first
    ranked.sort(key=lambda x: (-x[1], x[0]))
    return ranked


def cmd_semantic(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Semantic recall via OpenClaw memory_search (black-box embeddings).

    Steps:
      1) Call Gateway /tools/invoke for memory_search
      2) Parse obs#IDs from snippets
      3) Resolve IDs back into openclaw-mem SQLite observations
    """
    query = args.query.strip()
    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    # Call OpenClaw's built-in memory_search tool
    tool_args = {
        "query": query,
        "maxResults": int(args.max_results),
        "minScore": float(args.min_score),
    }
    try:
        result = _gateway_tools_invoke(args, tool="memory_search", tool_args=tool_args, session_key=args.session_key)
    except Exception as e:
        _emit({"error": str(e)}, args.json)
        sys.exit(1)

    # Parse results
    results: Any = None
    if isinstance(result, dict):
        # /tools/invoke wraps tool details
        details = result.get("details")
        if isinstance(details, dict) and isinstance(details.get("results"), list):
            results = details.get("results")
        elif isinstance(result.get("results"), list):
            results = result.get("results")
    elif isinstance(result, list):
        results = result

    if not isinstance(results, list):
        _emit({"error": f"unexpected memory_search result shape: {type(result).__name__}"}, args.json)
        sys.exit(1)

    scores: Dict[int, float] = {}
    for r in results:
        if not isinstance(r, dict):
            continue
        snippet = str(r.get("snippet") or "")
        base = float(r.get("score") or 0.0)
        for oid, sc in _rank_obs_ids_from_snippet(snippet, query, base_score=base):
            scores[oid] = max(scores.get(oid, 0.0), sc)

    if not scores:
        _emit({"ok": True, "query": query, "matches": [], "raw": results[: int(args.raw_limit)]}, args.json)
        return

    ids_ranked = [oid for oid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]

    # Resolve observations
    q = f"SELECT id, ts, kind, tool_name, summary FROM observations WHERE id IN ({','.join(['?']*len(ids_ranked))})"
    rows = conn.execute(q, ids_ranked).fetchall()
    obs_map = {int(r["id"]): dict(r) for r in rows}

    out = []
    for oid in ids_ranked[: int(args.limit)]:
        r = obs_map.get(oid)
        if not r:
            continue
        out.append(r)

    _emit(
        {
            "ok": True,
            "query": query,
            "ids": ids_ranked[: int(args.limit)],
            "matches": out,
            "raw": results[: int(args.raw_limit)],
        },
        args.json,
    )


def _triage_observations(conn: sqlite3.Connection, since_ts: str, keywords: List[str], limit: int) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = [since_ts]
    for k in keywords:
        like = f"%{k}%"
        clauses.append("(lower(coalesce(summary,'')) LIKE ? OR lower(coalesce(tool_name,'')) LIKE ? OR lower(coalesce(detail_json,'')) LIKE ?)")
        params.extend([like, like, like])

    where_kw = " OR ".join(clauses) if clauses else "1=0"
    q = f"""
        SELECT id, ts, kind, tool_name, summary
        FROM observations
        WHERE ts >= ? AND ({where_kw})
        ORDER BY ts DESC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def _triage_cron_errors(*, since_ms: int, cron_jobs_path: str, limit: int) -> List[Dict[str, Any]]:
    """Detect cron jobs whose lastStatus != ok.

    Reads OpenClaw cron store (jobs.json). Deterministic and no LLM calls.
    """
    p = Path(os.path.expanduser(cron_jobs_path))
    if not p.exists():
        return []

    try:
        data = json.loads(p.read_text("utf-8"))
    except Exception:
        return []

    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []

    bad: List[Dict[str, Any]] = []
    for j in jobs:
        if not isinstance(j, dict):
            continue
        state = j.get("state") if isinstance(j.get("state"), dict) else {}
        last_status = state.get("lastStatus")
        last_run = state.get("lastRunAtMs")
        if last_status in (None, "ok"):
            continue
        if isinstance(last_run, (int, float)) and int(last_run) < int(since_ms):
            continue
        bad.append(
            {
                "id": j.get("id"),
                "name": j.get("name"),
                "enabled": j.get("enabled"),
                "lastStatus": last_status,
                "lastRunAtMs": last_run,
                "lastDurationMs": state.get("lastDurationMs"),
                "nextRunAtMs": (state.get("nextRunAtMs") if isinstance(state, dict) else None),
            }
        )

    bad.sort(key=lambda x: (-(int(x.get("lastRunAtMs") or 0)), str(x.get("name") or "")))
    return bad[:limit]


def _triage_tasks(conn: sqlite3.Connection, *, since_ts: str, importance_min: float, limit: int) -> List[Dict[str, Any]]:
    """Scan proactively stored items (tool_name=memory_store) for tasks.

    Deterministic: all logic is local.

    Matching rules:
    - kind == 'task' OR
    - summary starts with TODO:/TASK:/REMINDER:

    Importance is best-effort parsed from detail_json.importance.
    """
    rows = conn.execute(
        """
        SELECT id, ts, kind, tool_name, summary, detail_json
        FROM observations
        WHERE ts >= ? AND tool_name = 'memory_store'
        ORDER BY id DESC
        LIMIT ?
        """,
        (since_ts, max(50, limit * 20)),
    ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        kind = (r["kind"] or "").strip().lower()
        summary = (r["summary"] or "").strip()
        if not summary:
            continue

        is_task = kind == "task" or summary.upper().startswith(("TODO:", "TASK:", "REMINDER:"))
        if not is_task:
            continue

        imp = 0.0
        try:
            dj = json.loads(r["detail_json"] or "{}")
            imp_val = dj.get("importance")
            if isinstance(imp_val, (int, float)):
                imp = float(imp_val)
        except Exception:
            imp = 0.0

        if imp < float(importance_min):
            continue

        out.append({"id": int(r["id"]), "ts": r["ts"], "kind": r["kind"], "tool_name": r["tool_name"], "summary": summary, "importance": imp})
        if len(out) >= limit:
            break

    return out


def _load_triage_state(path_: Path) -> Dict[str, Any]:
    try:
        if not path_.exists():
            return {}
        return json.loads(path_.read_text("utf-8"))
    except Exception:
        return {}


def _atomic_write_json(path_: Path, data: Dict[str, Any]) -> None:
    path_.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path_.parent,
        delete=False,
        prefix=".tmp_",
        suffix=path_.suffix or ".json",
    ) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path_)


def cmd_triage(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Deterministic local triage.

    Modes:
    - heartbeat (default): observations + cron-errors + tasks (new-only)
    - observations: observations only
    - cron-errors: cron store only
    - tasks: tasks only (new-only)

    Exit codes:
      0 = no new issues
      10 = needs attention (new matches found)
      2 = invalid args / error
    """
    try:
        since_minutes = int(getattr(args, "since_minutes", 60))
        limit = int(getattr(args, "limit", 10))
    except Exception:
        _emit({"error": "invalid since/limit"}, True)
        sys.exit(2)

    mode = str(getattr(args, "mode", "heartbeat") or "heartbeat").strip().lower()
    if mode not in {"heartbeat", "observations", "cron-errors", "tasks"}:
        _emit({"error": f"invalid mode: {mode}"}, True)
        sys.exit(2)

    since_minutes = max(0, since_minutes)
    limit = max(1, min(200, limit))

    kw_raw = getattr(args, "keywords", None)
    if kw_raw:
        keywords = [k.strip().lower() for k in str(kw_raw).split(",") if k.strip()]
    else:
        keywords = [
            "error",
            "failed",
            "exception",
            "traceback",
            "timeout",
            "rate_limit",
            "unauthorized",
            "forbidden",
            "not allowed",
            "db locked",
        ]

    cron_jobs_path = getattr(args, "cron_jobs_path", None) or "~/.openclaw/cron/jobs.json"

    # Tasks scan is typically longer-lived than a 30m error window.
    tasks_since_minutes = int(getattr(args, "tasks_since_minutes", 24 * 60))
    importance_min = float(getattr(args, "importance_min", 0.7))

    state_path = Path(os.path.expanduser(getattr(args, "state_path", None) or "~/.openclaw/memory/openclaw-mem/triage-state.json"))
    state = _load_triage_state(state_path)

    last_obs_id = int(((state.get("observations") or {}).get("last_alerted_id") or 0))
    last_task_id = int(((state.get("tasks") or {}).get("last_alerted_id") or 0))
    last_cron_ms = int(((state.get("cron") or {}).get("last_alerted_bad_run_at_ms") or 0))

    from datetime import timezone

    since_dt = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    since_utc = since_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    since_ms = int(since_dt.timestamp() * 1000)

    tasks_since_dt = datetime.now(timezone.utc) - timedelta(minutes=max(0, tasks_since_minutes))
    tasks_since_utc = tasks_since_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    obs_all: List[Dict[str, Any]] = []
    cron_all: List[Dict[str, Any]] = []
    tasks_all: List[Dict[str, Any]] = []

    if mode in {"heartbeat", "observations"}:
        obs_all = _triage_observations(conn, since_utc, keywords, limit)

    if mode in {"heartbeat", "cron-errors"}:
        cron_all = _triage_cron_errors(since_ms=since_ms, cron_jobs_path=str(cron_jobs_path), limit=limit)

    if mode in {"heartbeat", "tasks"}:
        tasks_all = _triage_tasks(conn, since_ts=tasks_since_utc, importance_min=importance_min, limit=limit)

    # Dedupe: only alert on *new* items
    obs_new = [m for m in obs_all if int(m.get("id") or 0) > last_obs_id]
    tasks_new = [m for m in tasks_all if int(m.get("id") or 0) > last_task_id]
    cron_new = [m for m in cron_all if int(m.get("lastRunAtMs") or 0) > last_cron_ms]

    needs_attention = (len(obs_new) > 0) or (len(cron_new) > 0) or (len(tasks_new) > 0)

    out = {
        "ok": True,
        "mode": mode,
        "since_minutes": since_minutes,
        "since_utc": since_utc,
        "keywords": keywords,
        "cron_jobs_path": os.path.expanduser(str(cron_jobs_path)),
        "tasks_since_minutes": tasks_since_minutes,
        "tasks_since_utc": tasks_since_utc,
        "importance_min": importance_min,
        "state_path": str(state_path),
        "needs_attention": needs_attention,
        "observations": {
            "found_total": len(obs_all),
            "found_new": len(obs_new),
            "matches": obs_new,
        },
        "cron": {
            "found_total": len(cron_all),
            "found_new": len(cron_new),
            "matches": cron_new,
        },
        "tasks": {
            "found_total": len(tasks_all),
            "found_new": len(tasks_new),
            "matches": tasks_new,
        },
    }

    if needs_attention:
        # Update state maxima
        if obs_new:
            last_obs_id = max(last_obs_id, max(int(m.get("id") or 0) for m in obs_new))
        if tasks_new:
            last_task_id = max(last_task_id, max(int(m.get("id") or 0) for m in tasks_new))
        if cron_new:
            last_cron_ms = max(last_cron_ms, max(int(m.get("lastRunAtMs") or 0) for m in cron_new))

        new_state = dict(state) if isinstance(state, dict) else {}
        new_state["observations"] = {"last_alerted_id": last_obs_id}
        new_state["tasks"] = {"last_alerted_id": last_task_id}
        new_state["cron"] = {"last_alerted_bad_run_at_ms": last_cron_ms}
        _atomic_write_json(state_path, new_state)

    _emit(out, True)

    if needs_attention:
        sys.exit(10)
    sys.exit(0)


def cmd_harvest(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Auto-ingest and embed observations from log file."""
    # 1. Determine source
    default_source = os.path.expanduser("~/.openclaw/memory/openclaw-mem-observations.jsonl")
    source = Path(args.source or default_source)

    if not source.exists() or source.stat().st_size == 0:
        _emit({"ok": True, "processed": 0, "reason": "source empty/missing"}, args.json)
        return

    # 2. Rotate
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    processing = source.with_suffix(f".jsonl.{ts}.processing")
    try:
        source.rename(processing)
    except OSError as e:
        _emit({"error": f"Failed to rotate log: {e}"}, args.json)
        sys.exit(1)

    # 3. Ingest
    inserted_ids = []
    try:
        with open(processing, "r", encoding="utf-8") as fp:
            for obs in _iter_jsonl(fp):
                inserted_ids.append(_insert_observation(conn, obs))
        conn.commit()
    except Exception as e:
        _emit({"error": f"Ingest failed: {e}", "file": str(processing)}, args.json)
        sys.exit(1)

    # 4. Update index (Route A)
    if getattr(args, "update_index", True):
        try:
            out_path = Path(getattr(args, "index_to", None) or DEFAULT_INDEX_PATH)
            _build_index(conn, out_path, int(getattr(args, "index_limit", 5000)))
        except Exception as e:
            print(f"Warning: failed to update index: {e}", file=sys.stderr)

    # Emit ingest result
    _emit(
        {
            "ok": True,
            "ingested": len(inserted_ids),
            "source": str(source),
            "archive": str(args.archive_dir) if args.archive_dir else "deleted",
        },
        args.json,
    )

    # 5. Embed (Optional)
    if args.embed:
        embed_args = argparse.Namespace(**vars(args))
        embed_args.limit = 500
        embed_args.batch = 64
        cmd_embed(conn, embed_args)

    # 6. Archive or Delete
    if args.archive_dir:
        archive_dir = Path(args.archive_dir)
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / processing.name
        processing.rename(dest)
    else:
        processing.unlink()


def cmd_store(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Proactive memory storage (SQLite + Vector + Markdown)."""
    text = args.text.strip()
    if not text:
        _emit({"error": "empty text"}, args.json)
        sys.exit(1)

    text_en = (getattr(args, "text_en", None) or "").strip() or None
    lang = (getattr(args, "lang", None) or "").strip() or None

    # 1. Insert into SQLite
    obs = {
        "kind": args.category,  # e.g., 'fact', 'preference'
        "summary": text,
        "summary_en": text_en,
        "lang": lang,
        "tool_name": "memory_store",
        "detail": {"importance": args.importance}
    }
    rowid = _insert_observation(conn, obs)

    # 2. Embed and store vector
    api_key = _get_api_key()
    if api_key:
        try:
            client = OpenAIEmbeddingsClient(api_key=api_key, base_url=args.base_url)
            created_at = datetime.utcnow().isoformat()

            vec = client.embed([text], model=args.model)[0]
            blob = pack_f32(vec)
            norm = l2_norm(vec)
            conn.execute(
                """
                INSERT OR REPLACE INTO observation_embeddings
                (observation_id, model, dim, vector, norm, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (rowid, args.model, len(vec), blob, norm, created_at),
            )

            if text_en:
                vec_en = client.embed([text_en], model=args.model)[0]
                blob_en = pack_f32(vec_en)
                norm_en = l2_norm(vec_en)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO observation_embeddings_en
                    (observation_id, model, dim, vector, norm, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (rowid, args.model, len(vec_en), blob_en, norm_en, created_at),
                )

            conn.commit()
        except Exception as e:
            # Non-fatal: storage succeeded, vector failed
            print(f"Warning: Failed to embed memory: {e}", file=sys.stderr)
    else:
        conn.commit()
        print("Warning: No API key, skipping embedding", file=sys.stderr)

    # 3. Append to memory/YYYY-MM-DD.md
    workspace = Path(args.workspace) if hasattr(args, "workspace") and args.workspace else DEFAULT_WORKSPACE
    
    # Fallback logic for workspace memory dir
    memory_dir = workspace / "memory"
    if not memory_dir.exists():
         alt = Path(os.path.expanduser("~/.openclaw/memory"))
         if alt.exists():
             memory_dir = alt

    date_str = datetime.now().strftime("%Y-%m-%d")
    md_file = memory_dir / f"{date_str}.md"
    
    md_entry = f"- [{args.category.upper()}] {text} (importance: {args.importance})\n"
    
    try:
        _atomic_append_file(md_file, md_entry)
        stored_path = str(md_file)
    except Exception as e:
        stored_path = f"failed ({e})"

    _emit({"ok": True, "id": rowid, "file": stored_path, "embedded": bool(api_key)}, args.json)


def build_parser() -> argparse.ArgumentParser:
    epilog = (
        "Examples:\n"
        "  # Observation store\n"
        "  openclaw-mem status --json\n"
        "  openclaw-mem ingest --file observations.jsonl --json\n"
        "\n"
        "  # Progressive disclosure search\n"
        "  openclaw-mem search \"gateway timeout\" --limit 20 --json\n"
        "  openclaw-mem timeline 23 41 57 --window 4 --json\n"
        "  openclaw-mem get 23 41 57 --json\n"
        "\n"
        "  # AI compression (requires API key via env or ~/.openclaw/openclaw.json)\n"
        "  export OPENAI_API_KEY=sk-...\n"
        "  openclaw-mem summarize --json  # yesterday's notes\n"
        "  openclaw-mem summarize 2026-02-04 --dry-run\n"
        "\n"
        "  # Export observations (Markdown)\n"
        "  openclaw-mem export --to /tmp/export.md --limit 20 --json\n"
        "  openclaw-mem export --to MEMORY.md --yes --limit 20\n"
        "\n"
        "  # Vector search (Phase 3)\n"
        "  export OPENAI_API_KEY=sk-...\n"
        "  openclaw-mem embed --limit 500 --json\n"
        "  openclaw-mem vsearch \"gateway timeout\" --limit 10 --json\n"
        "\n"
        "  # Hybrid Search & Store (Phase 4)\n"
        "  openclaw-mem hybrid \"python error\" --limit 5 --json\n"
        "  openclaw-mem store \"Prefer tabs over spaces\" --category preference --importance 0.9 --json\n"
        "\n"
        "Global flags also work before the command:\n"
        "  openclaw-mem --db /tmp/mem.sqlite --json status\n"
        "\n"
        "Input JSONL (one per line) for ingest:\n"
        "  {\"ts\":\"2026-02-04T13:00:00Z\", \"kind\":\"tool\", \"tool_name\":\"cron.list\", \"summary\":\"cron list called\", \"detail\":{...}}\n"
    )

    p = argparse.ArgumentParser(
        prog="openclaw-mem",
        description="OpenClaw memory CLI (M0 prototype).",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global flags (before the subcommand). These are merged with per-command flags.
    p.add_argument("--db", dest="db_global", default=None, help="SQLite DB path")
    p.add_argument("--json", dest="json_global", action="store_true", help="Structured JSON output")

    def add_common(sp: argparse.ArgumentParser) -> None:
        # Allow flags after the subcommand too.
        sp.add_argument("--db", default=None, help="SQLite DB path")
        sp.add_argument("--json", action="store_true", help="Structured JSON output")

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", help="Show store stats")
    add_common(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("ingest", help="Ingest observations (JSONL via --file or stdin)")
    add_common(sp)
    sp.add_argument("--file", help="JSONL file path (default: stdin)")
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("search", help="FTS search over observations")
    add_common(sp)
    sp.add_argument("query", help="Search query (FTS5 syntax)")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("timeline", help="Windowed timeline around IDs")
    add_common(sp)
    sp.add_argument("ids", type=int, nargs="+", help="Observation IDs")
    sp.add_argument("--window", type=int, default=4, help="±N rows around each id")
    sp.set_defaults(func=cmd_timeline)

    sp = sub.add_parser("get", help="Get full observations by ID")
    add_common(sp)
    sp.add_argument("ids", type=int, nargs="+", help="Observation IDs")
    sp.set_defaults(func=cmd_get)

    sp = sub.add_parser("summarize", help="Run AI compression on daily notes (requires API key)")
    add_common(sp)
    sp.add_argument("date", nargs="?", help="Date to compress (YYYY-MM-DD, default: yesterday)")
    sp.add_argument("--workspace", type=Path, help="Workspace root (default: cwd)")
    sp.add_argument("--model", default="gpt-5.2", help="OpenAI model")
    sp.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI API base URL")
    sp.add_argument("--max-tokens", type=int, default=700, help="Max output tokens")
    sp.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature")
    sp.add_argument("--dry-run", action="store_true", help="Preview without writing")
    # Gateway options
    sp.add_argument("--gateway", action="store_true", help="Use OpenClaw Gateway for model routing")
    sp.add_argument("--gateway-url", help="OpenClaw Gateway base URL (auto-detected if unset)")
    sp.add_argument("--gateway-token", help="OpenClaw Gateway token (auto-detected from ~/.openclaw/openclaw.json)")
    sp.add_argument("--agent-id", default="main", help="Target agent ID for Gateway (default: main)")
    sp.set_defaults(func=cmd_summarize)

    sp = sub.add_parser("export", help="Export observations to a Markdown file")
    add_common(sp)
    sp.add_argument("--to", required=True, help="Target file (e.g., MEMORY.md)")
    sp.add_argument("--yes", action="store_true", help="Required when exporting to MEMORY.md")
    sp.add_argument("--ids", type=int, nargs="+", help="Specific observation IDs to export")
    sp.add_argument("--limit", type=int, default=50, help="Export last N observations (default: 50)")
    sp.add_argument("--include-detail", action="store_true", help="Include detail_json blocks")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("embed", help="Compute/store embeddings for observations (requires API key)")
    add_common(sp)
    sp.add_argument("--model", default="text-embedding-3-small", help="Embedding model")
    sp.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI API base URL")
    sp.add_argument("--limit", type=int, default=500, help="Max observations to embed (default: 500)")
    sp.add_argument("--batch", type=int, default=64, help="Batch size per API call (default: 64)")
    sp.add_argument("--field", choices=["original", "english", "both"], default="original", help="Embedding source field (default: original)")
    sp.set_defaults(func=cmd_embed)

    sp = sub.add_parser("vsearch", help="Vector search over embeddings (cosine similarity)")
    add_common(sp)
    sp.add_argument("query", help="Query text")
    sp.add_argument("--model", default="text-embedding-3-small", help="Embedding model")
    sp.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI API base URL")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--query-vector-json", help="Provide query vector as JSON array (testing/offline)")
    sp.add_argument("--query-vector-file", help="Provide query vector from JSON file (testing/offline)")
    sp.set_defaults(func=cmd_vsearch)

    sp = sub.add_parser("hybrid", help="Hybrid search (Vector + FTS) using RRF")
    add_common(sp)
    sp.add_argument("query", help="Query text")
    sp.add_argument("--query-en", help="Optional English query for additional vector route")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--k", type=int, default=60, help="RRF constant (default: 60)")
    sp.add_argument("--model", default="text-embedding-3-small", help="Embedding model")
    sp.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI API base URL")
    sp.set_defaults(func=cmd_hybrid)

    sp = sub.add_parser("store", help="Proactively store a memory")
    add_common(sp)
    sp.add_argument("text", help="Memory content")
    sp.add_argument("--text-en", help="Optional English translation/summary")
    sp.add_argument("--lang", help="Original text language code (e.g., ko, ja, es)")
    sp.add_argument("--category", default="fact", choices=["fact", "preference", "decision", "entity", "task", "other"])
    sp.add_argument("--importance", type=float, default=0.7)
    sp.add_argument("--model", default="text-embedding-3-small", help="Embedding model")
    sp.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI API base URL")
    sp.add_argument("--workspace", type=Path, help="Workspace root (default: cwd)")
    sp.set_defaults(func=cmd_store)

    sp = sub.add_parser("index", help="Build Markdown index for OpenClaw memory_search (Route A)")
    add_common(sp)
    sp.add_argument("--to", help=f"Output path (default: {DEFAULT_INDEX_PATH})")
    sp.add_argument("--limit", type=int, default=5000, help="Max observations to include")
    sp.set_defaults(func=cmd_index)

    sp = sub.add_parser("semantic", help="Semantic recall via OpenClaw memory_search (black-box embeddings)")
    add_common(sp)
    sp.add_argument("query", help="Search query")
    sp.add_argument("--limit", type=int, default=10, help="Max matched observation IDs to resolve")
    sp.add_argument("--max-results", type=int, default=8, help="memory_search maxResults")
    sp.add_argument("--min-score", type=float, default=0.0, help="memory_search minScore")
    sp.add_argument("--raw-limit", type=int, default=8, help="Include first N raw memory_search hits")
    sp.add_argument("--session-key", default="main", help="Gateway sessionKey for tools/invoke")
    sp.add_argument("--gateway-url", help="OpenClaw Gateway base URL (auto-detected if unset)")
    sp.add_argument("--gateway-token", help="OpenClaw Gateway token (auto-detected from ~/.openclaw/openclaw.json)")
    sp.add_argument("--agent-id", default="main", help="Target agent ID for Gateway (default: main)")
    sp.set_defaults(func=cmd_semantic)

    sp = sub.add_parser("triage", help="Deterministic local scan (heartbeat/cron)"
    )
    add_common(sp)
    sp.add_argument(
        "--mode",
        default="heartbeat",
        choices=["heartbeat", "observations", "cron-errors", "tasks"],
        help="Scan mode (default: heartbeat)",
    )
    sp.add_argument("--since-minutes", type=int, default=60, help="Look back window in minutes")
    sp.add_argument("--limit", type=int, default=10, help="Max matches to return")
    sp.add_argument("--keywords", help="Comma-separated keywords override (observations modes)")
    sp.add_argument(
        "--cron-jobs-path",
        dest="cron_jobs_path",
        help="Path to OpenClaw cron jobs store (default: ~/.openclaw/cron/jobs.json)",
    )
    sp.add_argument(
        "--tasks-since-minutes",
        dest="tasks_since_minutes",
        type=int,
        default=24 * 60,
        help="Tasks lookback window in minutes (default: 1440)",
    )
    sp.add_argument(
        "--importance-min",
        dest="importance_min",
        type=float,
        default=0.7,
        help="Min importance for tasks mode (default: 0.7)",
    )
    sp.add_argument(
        "--state-path",
        dest="state_path",
        help="State file for dedupe (default: ~/.openclaw/memory/openclaw-mem/triage-state.json)",
    )
    sp.set_defaults(func=cmd_triage)

    sp = sub.add_parser("harvest", help="Auto-ingest and embed observations from log file")
    add_common(sp)
    sp.add_argument("--source", help="JSONL source file (default: ~/.openclaw/memory/openclaw-mem-observations.jsonl)")
    sp.add_argument("--archive-dir", help="Directory to move processed files (default: delete)")
    sp.add_argument("--embed", action="store_true", default=True, help="Run embedding after ingest (default: True)")
    sp.add_argument("--no-embed", dest="embed", action="store_false", help="Skip embedding")
    sp.add_argument("--model", default="text-embedding-3-small", help="Embedding model")
    sp.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI API base URL")
    sp.add_argument("--update-index", action="store_true", default=True, help="Update Route A index file after ingest (default: True)")
    sp.add_argument("--no-update-index", dest="update_index", action="store_false", help="Skip index update")
    sp.add_argument("--index-to", default=None, help=f"Index output path (default: {DEFAULT_INDEX_PATH})")
    sp.add_argument("--index-limit", type=int, default=5000, help="Index: max observations to include")
    sp.set_defaults(func=cmd_harvest)

    return p


def main() -> None:
    args = build_parser().parse_args()

    # Merge global flags (before subcommand) + per-command flags (after subcommand)
    base_db = os.environ.get("OPENCLAW_MEM_DB", DEFAULT_DB)
    args.db = getattr(args, "db", None) or getattr(args, "db_global", None) or base_db
    args.json = bool(getattr(args, "json", False) or getattr(args, "json_global", False))

    conn = _connect(args.db)
    args.func(conn, args)


if __name__ == "__main__":
    main()
