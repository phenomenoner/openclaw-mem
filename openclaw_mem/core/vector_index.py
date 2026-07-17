"""Exact vector-index backends with an optional NumPy acceleration lane."""

from __future__ import annotations

import math
import hashlib
import re
import sqlite3
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence

from openclaw_mem.vector import l2_norm, pack_f32, rank_cosine


SUPPORTED_TABLES = {"observation_embeddings", "observation_embeddings_en"}
_CACHE_MAX_ENTRIES = 8
SQLITE_VEC_META_TABLE = "openclaw_vec_indexes"
_SQLITE_VEC_SOURCE_TABLES = tuple(sorted(SUPPORTED_TABLES))


class VectorIndex(Protocol):
    name: str

    def search(
        self,
        conn: sqlite3.Connection,
        query_vector: Sequence[float],
        *,
        model: str,
        limit: int = 20,
        table: str = "observation_embeddings",
    ) -> list[tuple[int, float]]: ...


class SqliteVecUnavailable(RuntimeError):
    """sqlite-vec is not installed or cannot be loaded by this SQLite build."""


class SqliteVecIndexStale(RuntimeError):
    """A persisted vec0 index is missing or no longer matches source rows."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _validate_table(table: str) -> None:
    if table not in SUPPORTED_TABLES:
        raise ValueError(f"unsupported embeddings table: {table}")


class PurePythonIndex:
    name = "python"

    def search(
        self,
        conn: sqlite3.Connection,
        query_vector: Sequence[float],
        *,
        model: str,
        limit: int = 20,
        table: str = "observation_embeddings",
    ) -> list[tuple[int, float]]:
        _validate_table(table)
        if limit <= 0:
            return []
        rows = conn.execute(
            f"SELECT observation_id, vector, norm FROM {table} "
            "WHERE model = ? AND dim = ? ORDER BY observation_id",
            (model, len(query_vector)),
        ).fetchall()
        return rank_cosine(
            query_vec=query_vector,
            items=((int(row[0]), row[1], float(row[2])) for row in rows),
            limit=int(limit),
        )


def _load_numpy() -> Any | None:
    try:
        import numpy
    except ImportError:
        return None
    return numpy


def _load_sqlite_vec() -> Any | None:
    try:
        import sqlite_vec
    except ImportError:
        return None
    return sqlite_vec


def _enable_sqlite_vec(conn: sqlite3.Connection, module: Any | None = None) -> Any:
    sqlite_vec = module if module is not None else _load_sqlite_vec()
    if sqlite_vec is None:
        raise SqliteVecUnavailable(
            "sqlite-vec backend requested but sqlite-vec is not installed; "
            "install openclaw-context-pack[vec] or choose numpy/python"
        )
    try:
        conn.execute("SELECT vec_version()").fetchone()
        return sqlite_vec
    except sqlite3.DatabaseError:
        pass
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
    except (AttributeError, sqlite3.Error, OSError) as exc:
        raise SqliteVecUnavailable(f"sqlite-vec extension could not be loaded: {exc}") from exc
    finally:
        try:
            conn.enable_load_extension(False)
        except (AttributeError, sqlite3.Error):
            pass
    return sqlite_vec


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def _source_signature(
    conn: sqlite3.Connection, *, table: str, model: str, dim: int
) -> tuple[int, int]:
    _validate_table(table)
    row = conn.execute(
        f"SELECT COUNT(*), COALESCE(MAX(observation_id), 0) FROM {table} "
        "WHERE model = ? AND dim = ?",
        (model, int(dim)),
    ).fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def _vec_table_name(*, table: str, model: str, dim: int) -> str:
    _validate_table(table)
    slug = re.sub(r"[^a-z0-9]+", "_", str(model).lower()).strip("_")[:32] or "model"
    digest = hashlib.sha256(str(model).encode("utf-8")).hexdigest()[:8]
    suffix = "_en" if table == "observation_embeddings_en" else ""
    return f"vec_idx_{slug}_{digest}_{int(dim)}{suffix}"


def _create_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SQLITE_VEC_META_TABLE} (
            source_table TEXT NOT NULL,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vec_table TEXT NOT NULL UNIQUE,
            source_row_count INTEGER NOT NULL,
            source_max_id INTEGER NOT NULL,
            rebuilt_at TEXT NOT NULL,
            sqlite_vec_version TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(source_table, model, dim)
        )
        """
    )
    columns = {
        str(row[1]) for row in conn.execute(f"PRAGMA table_info({SQLITE_VEC_META_TABLE})")
    }
    if "stale" not in columns:
        conn.execute(
            f"ALTER TABLE {SQLITE_VEC_META_TABLE} "
            "ADD COLUMN stale INTEGER NOT NULL DEFAULT 1"
        )
    for source in _SQLITE_VEC_SOURCE_TABLES:
        if not _table_exists(conn, source):
            continue
        for action in ("INSERT", "UPDATE", "DELETE"):
            trigger = f"openclaw_vec_invalidate_{source}_{action.lower()}"
            conn.execute(
                f'CREATE TRIGGER IF NOT EXISTS "{trigger}" AFTER {action} ON "{source}" '
                f"BEGIN UPDATE {SQLITE_VEC_META_TABLE} SET stale = 1 "
                f"WHERE source_table = '{source}'; END"
            )


