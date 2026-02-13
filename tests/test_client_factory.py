"""
Client Factory Tests
====================

Tests for client creation, settings generation, and sandbox/permission configuration.
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
    SecurityConfig,
    ToolsConfig,
)
from agent_harness.client_factory import create_client


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

            # Verify default options are passed
            call_kwargs = mock_client_cls.call_args
            options = call_kwargs.kwargs.get("options") or call_kwargs.args[0]
            self.assertEqual(options.permission_mode, "acceptEdits")
            self.assertTrue(options.sandbox["enabled"])

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
            self.assertNotIn("env", options.mcp_servers["puppeteer"])

    @patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "oauth-token-test"})
    @patch("agent_harness.client_factory.ClaudeSDKClient")
    def test_oauth_token_creates_client(self, mock_client_cls: MagicMock) -> None:
        """Test that OAuth token authentication works."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(
                harness_dir=config_dir,
                project_dir=Path(tmpdir),
            )
            # Remove API key to ensure we're testing OAuth
            os.environ.pop("ANTHROPIC_API_KEY", None)
            create_client(config)
            mock_client_cls.assert_called_once()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"})
    @patch("agent_harness.client_factory.ClaudeSDKClient")
    def test_settings_passed_as_json_string(self, mock_client_cls: MagicMock) -> None:
        """Test that settings are passed as a JSON string, not a file path."""
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

            # Verify settings is a JSON string, not a file path
            self.assertIsInstance(options.settings, str)
            self.assertTrue(options.settings.startswith("{"))
            self.assertTrue(options.settings.endswith("}"))

            # Verify it parses as valid JSON with expected structure
            settings = json.loads(options.settings)
            self.assertIn("permissions", settings)
            self.assertIn("allow", settings["permissions"])
            self.assertIn("deny", settings["permissions"])
            self.assertEqual(settings["permissions"]["allow"], [])
            self.assertEqual(settings["permissions"]["deny"], [])


if __name__ == "__main__":
    unittest.main()
