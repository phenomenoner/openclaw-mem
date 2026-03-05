import stat
import json
import tempfile
import unittest
from pathlib import Path

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


class TestArtifactSidecar(unittest.TestCase):
    def test_artifact_stash_fetch_peek_and_caps(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            root = tmp_path / "artifacts"
            text = ("HEAD-" + ("A" * 220) + "\n" + ("B" * 220) + "-TAIL")

            stash = stash_artifact(text.encode("utf-8"), root=root, kind="tool_output")
            self.assertEqual(stash["schema"], "openclaw-mem.artifact.stash.v1")

            handle = stash["handle"]
            fetch = fetch_artifact(handle, root=root, mode="headtail", max_chars=120)
            self.assertEqual(fetch["schema"], "openclaw-mem.artifact.fetch.v1")
            self.assertLessEqual(len(fetch["text"]), 120)
            self.assertIn("HEAD-", fetch["text"])
            self.assertIn("-TAIL", fetch["text"])

            peek = peek_artifact(handle, root=root, preview_chars=80)
            self.assertEqual(peek["schema"], "openclaw-mem.artifact.peek.v1")
            self.assertLessEqual(len(peek["preview"]), 80)

            blob, meta = _artifact_paths(root, stash["sha256"], gzip_blob=False)
            self.assertTrue(blob.exists())
            self.assertTrue(meta.exists())
            self.assertEqual(stat.S_IMODE(blob.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(meta.stat().st_mode), 0o600)

    def test_artifact_handle_parser_is_strict(self) -> None:
        valid = "ocm_artifact:v1:sha256:" + ("a" * 64)
        self.assertEqual(parse_artifact_handle(valid), ("a" * 64))

        bad = [
            "",
            "ocm_artifact:v1:sha256:" + ("A" * 64),
            "ocm_artifact:v2:sha256:" + ("a" * 64),
            "ocm_artifact:v1:sha1:" + ("a" * 64),
            "ocm_artifact:v1:sha256:" + ("a" * 63),
            "ocm_artifact:v1:sha256:" + ("g" * 64),
        ]
        for item in bad:
            with self.assertRaises(ValueError):
                parse_artifact_handle(item)

    def test_artifact_gzip_blob_path_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            root = tmp_path / "artifacts"
            text = "gzip roundtrip payload\n" + ("x" * 200)

            stash = stash_artifact(text.encode("utf-8"), root=root, compress=True)
            blob, meta = _artifact_paths(root, stash["sha256"], gzip_blob=True)

            self.assertTrue(blob.exists(), "expected .txt.gz blob")
            self.assertTrue(meta.exists(), "expected metadata json")

            fetched = fetch_artifact(stash["handle"], root=root, mode="head", max_chars=10_000)
            self.assertEqual(fetched["text"], text)


    def test_meta_blob_path_cannot_escape_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            root = tmp_path / "artifacts"

            good = "GOOD\n"
            secret = "SECRET\n"

            stash = stash_artifact(good.encode("utf-8"), root=root)
            _blob, meta = _artifact_paths(root, stash["sha256"], gzip_blob=False)

            # Write a secret file outside artifacts_root.
            secret_path = tmp_path / "secret.txt"
            secret_path.write_text(secret, encoding="utf-8")

            # Tamper metadata to point outside root; fetch must NOT follow it.
            obj = json.loads(meta.read_text(encoding="utf-8"))
            obj["blob"] = "../secret.txt"
            meta.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            fetched = fetch_artifact(stash["handle"], root=root, mode="head", max_chars=1000)
            self.assertEqual(fetched["text"], good)


if __name__ == "__main__":
    unittest.main()
