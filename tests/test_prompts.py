"""
Prompt Loading Tests
====================

Tests for prompt loading with file: references and init file copying.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness.config import ConfigError, HarnessConfig, InitFileConfig, resolve_file_reference
from agent_harness.runner import copy_init_files


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
            copy_init_files(config)
            # Verify no files were created (only the tmpdir itself exists)
            self.assertEqual(list(Path(tmpdir).iterdir()), [])

    def test_copy_init_files_missing_source_skips(self) -> None:
        """Missing source file should log warning and continue."""
        import logging
        with TemporaryDirectory() as tmpdir:
            harness_dir = Path(tmpdir) / ".agent-harness"
            harness_dir.mkdir()
            config = HarnessConfig(
                harness_dir=harness_dir,
                init_files=[InitFileConfig(source="missing.txt", dest="out.txt")],
            )
            # Should not raise, should log warning
            with self.assertLogs("agent_harness.runner", level=logging.WARNING) as cm:
                copy_init_files(config)
            self.assertTrue(any("missing.txt" in msg for msg in cm.output))
            # Dest should NOT have been created
            self.assertFalse((harness_dir / "out.txt").exists())

    def test_copy_init_files_path_traversal_source_raises(self) -> None:
        """Test that path traversal in source is rejected."""
        with TemporaryDirectory() as tmpdir:
            # Create a file outside harness dir
            outside_file = Path(tmpdir) / "secret.txt"
            outside_file.write_text("secret data")

            harness_dir = Path(tmpdir) / ".agent-harness"
            harness_dir.mkdir()

            config = HarnessConfig(
                harness_dir=harness_dir,
                init_files=[InitFileConfig(source="../secret.txt", dest="out.txt")],
            )

            with self.assertRaises(ConfigError) as ctx:
                copy_init_files(config)
            self.assertIn("source escapes harness directory", str(ctx.exception))

    def test_copy_init_files_path_traversal_dest_raises(self) -> None:
        """Test that path traversal in dest is rejected."""
        with TemporaryDirectory() as tmpdir:
            harness_dir = Path(tmpdir) / ".agent-harness"
            harness_dir.mkdir()
            (harness_dir / "source.txt").write_text("data")

            config = HarnessConfig(
                harness_dir=harness_dir,
                init_files=[InitFileConfig(source="source.txt", dest="../outside.txt")],
            )

            with self.assertRaises(ConfigError) as ctx:
                copy_init_files(config)
            self.assertIn("dest escapes harness directory", str(ctx.exception))

    def test_copy_init_files_absolute_path_source_raises(self) -> None:
        """Test that absolute paths escaping harness dir are rejected."""
        with TemporaryDirectory() as tmpdir:
            # Create a file at absolute path outside harness dir
            outside_file = Path(tmpdir) / "outside.txt"
            outside_file.write_text("outside data")

            harness_dir = Path(tmpdir) / ".agent-harness"
            harness_dir.mkdir()

            config = HarnessConfig(
                harness_dir=harness_dir,
                init_files=[InitFileConfig(source=str(outside_file), dest="out.txt")],
            )

            with self.assertRaises(ConfigError) as ctx:
                copy_init_files(config)
            self.assertIn("source escapes harness directory", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