def sqlite_vec_index_status(conn: sqlite3.Connection) -> dict[str, Any]:
    """Inspect persisted vec0 indexes without creating or rebuilding anything."""

    module = _load_sqlite_vec()
    version: str | None = None
    load_error: str | None = None
    if module is not None:
        try:
            _enable_sqlite_vec(conn, module)
            version = str(conn.execute("SELECT vec_version()").fetchone()[0])
        except SqliteVecUnavailable as exc:
            load_error = str(exc)

    metadata: dict[tuple[str, str, int], sqlite3.Row | tuple[Any, ...]] = {}
    if _table_exists(conn, SQLITE_VEC_META_TABLE):
        meta_columns = {
            str(row[1])
            for row in conn.execute(f"PRAGMA table_info({SQLITE_VEC_META_TABLE})")
        }
        stale_expr = "stale" if "stale" in meta_columns else "1 AS stale"
        for row in conn.execute(
            f"SELECT source_table, model, dim, vec_table, source_row_count, "
            f"source_max_id, rebuilt_at, sqlite_vec_version, {stale_expr} "
            f"FROM {SQLITE_VEC_META_TABLE}"
        ).fetchall():
            metadata[(str(row[0]), str(row[1]), int(row[2]))] = row

    distributions: list[tuple[str, str, int]] = []
    for source in sorted(SUPPORTED_TABLES):
        if not _table_exists(conn, source):
            continue
        distributions.extend(
            (source, str(row[0]), int(row[1]))
            for row in conn.execute(
                f"SELECT model, dim FROM {source} GROUP BY model, dim ORDER BY model, dim"
            ).fetchall()
        )

    keys = sorted(set(distributions) | set(metadata))
    indexes: list[dict[str, Any]] = []
    for source, model, dim in keys:
        meta = metadata.get((source, model, dim))
        current_count, current_max_id = _source_signature(
            conn, table=source, model=model, dim=dim
        ) if _table_exists(conn, source) else (0, 0)
        vec_table = str(meta[3]) if meta is not None else _vec_table_name(
            table=source, model=model, dim=dim
        )
        present = meta is not None and _table_exists(conn, vec_table)
        indexed_rows: int | None = None
        if present and version is not None:
            try:
                indexed_rows = int(conn.execute(f'SELECT COUNT(*) FROM "{vec_table}"').fetchone()[0])
            except sqlite3.DatabaseError:
                indexed_rows = None
        fresh = bool(
            present
            and indexed_rows == current_count
            and int(meta[4]) == current_count
            and int(meta[5]) == current_max_id
            and not bool(meta[8])
        )
        reason = None
        if not present:
            reason = "missing_index"
        elif indexed_rows is None:
            reason = "extension_unavailable"
        elif bool(meta[8]) or not fresh:
            reason = "source_changed"
        indexes.append(
            {
                "source_table": source,
                "model": model,
                "dim": dim,
                "vec_table": vec_table,
                "present": present,
                "fresh": fresh,
                "reason": reason,
                "indexed_rows": indexed_rows,
                "source_row_count": current_count,
                "source_max_id": current_max_id,
                "rebuilt_at": str(meta[6]) if meta is not None else None,
            }
        )
    return {
        "installed": module is not None and version is not None,
        "version": version,
        "load_error": load_error,
        "fresh": bool(indexes) and all(item["fresh"] for item in indexes),
        "index_count": sum(1 for item in indexes if item["present"]),
        "row_count": sum(int(item["indexed_rows"] or 0) for item in indexes),
        "indexes": indexes,
        "hint": None
        if not indexes or all(item["fresh"] for item in indexes)
        else "run `openclaw-mem db reindex --vec --json`",
    }


