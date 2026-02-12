"""
Verification Tests
==================

Tests for each verification check with mocked environment.
"""

import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from agent_harness.config import HarnessConfig, McpServerConfig, ToolsConfig, InitFileConfig
from agent_harness.verify import (
    check_api_connectivity,
    check_authentication,
    check_claude_cli,
    check_config_exists,
    check_config_valid,
    check_file_references,
    check_mcp_commands,
    check_project_dir,
    check_python_version,
    run_verify,
)


class TestCheckPythonVersion(unittest.TestCase):
    def test_current_version_passes(self) -> None:
        result = check_python_version()
        self.assertEqual(result.status, "PASS")

    @patch("agent_harness.verify.sys")
    def test_old_version_fails(self, mock_sys: MagicMock) -> None:
        mock_sys.version_info = (3, 9, 0)
        result = check_python_version()
        self.assertEqual(result.status, "FAIL")


class TestCheckAuthentication(unittest.TestCase):
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False)
    def test_api_key_passes(self) -> None:
        result = check_authentication()
        self.assertEqual(result.status, "PASS")

    @patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "token"}, clear=False)
    def test_oauth_token_passes(self) -> None:
        result = check_authentication()
        self.assertEqual(result.status, "PASS")

    @patch.dict(os.environ, {}, clear=True)
    def test_no_auth_fails(self) -> None:
        result = check_authentication()
        self.assertEqual(result.status, "FAIL")


class TestCheckClaudeCli(unittest.TestCase):
    @patch("agent_harness.verify.shutil.which", return_value=None)
    def test_not_found_fails(self, mock_which: MagicMock) -> None:
        """Test that when CLI is not on PATH and SDK import fails, check fails."""
        with patch("builtins.__import__", side_effect=ImportError("No module named 'claude_agent_sdk'")):
            result = check_claude_cli()
            self.assertEqual(result.status, "FAIL")

    @patch("agent_harness.verify.shutil.which", return_value=None)
    def test_bundled_cli_passes(self, mock_which: MagicMock) -> None:
        """Test that bundled CLI in SDK is detected when not on PATH."""
        with TemporaryDirectory() as tmpdir:
            # Create mock SDK structure
            sdk_dir = Path(tmpdir) / "claude_agent_sdk"
            bundled_dir = sdk_dir / "_bundled"
            bundled_dir.mkdir(parents=True)
            (bundled_dir / "claude").touch()

            mock_sdk = MagicMock()
            mock_sdk.__file__ = str(sdk_dir / "__init__.py")

            with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
                result = check_claude_cli()
                self.assertEqual(result.status, "PASS")
                self.assertIn("bundled with SDK", result.message)


class TestCheckConfigExists(unittest.TestCase):
    def test_exists(self) -> None:
        with TemporaryDirectory() as tmpdir:
            harness_dir = Path(tmpdir) / ".agent-harness"
            harness_dir.mkdir()
            (harness_dir / "config.toml").write_text("")
            result = check_config_exists(harness_dir)
            self.assertEqual(result.status, "PASS")

    def test_missing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result = check_config_exists(Path(tmpdir) / ".agent-harness")
            self.assertEqual(result.status, "FAIL")


class TestCheckConfigValid(unittest.TestCase):
    def test_valid_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text("")
            result, config = check_config_valid(Path(tmpdir))
            self.assertEqual(result.status, "PASS")
            self.assertIsNotNone(config)

    def test_invalid_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text("invalid [[[")
            result, config = check_config_valid(Path(tmpdir))
            self.assertEqual(result.status, "FAIL")
            self.assertIsNone(config)


