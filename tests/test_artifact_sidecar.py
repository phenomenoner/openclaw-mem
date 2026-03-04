import stat
from pathlib import Path

import pytest

from openclaw_mem.artifact_sidecar import (
    fetch_artifact,
    parse_artifact_handle,
    peek_artifact,
    stash_artifact,
)


def _artifact_paths(root: Path, sha256_hex: str, *, gzip_blob: bool) -> tuple[Path, Path]:
    a, b = sha256_hex[:2], sha256_hex[2:4]
    blob_ext = ".txt.gz" if gzip_blob else ".txt"
    blob = root / "blobs" / "sha256" / a / b / f"{sha256_hex}{blob_ext}"
    meta = root / "meta" / "sha256" / a / b / f"{sha256_hex}.json"
    return blob, meta


def test_artifact_stash_fetch_peek_and_caps(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    text = ("HEAD-" + ("A" * 220) + "\n" + ("B" * 220) + "-TAIL")

    stash = stash_artifact(text.encode("utf-8"), root=root, kind="tool_output")
    assert stash["schema"] == "openclaw-mem.artifact.stash.v1"

    handle = stash["handle"]
    fetch = fetch_artifact(handle, root=root, mode="headtail", max_chars=120)
    assert fetch["schema"] == "openclaw-mem.artifact.fetch.v1"
    assert len(fetch["text"]) <= 120
    assert "HEAD-" in fetch["text"]
    assert "-TAIL" in fetch["text"]

    peek = peek_artifact(handle, root=root, preview_chars=80)
    assert peek["schema"] == "openclaw-mem.artifact.peek.v1"
    assert len(peek["preview"]) <= 80

    blob, meta = _artifact_paths(root, stash["sha256"], gzip_blob=False)
    assert blob.exists()
    assert meta.exists()
    assert stat.S_IMODE(blob.stat().st_mode) == 0o600
    assert stat.S_IMODE(meta.stat().st_mode) == 0o600


def test_artifact_handle_parser_is_strict() -> None:
    valid = "ocm_artifact:v1:sha256:" + ("a" * 64)
    assert parse_artifact_handle(valid) == ("a" * 64)

    bad = [
        "",
        "ocm_artifact:v1:sha256:" + ("A" * 64),
        "ocm_artifact:v2:sha256:" + ("a" * 64),
        "ocm_artifact:v1:sha1:" + ("a" * 64),
        "ocm_artifact:v1:sha256:" + ("a" * 63),
        "ocm_artifact:v1:sha256:" + ("g" * 64),
    ]
    for item in bad:
        with pytest.raises(ValueError):
            parse_artifact_handle(item)


def test_artifact_gzip_blob_path_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    text = "gzip roundtrip payload\n" + ("x" * 200)

    stash = stash_artifact(text.encode("utf-8"), root=root, compress=True)
    blob, meta = _artifact_paths(root, stash["sha256"], gzip_blob=True)

    assert blob.exists(), "expected .txt.gz blob"
    assert meta.exists(), "expected metadata json"

    fetched = fetch_artifact(stash["handle"], root=root, mode="head", max_chars=10_000)
    assert fetched["text"] == text
