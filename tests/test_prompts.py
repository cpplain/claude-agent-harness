"""
Prompt Loading Tests
====================

Tests for prompt loading with file: references.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness.config import ConfigError, resolve_file_reference


class TestResolveFileReference(unittest.TestCase):
    """Test file: reference resolution."""

    def test_inline_prompt(self) -> None:
        result = resolve_file_reference("Do the thing.", Path("/tmp"))
        self.assertEqual(result, "Do the thing.")

    def test_file_reference(self) -> None:
        with TemporaryDirectory() as tmpdir:
            prompt_file = Path(tmpdir) / "coding.md"
            prompt_file.write_text("Build the app.")
            result = resolve_file_reference("file:coding.md", Path(tmpdir))
            self.assertEqual(result, "Build the app.")

    def test_file_reference_subdirectory(self) -> None:
        with TemporaryDirectory() as tmpdir:
            prompts_dir = Path(tmpdir) / "prompts"
            prompts_dir.mkdir()
            (prompts_dir / "init.md").write_text("Initialize.")
            result = resolve_file_reference("file:prompts/init.md", Path(tmpdir))
            self.assertEqual(result, "Initialize.")

    def test_missing_file_raises(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(ConfigError):
                resolve_file_reference("file:nonexistent.md", Path(tmpdir))

    def test_path_traversal_raises(self) -> None:
        with TemporaryDirectory() as tmpdir:
            # Create a file outside the harness dir
            outside_file = Path(tmpdir) / "secret.txt"
            outside_file.write_text("secret")
            harness_dir = Path(tmpdir) / "harness"
            harness_dir.mkdir()
            with self.assertRaises(ConfigError):
                resolve_file_reference("file:../secret.txt", harness_dir)


if __name__ == "__main__":
    unittest.main()
