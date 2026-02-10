"""
CLI Tests
=========

Tests for CLI argument parsing and subcommand dispatch.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness.cli import build_parser, cmd_init, cmd_run, cmd_verify
from agent_harness.config import DEFAULT_BUILTIN_TOOLS


class TestBuildParser(unittest.TestCase):
    """Test CLI argument parser construction."""

    def test_build_parser_has_subcommands(self) -> None:
        parser = build_parser()
        # Parse each subcommand to verify they exist
        args = parser.parse_args(["run"])
        self.assertEqual(args.command, "run")
        args = parser.parse_args(["verify"])
        self.assertEqual(args.command, "verify")
        args = parser.parse_args(["init"])
        self.assertEqual(args.command, "init")

    def test_run_defaults_project_dir_to_cwd(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["run"])
        self.assertEqual(args.project_dir, Path("."))

    def test_model_and_max_iterations_override(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "run", "--model", "claude-opus-4-20250514",
            "--max-iterations", "5",
        ])
        self.assertEqual(args.model, "claude-opus-4-20250514")
        self.assertEqual(args.max_iterations, 5)


class TestCmdInit(unittest.TestCase):
    """Test init subcommand."""

    def test_init_creates_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            parser = build_parser()
            args = parser.parse_args(["init", "--project-dir", tmpdir])
            cmd_init(args)
            harness_dir = Path(tmpdir) / ".agent-harness"
            self.assertTrue((harness_dir / "config.toml").exists())
            self.assertTrue((harness_dir / "prompts").is_dir())

    def test_init_refuses_overwrite(self) -> None:
        with TemporaryDirectory() as tmpdir:
            harness_dir = Path(tmpdir) / ".agent-harness"
            harness_dir.mkdir()
            (harness_dir / "config.toml").write_text("existing")
            parser = build_parser()
            args = parser.parse_args(["init", "--project-dir", tmpdir])
            with self.assertRaises(SystemExit) as ctx:
                cmd_init(args)
            self.assertEqual(ctx.exception.code, 1)

    def test_init_uses_default_builtin_tools_constant(self) -> None:
        """Test that init-generated config contains DEFAULT_BUILTIN_TOOLS."""
        with TemporaryDirectory() as tmpdir:
            parser = build_parser()
            args = parser.parse_args(["init", "--project-dir", tmpdir])
            cmd_init(args)
            config_file = Path(tmpdir) / ".agent-harness" / "config.toml"
            config_content = config_file.read_text()
            # Check that the tools from DEFAULT_BUILTIN_TOOLS appear in the config
            for tool in DEFAULT_BUILTIN_TOOLS:
                self.assertIn(tool, config_content)


class TestCmdRun(unittest.TestCase):
    """Test run subcommand."""

    def test_cmd_run_config_error_exits(self) -> None:
        with TemporaryDirectory() as tmpdir:
            # No config.toml -> ConfigError -> sys.exit(1)
            harness_dir = Path(tmpdir) / ".agent-harness"
            harness_dir.mkdir()
            parser = build_parser()
            args = parser.parse_args(["run", "--project-dir", tmpdir])
            with self.assertRaises(SystemExit) as ctx:
                cmd_run(args)
            self.assertEqual(ctx.exception.code, 1)


class TestCmdVerify(unittest.TestCase):
    """Test verify subcommand."""

    def test_cmd_verify_returns_exit_code(self) -> None:
        with TemporaryDirectory() as tmpdir:
            # Missing config will cause FAIL results -> exit(1)
            parser = build_parser()
            args = parser.parse_args(["verify", "--project-dir", tmpdir])
            with self.assertRaises(SystemExit) as ctx:
                cmd_verify(args)
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