def rebuild_sqlite_vec_indexes(conn: sqlite3.Connection) -> dict[str, Any]:
    """Atomically rebuild every per-model vec0 table from source embeddings."""

    _enable_sqlite_vec(conn)
    version = str(conn.execute("SELECT vec_version()").fetchone()[0])
    _create_meta_table(conn)
    desired: set[tuple[str, str, int]] = set()
    rebuilt: list[dict[str, Any]] = []

    for source in sorted(SUPPORTED_TABLES):
        for row in conn.execute(
            f"SELECT model, dim, COUNT(*), COALESCE(MAX(observation_id), 0) "
            f"FROM {source} GROUP BY model, dim ORDER BY model, dim"
        ).fetchall():
            model, dim, row_count, max_id = str(row[0]), int(row[1]), int(row[2]), int(row[3])
            desired.add((source, model, dim))
            vec_table = _vec_table_name(table=source, model=model, dim=dim)
            conn.execute(f'DROP TABLE IF EXISTS "{vec_table}"')
            conn.execute(
                f'CREATE VIRTUAL TABLE "{vec_table}" USING vec0('
                f'observation_id integer primary key, embedding float[{dim}] distance_metric=cosine)'
            )
            rows = conn.execute(
                f"SELECT observation_id, vector FROM {source} "
                "WHERE model = ? AND dim = ? ORDER BY observation_id",
                (model, dim),
            ).fetchall()
            conn.executemany(
                f'INSERT INTO "{vec_table}"(observation_id, embedding) VALUES (?, ?)',
                ((int(item[0]), item[1]) for item in rows),
            )
            conn.execute(
                f"INSERT INTO {SQLITE_VEC_META_TABLE}("
                "source_table, model, dim, vec_table, source_row_count, source_max_id, rebuilt_at, sqlite_vec_version, stale"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0) "
                "ON CONFLICT(source_table, model, dim) DO UPDATE SET "
                "vec_table=excluded.vec_table, source_row_count=excluded.source_row_count, "
                "source_max_id=excluded.source_max_id, rebuilt_at=excluded.rebuilt_at, "
                "sqlite_vec_version=excluded.sqlite_vec_version, stale=0",
                (source, model, dim, vec_table, row_count, max_id, _utcnow_iso(), version),
            )
            rebuilt.append(
                {
                    "source_table": source,
                    "model": model,
                    "dim": dim,
                    "vec_table": vec_table,
                    "row_count": row_count,
                }
            )

    existing = conn.execute(
        f"SELECT source_table, model, dim, vec_table FROM {SQLITE_VEC_META_TABLE}"
    ).fetchall()
    for row in existing:
        key = (str(row[0]), str(row[1]), int(row[2]))
        if key in desired:
            continue
        vec_table = str(row[3])
        if re.fullmatch(r"vec_idx_[a-z0-9_]+", vec_table):
            conn.execute(f'DROP TABLE IF EXISTS "{vec_table}"')
        conn.execute(
            f"DELETE FROM {SQLITE_VEC_META_TABLE} WHERE source_table = ? AND model = ? AND dim = ?",
            key,
        )

    return {
        "kind": "openclaw-mem.db.vec-reindex.v1",
        "backend": "sqlite-vec",
        "sqlite_vec_version": version,
        "index_count": len(rebuilt),
        "row_count": sum(int(item["row_count"]) for item in rebuilt),
        "indexes": rebuilt,
    }


@dataclass
class _MatrixCache:
    signature: tuple[int | None, int]
    ids: Any
    matrix: Any
    norms: Any


_NUMPY_CACHE: "OrderedDict[tuple[str, str, str, int], _MatrixCache]" = OrderedDict()
_NUMPY_LOADS = 0
_NUMPY_HITS = 0


def _database_identity(conn: sqlite3.Connection) -> tuple[str, int | None]:
    rows = conn.execute("PRAGMA database_list").fetchall()
    raw_path = next((str(row[2] or "") for row in rows if str(row[1]) == "main"), "")
    if not raw_path:
        return f":memory:{id(conn)}", int(conn.total_changes)
    path = Path(raw_path).expanduser().resolve()
    mtimes = []
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            mtimes.append(candidate.stat().st_mtime_ns)
        except FileNotFoundError:
            continue
    return str(path), max(mtimes) if mtimes else None


