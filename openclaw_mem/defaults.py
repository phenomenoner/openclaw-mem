"""Centralized defaults + env overrides.

Goal: prevent scattered hardcodes (models/base URLs) that silently drift.

Env vars (preferred):
- OPENCLAW_MEM_OPENAI_BASE_URL
- OPENCLAW_MEM_EMBED_MODEL
- OPENCLAW_MEM_SUMMARY_MODEL
- OPENCLAW_MEM_RERANK_MODEL

These are intentionally narrow and stable.
"""

from __future__ import annotations

import os

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_EMBED_MODEL = "text-embedding-3-small"
DEFAULT_SUMMARY_MODEL = "gpt-5.2"
DEFAULT_RERANK_MODEL = "jina-reranker-v2-base-multilingual"


def _env(name: str, default: str) -> str:
    v = (os.getenv(name) or "").strip()
    return v or default


def openai_base_url() -> str:
    return _env("OPENCLAW_MEM_OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)


def embed_model() -> str:
    return _env("OPENCLAW_MEM_EMBED_MODEL", DEFAULT_EMBED_MODEL)


def summary_model() -> str:
    return _env("OPENCLAW_MEM_SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL)


def rerank_model() -> str:
    return _env("OPENCLAW_MEM_RERANK_MODEL", DEFAULT_RERANK_MODEL)