class TestCheckFileReferences(unittest.TestCase):
    def test_no_init_files(self) -> None:
        config = HarnessConfig(harness_dir=Path("/tmp"))
        result = check_file_references(config)
        self.assertEqual(result.status, "PASS")

    def test_missing_init_file_source(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(
                harness_dir=config_dir,
                init_files=[InitFileConfig(source="missing.txt", dest="out.txt")],
            )
            result = check_file_references(config)
            self.assertEqual(result.status, "FAIL")

    def test_existing_init_file_source(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            (config_dir / "spec.txt").write_text("content")
            config = HarnessConfig(
                harness_dir=config_dir,
                init_files=[InitFileConfig(source="spec.txt", dest="out.txt")],
            )
            result = check_file_references(config)
            self.assertEqual(result.status, "PASS")


class TestCheckMcpCommands(unittest.TestCase):
    def test_no_servers(self) -> None:
        config = HarnessConfig()
        result = check_mcp_commands(config)
        self.assertEqual(result.status, "PASS")

    @patch("agent_harness.verify.shutil.which", return_value=None)
    def test_missing_command_warns(self, mock_which: MagicMock) -> None:
        config = HarnessConfig(
            tools=ToolsConfig(
                mcp_servers={
                    "test": McpServerConfig(command="nonexistent-cmd", args=[])
                }
            )
        )
        result = check_mcp_commands(config)
        self.assertEqual(result.status, "WARN")

    @patch("agent_harness.verify.shutil.which", return_value="/usr/bin/npx")
    def test_found_command_passes(self, mock_which: MagicMock) -> None:
        config = HarnessConfig(
            tools=ToolsConfig(
                mcp_servers={
                    "puppeteer": McpServerConfig(command="npx", args=[])
                }
            )
        )
        result = check_mcp_commands(config)
        self.assertEqual(result.status, "PASS")

    @patch("agent_harness.verify.shutil.which")
    def test_npx_missing_warns_with_auto_download_message(self, mock_which: MagicMock) -> None:
        """Test that missing npx-only gets a specific auto-download message."""
        # Return None for npx (not found), but this is the only server
        def which_side_effect(cmd: str) -> None:
            return None
        mock_which.side_effect = which_side_effect

        config = HarnessConfig(
            tools=ToolsConfig(
                mcp_servers={
                    "puppeteer": McpServerConfig(command="npx", args=[])
                }
            )
        )
        result = check_mcp_commands(config)
        self.assertEqual(result.status, "WARN")
        self.assertIn("auto-download", result.message)
        self.assertIn("npx not found", result.message)

    @patch("agent_harness.verify.shutil.which")
    def test_npx_and_other_missing(self, mock_which: MagicMock) -> None:
        """Test that when npx and other commands are missing, other command is mentioned."""
        # Return None for everything (not found)
        def which_side_effect(cmd: str) -> None:
            return None
        mock_which.side_effect = which_side_effect

        config = HarnessConfig(
            tools=ToolsConfig(
                mcp_servers={
                    "puppeteer": McpServerConfig(command="npx", args=[]),
                    "other": McpServerConfig(command="other-cmd", args=[])
                }
            )
        )
        result = check_mcp_commands(config)
        self.assertEqual(result.status, "WARN")
        # Should mention "other" command, not just npx
        self.assertIn("other-cmd", result.message)
        self.assertIn("Commands not found", result.message)


class TestCheckProjectDir(unittest.TestCase):
    def test_existing_writable(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result = check_project_dir(Path(tmpdir))
            self.assertEqual(result.status, "PASS")

    def test_nonexistent_with_writable_parent(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result = check_project_dir(Path(tmpdir) / "new_dir")
            self.assertEqual(result.status, "PASS")


class TestCheckApiConnectivity(unittest.TestCase):
    def test_api_connectivity_timeout(self) -> None:
        """Verify that a slow API check times out with a FAIL result."""
        import warnings

        def fake_run(coro):
            coro.close()
            raise asyncio.TimeoutError()

        with patch("asyncio.run", side_effect=fake_run), \
             warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            result = check_api_connectivity()
            self.assertEqual(result.status, "FAIL")
            self.assertIn("Timed out", result.message)


class TestRunVerify(unittest.TestCase):
    def test_full_verify_with_valid_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text("")
            results = run_verify(Path(tmpdir))
            # Should have at least the basic checks
            self.assertGreater(len(results), 4)

            # Verify specific check names are present
            check_names = [result.name for result in results]
            self.assertIn("Config file", check_names)
            self.assertIn("Config validation", check_names)
            self.assertIn("Python version", check_names)

            # Verify at least the "Config file" check passes
            config_file_result = next(r for r in results if r.name == "Config file")
            self.assertEqual(config_file_result.status, "PASS")


if __name__ == "__main__":
    unittest.main()