class NumpyIndex:
    name = "numpy"

    def __init__(self, numpy_module: Any | None = None):
        self._np = numpy_module if numpy_module is not None else _load_numpy()
        if self._np is None:
            raise RuntimeError(
                "NumPy vector backend requested but numpy is not installed; "
                "install the development/optional NumPy dependency or use --vector-backend python"
            )

    def cache_info(self) -> dict[str, int]:
        return {"entries": len(_NUMPY_CACHE), "loads": _NUMPY_LOADS, "hits": _NUMPY_HITS}

    def _matrix(
        self,
        conn: sqlite3.Connection,
        *,
        model: str,
        dim: int,
        table: str,
    ) -> _MatrixCache:
        global _NUMPY_HITS, _NUMPY_LOADS

        identity, mtime_ns = _database_identity(conn)
        row_count = int(
            conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE model = ? AND dim = ?", (model, dim)
            ).fetchone()[0]
        )
        key = (identity, table, model, dim)
        signature = (mtime_ns, row_count)
        cached = _NUMPY_CACHE.get(key)
        if cached is not None and cached.signature == signature:
            _NUMPY_CACHE.move_to_end(key)
            _NUMPY_HITS += 1
            return cached

        rows = conn.execute(
            f"SELECT observation_id, vector, norm FROM {table} "
            "WHERE model = ? AND dim = ? ORDER BY observation_id",
            (model, dim),
        ).fetchall()
        ids: list[int] = []
        vectors: list[Any] = []
        norms: list[float] = []
        for row in rows:
            blob = row[1]
            norm = float(row[2] or 0.0)
            if not blob or not norm or not math.isfinite(norm):
                continue
            vector = self._np.frombuffer(blob, dtype=self._np.float32)
            if int(vector.size) != dim:
                continue
            ids.append(int(row[0]))
            vectors.append(vector)
            norms.append(norm)
        matrix = (
            self._np.stack(vectors).astype(self._np.float32, copy=False)
            if vectors
            else self._np.empty((0, dim), dtype=self._np.float32)
        )
        value = _MatrixCache(
            signature=signature,
            ids=self._np.asarray(ids, dtype=self._np.int64),
            matrix=matrix,
            norms=self._np.asarray(norms, dtype=self._np.float64),
        )
        _NUMPY_CACHE[key] = value
        _NUMPY_CACHE.move_to_end(key)
        while len(_NUMPY_CACHE) > _CACHE_MAX_ENTRIES:
            _NUMPY_CACHE.popitem(last=False)
        _NUMPY_LOADS += 1
        return value

    def search(
        self,
        conn: sqlite3.Connection,
        query_vector: Sequence[float],
        *,
        model: str,
        limit: int = 20,
        table: str = "observation_embeddings",
    ) -> list[tuple[int, float]]:
        _validate_table(table)
        if limit <= 0:
            return []
        query = self._np.asarray(list(query_vector), dtype=self._np.float64)
        query_norm = float(self._np.linalg.norm(query))
        if query.size == 0 or query_norm == 0.0 or not math.isfinite(query_norm):
            return []
        cached = self._matrix(
            conn, model=model, dim=int(query.size), table=table
        )
        if cached.ids.size == 0:
            return []
        scores = (cached.matrix @ query) / (query_norm * cached.norms)
        valid = self._np.isfinite(scores)
        if not bool(valid.all()):
            ids = cached.ids[valid]
            scores = scores[valid]
        else:
            ids = cached.ids
        count = int(scores.size)
        if count == 0:
            return []
        take = min(int(limit), count)
        if take < count:
            threshold = self._np.partition(scores, count - take)[count - take]
            greater = self._np.flatnonzero(scores > threshold)
            tied = self._np.flatnonzero(scores == threshold)
            selected = self._np.concatenate((greater, tied[: take - int(greater.size)]))
        else:
            selected = self._np.arange(count)
        order = self._np.lexsort((selected, -scores[selected]))
        ranked = selected[order]
        return [(int(ids[index]), float(scores[index])) for index in ranked[:take]]


