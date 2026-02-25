from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from openclaw_mem.vector import rank_rrf


@dataclass(frozen=True)
class DocsChunk:
    chunk_id: str
    heading_path: str
    title: str
    text: str
    ordinal: int


_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*$")
_FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")
_FRONTMATTER_DATE_RE = re.compile(r"^\s*date\s*:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\s*$", re.IGNORECASE)
_PATH_DATE_RE = re.compile(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)")


def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "root"


def detect_doc_kind(path: str) -> str:
    p = (path or "").lower()
    name = Path(path or "").name.lower()

    if "/decisions/" in p or name.startswith("decision"):
        return "decision"
    if "/captain-log/" in p or "captain-log" in p or "/logs/" in p:
        return "log"
    if "/specs/" in p or "spec" in name or "prd" in name:
        return "spec"
    if "/roadmap" in p or "roadmap" in name:
        return "roadmap"
    return "doc"


def parse_ts_hint(text: str, file_path: str) -> Optional[str]:
    lines = (text or "").splitlines()
    in_frontmatter = False

    if lines and lines[0].strip() == "---":
        in_frontmatter = True

    if in_frontmatter:
        for line in lines[1:40]:
            if line.strip() == "---":
                break
            m = _FRONTMATTER_DATE_RE.match(line)
            if m:
                return m.group(1)

    m2 = _PATH_DATE_RE.search(file_path or "")
    if not m2:
        return None
    return f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"


def _split_by_headings(markdown_text: str, *, default_title: str) -> List[Tuple[str, str, List[str]]]:
    lines = (markdown_text or "").splitlines()
    sections: List[Tuple[str, str, List[str]]] = []

    heading_stack: List[str] = []
    current_heading_path = ""
    current_title = default_title or "(root)"
    current_lines: List[str] = []

    in_code = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_code = not in_code
            current_lines.append(line)
            continue

        if not in_code:
            m = _HEADING_RE.match(line)
            if m:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append((current_heading_path, current_title, current_lines))

                level = len(m.group(1))
                heading = re.sub(r"\s+#+\s*$", "", (m.group(2) or "").strip()).strip() or "(untitled)"

                heading_stack = heading_stack[: max(0, level - 1)]
                heading_stack.append(heading)

                current_heading_path = " / ".join(heading_stack)
                current_title = heading
                current_lines = []
                continue

        current_lines.append(line)

    tail = "\n".join(current_lines).strip()
    if tail:
        sections.append((current_heading_path, current_title, current_lines))

    return sections


def _chunk_section_text(raw_lines: List[str], *, max_chars: int) -> List[str]:
    text = "\n".join(raw_lines).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf.strip():
            chunks.append(buf.strip())
        buf = ""

    for p in paragraphs:
        if len(p) > max_chars:
            flush()
            i = 0
            while i < len(p):
                chunks.append(p[i : i + max_chars].strip())
                i += max_chars
            continue

        candidate = p if not buf else f"{buf}\n\n{p}"
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            flush()
            buf = p

    flush()
    return chunks


def chunk_markdown(markdown_text: str, *, default_title: str, max_chars: int = 1400) -> List[DocsChunk]:
    sections = _split_by_headings(markdown_text, default_title=default_title)
    out: List[DocsChunk] = []

    section_name_counts: Dict[str, int] = {}
    for heading_path, title, raw_lines in sections:
        chunks = _chunk_section_text(raw_lines, max_chars=max(200, int(max_chars)))
        if not chunks:
            continue

        base = slugify(heading_path or "root")
        section_name_counts[base] = section_name_counts.get(base, 0) + 1
        seen_count = section_name_counts[base]

        section_key = base if seen_count == 1 else f"{base}~{seen_count}"

        for idx, chunk_text in enumerate(chunks, start=1):
            out.append(
                DocsChunk(
                    chunk_id=f"{section_key}:{idx:03d}",
                    heading_path=heading_path,
                    title=title,
                    text=chunk_text,
                    ordinal=idx,
                )
            )

    return out


def make_doc_id(repo: str, rel_path: str) -> str:
    repo_part = (repo or "local").strip() or "local"
    path_part = (rel_path or "").strip().lstrip("/")
    return f"{repo_part}:{path_part}"


def chunk_content_hash(*, heading_path: str, title: str, text: str) -> str:
    material = "\n".join([(heading_path or "").strip(), (title or "").strip(), (text or "").strip()])
    return hashlib.sha1(material.encode("utf-8")).hexdigest()


def make_record_ref(*, repo: str, rel_path: str, chunk_id: str) -> str:
    return f"doc:{(repo or 'local').strip()}:{(rel_path or '').lstrip('/')}#{chunk_id}"


def fuse_rankings_rrf(
    *,
    fts_ids: Sequence[int],
    vec_ids: Sequence[int],
    k: int = 60,
    limit: int = 20,
) -> List[Tuple[int, float]]:
    return rank_rrf([list(fts_ids), list(vec_ids)], k=max(1, int(k)), limit=max(1, int(limit)))


def rrf_components(
    *,
    fused: Iterable[Tuple[int, float]],
    fts_ids: Sequence[int],
    vec_ids: Sequence[int],
    k: int,
) -> List[Dict[str, object]]:
    fts_rank = {rid: idx for idx, rid in enumerate(fts_ids)}
    vec_rank = {rid: idx for idx, rid in enumerate(vec_ids)}

    out: List[Dict[str, object]] = []
    for rid, score in fused:
        fr = fts_rank.get(rid)
        vr = vec_rank.get(rid)
        fts_rrf = (1.0 / (k + fr + 1)) if fr is not None else 0.0
        vec_rrf = (1.0 / (k + vr + 1)) if vr is not None else 0.0
        out.append(
            {
                "id": int(rid),
                "rrf_score": float(score),
                "fts_rank": (int(fr) + 1) if fr is not None else None,
                "vec_rank": (int(vr) + 1) if vr is not None else None,
                "fts_rrf": float(fts_rrf),
                "vec_rrf": float(vec_rrf),
            }
        )
    return out
