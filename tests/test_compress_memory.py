import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

# Import from parent directory
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from compress_memory import (
    OpenAIClient,
    CompressError,
    validate_date,
    atomic_append,
    compress_daily_note,
)


class MockOpenAIClient:
    """Mock OpenAI client for testing."""

    def __init__(self, response: str = "Test summary"):
        self.response = response
        self.calls = []

    def complete(self, prompt: str, model: str, max_tokens: int, temperature: float) -> str:
        self.calls.append({"prompt": prompt, "model": model, "max_tokens": max_tokens, "temperature": temperature})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class TestValidateDate(unittest.TestCase):
    def test_valid_date(self):
        self.assertEqual(validate_date("2026-02-05"), "2026-02-05")
        self.assertEqual(validate_date("2026-01-01"), "2026-01-01")

    def test_invalid_format(self):
        with self.assertRaises(CompressError):
            validate_date("2026/02/05")
        with self.assertRaises(CompressError):
            validate_date("invalid")
        with self.assertRaises(CompressError):
            validate_date("2026-13-01")  # invalid month


class TestAtomicAppend(unittest.TestCase):
    def test_append_to_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.md"
            atomic_append(file_path, "Hello\n")
            self.assertEqual(file_path.read_text(), "Hello\n")

    def test_append_to_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.md"
            file_path.write_text("Existing\n")
            atomic_append(file_path, "New\n")
            self.assertEqual(file_path.read_text(), "Existing\nNew\n")

    def test_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "subdir" / "test.md"
            atomic_append(file_path, "Content\n")
            self.assertTrue(file_path.exists())
            self.assertEqual(file_path.read_text(), "Content\n")


class TestCompressDailyNote(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        self.memory_dir = self.workspace / "memory"
        self.memory_dir.mkdir()
        self.memory_file = self.workspace / "MEMORY.md"
        self.prompt_file = self.workspace / "prompt.txt"
        self.prompt_file.write_text("Compress this:\n")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_compress_success(self):
        # Create daily note
        daily_file = self.memory_dir / "2026-02-05.md"
        daily_file.write_text("# Notes\nSome content")

        # Mock client
        client = MockOpenAIClient("Summary text")

        # Run compression
        result = compress_daily_note(
            date="2026-02-05",
            memory_dir=self.memory_dir,
            memory_file=self.memory_file,
            prompt_file=self.prompt_file,
            client=client,
            model="gpt-4.1",
            max_tokens=700,
            temperature=0.2,
            dry_run=False,
        )

        # Check result
        self.assertTrue(result["ok"])
        self.assertTrue(result["appended"])
        self.assertEqual(result["date"], "2026-02-05")

        # Check file was written
        self.assertTrue(self.memory_file.exists())
        content = self.memory_file.read_text()
        self.assertIn("## 2026-02-05 Summary", content)
        self.assertIn("Summary text", content)

        # Check client was called correctly
        self.assertEqual(len(client.calls), 1)
        self.assertIn("2026-02-05", client.calls[0]["prompt"])

    def test_skip_if_no_daily_note(self):
        client = MockOpenAIClient()

        result = compress_daily_note(
            date="2026-02-05",
            memory_dir=self.memory_dir,
            memory_file=self.memory_file,
            prompt_file=self.prompt_file,
            client=client,
            model="gpt-4.1",
            max_tokens=700,
            temperature=0.2,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertIn("No daily note", result["reason"])
        self.assertEqual(len(client.calls), 0)

    def test_skip_if_empty_daily_note(self):
        daily_file = self.memory_dir / "2026-02-05.md"
        daily_file.write_text("   \n\n   ")  # only whitespace

        client = MockOpenAIClient()

        result = compress_daily_note(
            date="2026-02-05",
            memory_dir=self.memory_dir,
            memory_file=self.memory_file,
            prompt_file=self.prompt_file,
            client=client,
            model="gpt-4.1",
            max_tokens=700,
            temperature=0.2,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertIn("empty", result["reason"])

    def test_skip_if_already_summarized(self):
        daily_file = self.memory_dir / "2026-02-05.md"
        daily_file.write_text("Content")

        # Pre-write summary to MEMORY.md
        self.memory_file.write_text("## 2026-02-05 Summary\nAlready done\n")

        client = MockOpenAIClient()

        result = compress_daily_note(
            date="2026-02-05",
            memory_dir=self.memory_dir,
            memory_file=self.memory_file,
            prompt_file=self.prompt_file,
            client=client,
            model="gpt-4.1",
            max_tokens=700,
            temperature=0.2,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertIn("already appears", result["reason"])

    def test_dry_run_mode(self):
        daily_file = self.memory_dir / "2026-02-05.md"
        daily_file.write_text("Content")

        client = MockOpenAIClient("Dry run summary")

        result = compress_daily_note(
            date="2026-02-05",
            memory_dir=self.memory_dir,
            memory_file=self.memory_file,
            prompt_file=self.prompt_file,
            client=client,
            model="gpt-4.1",
            max_tokens=700,
            temperature=0.2,
            dry_run=True,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["summary"], "Dry run summary")

        # File should NOT be written
        self.assertFalse(self.memory_file.exists())

    def test_invalid_date_format(self):
        client = MockOpenAIClient()

        with self.assertRaises(CompressError):
            compress_daily_note(
                date="invalid",
                memory_dir=self.memory_dir,
                memory_file=self.memory_file,
                prompt_file=self.prompt_file,
                client=client,
                model="gpt-4.1",
                max_tokens=700,
                temperature=0.2,
            )

    def test_missing_prompt_file(self):
        daily_file = self.memory_dir / "2026-02-05.md"
        daily_file.write_text("Content")

        self.prompt_file.unlink()  # Remove prompt file

        client = MockOpenAIClient()

        with self.assertRaises(CompressError):
            compress_daily_note(
                date="2026-02-05",
                memory_dir=self.memory_dir,
                memory_file=self.memory_file,
                prompt_file=self.prompt_file,
                client=client,
                model="gpt-4.1",
                max_tokens=700,
                temperature=0.2,
            )


if __name__ == "__main__":
    unittest.main()
