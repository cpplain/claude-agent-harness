"""
Prompt Loading Tests
====================

Tests for prompt loading with file: references and init file copying.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness.config import ConfigError, HarnessConfig, InitFileConfig
from agent_harness.prompts import copy_init_files, load_prompt


class TestLoadPrompt(unittest.TestCase):
    """Test prompt loading."""

    def test_inline_prompt(self) -> None:
        result = load_prompt("Do the thing.", Path("/tmp"))
        self.assertEqual(result, "Do the thing.")

    def test_file_reference(self) -> None:
        with TemporaryDirectory() as tmpdir:
            prompt_file = Path(tmpdir) / "coding.md"
            prompt_file.write_text("Build the app.")
            result = load_prompt("file:coding.md", Path(tmpdir))
            self.assertEqual(result, "Build the app.")

    def test_file_reference_subdirectory(self) -> None:
        with TemporaryDirectory() as tmpdir:
            prompts_dir = Path(tmpdir) / "prompts"
            prompts_dir.mkdir()
            (prompts_dir / "init.md").write_text("Initialize.")
            result = load_prompt("file:prompts/init.md", Path(tmpdir))
            self.assertEqual(result, "Initialize.")

    def test_missing_file_raises(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(ConfigError):
                load_prompt("file:nonexistent.md", Path(tmpdir))


class TestCopyInitFiles(unittest.TestCase):
    """Test init file copying."""

    def test_copies_file_to_harness_dir(self) -> None:
        with TemporaryDirectory() as tmpdir:
            harness_dir = Path(tmpdir) / ".agent-harness"
            harness_dir.mkdir()
            prompts_dir = harness_dir / "prompts"
            prompts_dir.mkdir()
            (prompts_dir / "spec.txt").write_text("App specification")

            config = HarnessConfig(
                harness_dir=harness_dir,
                init_files=[InitFileConfig(source="prompts/spec.txt", dest="spec.txt")],
            )
            copy_init_files(config)
            self.assertEqual((harness_dir / "spec.txt").read_text(), "App specification")

    def test_skips_existing_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            harness_dir = Path(tmpdir) / ".agent-harness"
            harness_dir.mkdir()
            (harness_dir / "source_spec.txt").write_text("New content")
            (harness_dir / "spec.txt").write_text("Existing content")

            config = HarnessConfig(
                harness_dir=harness_dir,
                init_files=[InitFileConfig(source="source_spec.txt", dest="spec.txt")],
            )
            copy_init_files(config)
            self.assertEqual((harness_dir / "spec.txt").read_text(), "Existing content")

    def test_creates_parent_directories(self) -> None:
        with TemporaryDirectory() as tmpdir:
            harness_dir = Path(tmpdir) / ".agent-harness"
            harness_dir.mkdir()
            (harness_dir / "data.txt").write_text("Data")

            config = HarnessConfig(
                harness_dir=harness_dir,
                init_files=[
                    InitFileConfig(source="data.txt", dest="sub/dir/data.txt")
                ],
            )
            copy_init_files(config)
            self.assertEqual(
                (harness_dir / "sub" / "dir" / "data.txt").read_text(), "Data"
            )

    def test_no_init_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config = HarnessConfig(
                harness_dir=Path(tmpdir),
                init_files=[],
            )
            copy_init_files(config)  # Should not raise


if __name__ == "__main__":
    unittest.main()
