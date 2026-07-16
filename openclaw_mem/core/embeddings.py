"""Embedding provider helpers shared by core retrieval surfaces."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from openclaw_mem import defaults
from openclaw_mem.core.config import resolve_config

EMBED_PROVIDER_ENV = "OPENCLAW_MEM_EMBED_PROVIDER"
LOCAL_FASTEMBED_MODEL = "BAAI/bge-small-en-v1.5"
LOCAL_FASTEMBED_MODEL_ID = "fastembed:bge-small-en-v1.5"


class EmbeddingProviderError(RuntimeError):
    """Raised when a selected embedding provider cannot be constructed."""


class MissingEmbeddingCredentials(EmbeddingProviderError):
    """Raised when the remote provider is selected without credentials."""


class EmbeddingProvider(Protocol):
    provider_name: str
    model_id: str

    def embed(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]: ...


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
    provider_name = "openai"

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = (base_url or defaults.openai_base_url()).rstrip("/")
        self.model_id = ""

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


class LocalFastEmbedProvider:
    """Lazy optional local provider backed by fastembed's ONNX runtime."""

    provider_name = "local"
    model_id = LOCAL_FASTEMBED_MODEL_ID

    def __init__(self) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EmbeddingProviderError(
                "local embedding provider requires the 'embed' extra: "
                "pip install openclaw-context-pack[embed]"
            ) from exc
        try:
            self._model = TextEmbedding(model_name=LOCAL_FASTEMBED_MODEL)
        except Exception as exc:
            raise EmbeddingProviderError(
                f"failed to initialize local embedding model {LOCAL_FASTEMBED_MODEL!r}: {exc}"
            ) from exc

    def embed(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        del model
        return [
            value.tolist() if hasattr(value, "tolist") else list(value)
            for value in self._model.embed(list(texts))
        ]


def embedding_provider_name(explicit: Optional[str] = None) -> str:
    configured = resolve_config().get("embed_provider", "openai")
    value = str(explicit or os.getenv(EMBED_PROVIDER_ENV) or configured).strip().lower()
    if value not in {"openai", "local"}:
        raise EmbeddingProviderError(
            f"unsupported embedding provider {value!r}; expected openai or local"
        )
    return value


def create_embedding_provider(
    *,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    openai_client_factory: Callable[..., EmbeddingProvider] = OpenAIEmbeddingsClient,
) -> EmbeddingProvider:
    selected = embedding_provider_name(provider)
    if selected == "local":
        return LocalFastEmbedProvider()
    if not str(api_key or "").strip():
        raise MissingEmbeddingCredentials(
            "OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json"
        )
    client = openai_client_factory(api_key=str(api_key), base_url=base_url)
    client.provider_name = "openai"
    client.model_id = str(model or defaults.embed_model())
    return client
