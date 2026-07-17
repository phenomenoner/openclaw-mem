from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from openclaw_mem.cli import build_parser
from openclaw_mem.core import config
from openclaw_mem.core.embeddings import embedding_provider_name


CONFIG_ENV_KEYS = tuple(config._ENV_KEYS.values()) + ("OPENCLAW_MEM_CONFIG",)


def _clear_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CONFIG_ENV_KEYS:
        monkeypatch.delenv(name, raising=False)


def test_config_priority_env_then_toml_then_builtin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_config_env(monkeypatch)
    path = tmp_path / "config.toml"
    path.write_text(
        'db_path = "from-file.sqlite"\n'
        'default_scope = "file-scope"\n'
        'vector_backend = "python"\n'
        'embed_provider = "local"\n'
        "\n[pack]\n"
        "budget_tokens = 777\n"
        "\n[scoring]\n"
        'profile = "composite"\n'
        "[scoring.recency]\n"
        "enabled = false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_MEM_DB", "from-env.sqlite")
    monkeypatch.setenv("OPENCLAW_MEM_PACK_BUDGET_TOKENS", "888")

    resolved = config.resolve_config(path)

    assert resolved["db_path"] == "from-env.sqlite"
    assert resolved["default_scope"] == "file-scope"
    assert resolved["vector_backend"] == "python"
    assert resolved["embed_provider"] == "local"
    assert resolved["pack"]["budget_tokens"] == 888
    assert resolved["scoring"]["profile"] == "composite"
    assert resolved["scoring"]["recency"]["enabled"] is False


def test_invalid_env_values_fall_back_without_corrupting_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_config_env(monkeypatch)
    path = tmp_path / "config.toml"
    path.write_text(
        'vector_backend = "numpy"\nembed_provider = "local"\n'
        "[pack]\nbudget_tokens = 640\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_MEM_VECTOR_BACKEND", "bogus")
    monkeypatch.setenv("OPENCLAW_MEM_EMBED_PROVIDER", "bogus")
    monkeypatch.setenv("OPENCLAW_MEM_PACK_BUDGET_TOKENS", "-1")

    resolved = config.resolve_config(path)

    assert resolved["vector_backend"] == "auto"
    assert resolved["embed_provider"] == "openai"
    assert resolved["pack"]["budget_tokens"] == 1200


def test_quota_config_nested_values_and_environment_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_config_env(monkeypatch)
    path = tmp_path / "config.toml"
    path.write_text(
        "[quota]\nenabled = false\n"
        "[quota.preference]\nmin = 2\n"
        "[quota.decision]\nmin = 3\n"
        "[quota.event]\nmax_ratio = 0.25\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_MEM_QUOTA_ENABLED", "true")
    monkeypatch.setenv("OPENCLAW_MEM_QUOTA_PREFERENCE_MIN", "4")

    resolved = config.resolve_config(path)

    assert resolved["quota"] == {
        "enabled": True,
        "preference": {"min": 4},
        "decision": {"min": 3},
        "event": {"max_ratio": 0.25},
    }


def test_ensure_config_only_fills_missing_keys_and_is_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    original = '# operator choice\ndb_path = "keep.sqlite"\n\n[pack]\nbudget_tokens = 321\n'
    path.write_text(original, encoding="utf-8")
    values = config.built_in_defaults()
    values["db_path"] = "replace.sqlite"

    first = config.ensure_config(values, path)
    first_content = path.read_text(encoding="utf-8")
    second = config.ensure_config(values, path)

    assert first["changed"] is True
    assert first["added"] == [
        "default_scope",
        "vector_backend",
        "embed_provider",
        "scoring.profile",
        "scoring.relevance.enabled",
        "scoring.importance.enabled",
        "scoring.recency.enabled",
        "scoring.use.enabled",
        "scoring.state.enabled",
        "taxonomy.enabled",
        "quota.enabled",
        "quota.preference.min",
        "quota.decision.min",
        "quota.event.max_ratio",
    ]
    assert 'db_path = "keep.sqlite"' in first_content
    assert "# operator choice" in first_content
    assert config.resolve_config(path)["pack"]["budget_tokens"] == 321
    assert second == {"path": str(path), "changed": False, "added": []}
    assert path.read_text(encoding="utf-8") == first_content


def test_parser_and_embedding_provider_consume_resolved_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_config_env(monkeypatch)
    path = tmp_path / "config.toml"
    path.write_text(
        'default_scope = "configured"\nvector_backend = "numpy"\nembed_provider = "local"\n'
        "[pack]\nbudget_tokens = 456\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_MEM_CONFIG", str(path))

    parser = build_parser()

    assert parser.parse_args(["recall", "needle"]).scope == "configured"
    assert parser.parse_args(["recall", "needle"]).vector_backend == "numpy"
    assert parser.parse_args(["store", "memory"]).scope == "configured"
    assert parser.parse_args(["pack", "--query", "needle"]).budget_tokens == 456
    assert embedding_provider_name() == "local"


def _cli(env: dict[str, str], *args: str) -> tuple[int, dict[str, object], str]:
    completed = subprocess.run(
        [sys.executable, "-m", "openclaw_mem", *args],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    payload = json.loads(completed.stdout)
    return completed.returncode, payload, completed.stderr


def test_clean_home_init_store_recall_and_idempotency(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ)
    for name in CONFIG_ENV_KEYS:
        env.pop(name, None)
    env.pop("OPENCLAW_HOME", None)
    env.pop("OPENCLAW_STATE_DIR", None)
    env.pop("CLAWDBOT_STATE_DIR", None)
    env.pop("OPENAI_API_KEY", None)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["OPENCLAW_MEM_CONFIG"] = str(home / ".openclaw-mem" / "config.toml")

    code, initialized, stderr = _cli(env, "init", "--json")
    assert code == 0, stderr
    assert initialized["kind"] == "openclaw-mem.init.v1"
    assert initialized["ok"] is True
    assert initialized["config_changed"] is True
    assert set(initialized["capabilities"]) == {
        "numpy",
        "sqlite_vec",
        "fastembed",
        "api_key",
        "trigram_migrated",
        "git_scope",
    }
    assert initialized["capabilities"]["trigram_migrated"] is True
    assert Path(str(initialized["db"])).exists()
    assert Path(str(initialized["config_path"])).exists()

    code, stored, stderr = _cli(
        env,
        "store",
        "clean-home memory needle",
        "--no-file-write",
        "--json",
    )
    assert code == 0, stderr
    assert stored["ok"] is True

    code, recalled, stderr = _cli(
        env, "recall", "clean-home memory needle", "--mode", "lexical", "--json"
    )
    assert code == 0, stderr
    assert recalled["kind"] == "openclaw-mem.recall.v1"
    assert recalled["results"][0]["summary"] == "clean-home memory needle"

    code, second_init, stderr = _cli(env, "init", "--json")
    assert code == 0, stderr
    assert second_init["config_changed"] is False
    assert second_init["config_added"] == []