class SqliteVecIndex:
    name = "sqlite-vec"

    def __init__(self, sqlite_vec_module: Any | None = None):
        self._sqlite_vec = sqlite_vec_module if sqlite_vec_module is not None else _load_sqlite_vec()
        if self._sqlite_vec is None:
            raise SqliteVecUnavailable(
                "sqlite-vec backend requested but sqlite-vec is not installed; "
                "install openclaw-context-pack[vec] or choose numpy/python"
            )
        self.receipt: dict[str, Any] = {
            "requested": "sqlite-vec",
            "selected": "sqlite-vec",
            "fallback_reason": None,
            "hint": None,
        }

    def rebuild(self, conn: sqlite3.Connection) -> dict[str, Any]:
        return rebuild_sqlite_vec_indexes(conn)

    def search(
        self,
        conn: sqlite3.Connection,
        query_vector: Sequence[float],
        *,
        model: str,
        limit: int = 20,
        table: str = "observation_embeddings",
    ) -> list[tuple[int, float]]:
        _validate_table(table)
        if limit <= 0:
            return []
        dim = len(query_vector)
        if dim == 0:
            return []
        query_norm = l2_norm(query_vector)
        if not query_norm or not math.isfinite(query_norm):
            return []
        _enable_sqlite_vec(conn, self._sqlite_vec)
        if not _table_exists(conn, SQLITE_VEC_META_TABLE):
            raise SqliteVecIndexStale("sqlite_vec_index_missing")
        meta_columns = {
            str(row[1])
            for row in conn.execute(f"PRAGMA table_info({SQLITE_VEC_META_TABLE})")
        }
        if "stale" not in meta_columns:
            raise SqliteVecIndexStale("sqlite_vec_index_stale")
        meta = conn.execute(
            f"SELECT vec_table, source_row_count, stale FROM {SQLITE_VEC_META_TABLE} "
            "WHERE source_table = ? AND model = ? AND dim = ?",
            (table, model, dim),
        ).fetchone()
        if meta is None or not _table_exists(conn, str(meta[0])):
            raise SqliteVecIndexStale("sqlite_vec_index_missing")
        if bool(meta[2]):
            raise SqliteVecIndexStale("sqlite_vec_index_stale")
        vec_table = str(meta[0])
        source_count = int(meta[1])
        if source_count <= 0:
            return []
        rows = conn.execute(
            f'SELECT observation_id, distance FROM "{vec_table}" '
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (pack_f32(query_vector), min(max(1, int(limit)), source_count)),
        ).fetchall()
        return [(int(row[0]), 1.0 - float(row[1])) for row in rows]


class AutoVectorIndex:
    """Select a fresh persisted sqlite-vec index, then NumPy, then Python."""

    def __init__(self):
        numpy_module = _load_numpy()
        self._fallback: VectorIndex = (
            NumpyIndex(numpy_module) if numpy_module is not None else PurePythonIndex()
        )
        self._name = self._fallback.name
        self.receipt: dict[str, Any] = {
            "requested": "auto",
            "selected": self._name,
            "fallback_reason": "sqlite_vec_not_evaluated",
            "hint": None,
        }

    @property
    def name(self) -> str:
        return self._name

    def search(
        self,
        conn: sqlite3.Connection,
        query_vector: Sequence[float],
        *,
        model: str,
        limit: int = 20,
        table: str = "observation_embeddings",
    ) -> list[tuple[int, float]]:
        sqlite_vec = _load_sqlite_vec()
        if sqlite_vec is not None:
            try:
                ranked = SqliteVecIndex(sqlite_vec).search(
                    conn,
                    query_vector,
                    model=model,
                    limit=limit,
                    table=table,
                )
            except SqliteVecIndexStale as exc:
                self.receipt = {
                    "requested": "auto",
                    "selected": self._fallback.name,
                    "fallback_reason": exc.reason,
                    "hint": "run `openclaw-mem db reindex --vec --json`",
                }
            except SqliteVecUnavailable as exc:
                self.receipt = {
                    "requested": "auto",
                    "selected": self._fallback.name,
                    "fallback_reason": "sqlite_vec_unavailable",
                    "detail": str(exc),
                    "hint": "install openclaw-context-pack[vec] or use numpy/python",
                }
            else:
                self._name = "sqlite-vec"
                self.receipt = {
                    "requested": "auto",
                    "selected": "sqlite-vec",
                    "fallback_reason": None,
                    "hint": None,
                }
                return ranked
        else:
            self.receipt = {
                "requested": "auto",
                "selected": self._fallback.name,
                "fallback_reason": "sqlite_vec_not_installed",
                "hint": "install openclaw-context-pack[vec] to enable the sqlite-vec lane",
            }
        self._name = self._fallback.name
        return self._fallback.search(
            conn,
            query_vector,
            model=model,
            limit=limit,
            table=table,
        )


def create_vector_index(backend: str = "auto") -> VectorIndex:
    requested = str(backend or "auto").strip().lower()
    if requested == "python":
        return PurePythonIndex()
    if requested == "numpy":
        return NumpyIndex()
    if requested == "sqlite-vec":
        return SqliteVecIndex()
    if requested != "auto":
        raise ValueError("vector backend must be auto, sqlite-vec, numpy, or python")
    return AutoVectorIndex()
