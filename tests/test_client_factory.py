"""
Client Factory Tests
====================

Tests for client creation, settings generation, and hook installation.
"""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from agent_harness.config import (
    HarnessConfig,
    McpServerConfig,
    PermissionRulesConfig,
    SandboxConfig,
    SecurityConfig,
    ToolsConfig,
)
from agent_harness.client_factory import (
    _write_settings,
    create_client,
)


class TestWriteSettings(unittest.TestCase):
    """Test settings file writing."""

    def test_writes_json_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(harness_dir=config_dir)
            settings_file = _write_settings(config)
            self.assertTrue(settings_file.exists())
            data = json.loads(settings_file.read_text())
            # Settings file now only contains permissions
            self.assertIn("permissions", data)
            self.assertIn("allow", data["permissions"])
            self.assertIn("deny", data["permissions"])

    def test_writes_to_config_dir(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(harness_dir=config_dir)
            settings_file = _write_settings(config)
            self.assertEqual(settings_file, config_dir / ".claude_settings.json")

    def test_write_settings_skips_unchanged(self) -> None:
        """Test that _write_settings doesn't rewrite file when content is unchanged."""
        import time
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(harness_dir=config_dir)

            # First write
            settings_file = _write_settings(config)
            self.assertTrue(settings_file.exists())

            # Record mtime (wait briefly to ensure any write would change mtime)
            first_mtime = os.path.getmtime(settings_file)
            time.sleep(0.01)  # 10ms to ensure mtime resolution

            # Second write with same config
            _write_settings(config)
            second_mtime = os.path.getmtime(settings_file)

            # File should not have been rewritten (mtime unchanged)
            self.assertEqual(first_mtime, second_mtime)


class TestCreateClient(unittest.TestCase):
    """Test full client creation."""

    @patch.dict(os.environ, {}, clear=True)
    def test_no_auth_raises(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(
                harness_dir=config_dir,
                project_dir=Path(tmpdir),
            )
            # Remove any auth env vars
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
            with self.assertRaises(ValueError) as ctx:
                create_client(config)
            self.assertIn("No authentication", str(ctx.exception))

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"})
    @patch("agent_harness.client_factory.ClaudeSDKClient")
    def test_creates_client_with_defaults(self, mock_client_cls: MagicMock) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(
                harness_dir=config_dir,
                project_dir=Path(tmpdir),
            )
            create_client(config)
            mock_client_cls.assert_called_once()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"})
    @patch("agent_harness.client_factory.ClaudeSDKClient")
    def test_permission_mode_passed_on_options(self, mock_client_cls: MagicMock) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(
                harness_dir=config_dir,
                project_dir=Path(tmpdir),
                security=SecurityConfig(permission_mode="plan"),
            )
            create_client(config)
            call_kwargs = mock_client_cls.call_args
            options = call_kwargs.kwargs.get("options") or call_kwargs.args[0]
            self.assertEqual(options.permission_mode, "plan")

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"})
    @patch("agent_harness.client_factory.ClaudeSDKClient")
    def test_sandbox_passed_on_options(self, mock_client_cls: MagicMock) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(
                harness_dir=config_dir,
                project_dir=Path(tmpdir),
            )
            create_client(config)
            call_kwargs = mock_client_cls.call_args
            options = call_kwargs.kwargs.get("options") or call_kwargs.args[0]
            # Sandbox should be passed as dict
            self.assertIsNotNone(options.sandbox)
            self.assertIsInstance(options.sandbox, dict)
            self.assertTrue(options.sandbox["enabled"])

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"})
    @patch("agent_harness.client_factory.ClaudeSDKClient")
    def test_allow_unsandboxed_commands_defaults_to_false(self, mock_client_cls: MagicMock) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(
                harness_dir=config_dir,
                project_dir=Path(tmpdir),
            )
            create_client(config)
            call_kwargs = mock_client_cls.call_args
            options = call_kwargs.kwargs.get("options") or call_kwargs.args[0]
            self.assertFalse(options.sandbox["allowUnsandboxedCommands"])

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"})
    @patch("agent_harness.client_factory.ClaudeSDKClient")
    def test_mcp_servers_passed_through(self, mock_client_cls: MagicMock) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(
                harness_dir=config_dir,
                project_dir=Path(tmpdir),
                tools=ToolsConfig(
                    mcp_servers={
                        "puppeteer": McpServerConfig(
                            command="npx", args=["puppeteer-mcp-server"]
                        )
                    }
                ),
            )
            create_client(config)
            call_kwargs = mock_client_cls.call_args
            options = call_kwargs.kwargs.get("options") or call_kwargs.args[0]
            self.assertIsNotNone(options.mcp_servers)
            self.assertIn("puppeteer", options.mcp_servers)


if __name__ == "__main__":
    unittest.main()
