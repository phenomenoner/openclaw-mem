"""Embedding provider helpers shared by core retrieval surfaces."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from openclaw_mem import defaults


def _read_config() -> Dict[str, Any]:
    configured = str(os.getenv("OPENCLAW_CONFIG_PATH") or "").strip()
    path = Path(configured).expanduser() if configured else Path.home() / ".openclaw" / "openclaw.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def get_api_key(env_var: str = "OPENAI_API_KEY") -> Optional[str]:
    value = str(os.getenv(env_var) or "").strip()
    if value:
        return value
    config = _read_config()
    key = (
        config.get("agents", {})
        .get("defaults", {})
        .get("memorySearch", {})
        .get("remote", {})
        .get("apiKey")
    )
    return key if isinstance(key, str) and key.strip() else None


class OpenAIEmbeddingsClient:
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = (base_url or defaults.openai_base_url()).rstrip("/")

    def embed(self, texts: List[str], model: str) -> List[List[float]]:
        request = urllib.request.Request(
            self.base_url + "/embeddings",
            data=json.dumps({"model": model, "input": texts}).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI embeddings API error ({exc.code}): {error_body}") from exc
        except Exception as exc:
            raise RuntimeError(f"Error calling OpenAI embeddings API: {exc}") from exc
        value = json.loads(body)
        return [item["embedding"] for item in value.get("data", [])]
