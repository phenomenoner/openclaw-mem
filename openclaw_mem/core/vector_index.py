"""Exact vector-index backends with an optional NumPy acceleration lane."""

from __future__ import annotations

import math
import sqlite3
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from openclaw_mem.vector import l2_norm, rank_cosine


SUPPORTED_TABLES = {"observation_embeddings", "observation_embeddings_en"}
_CACHE_MAX_ENTRIES = 8


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


def create_vector_index(backend: str = "auto") -> VectorIndex:
    requested = str(backend or "auto").strip().lower()
    if requested == "python":
        return PurePythonIndex()
    if requested == "numpy":
        return NumpyIndex()
    if requested != "auto":
        raise ValueError("vector backend must be auto, python, or numpy")
    numpy_module = _load_numpy()
    return NumpyIndex(numpy_module) if numpy_module is not None else PurePythonIndex()
