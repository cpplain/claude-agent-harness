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
    BashSecurityConfig,
    ExtraValidatorConfig,
    HarnessConfig,
    McpServerConfig,
    SecurityConfig,
    SandboxConfig,
    ToolsConfig,
)
from agent_harness.client_factory import (
    _build_permission_rules,
    _build_settings,
    _write_settings,
    _build_allowed_tools,
    _build_mcp_servers,
    create_client,
)


class TestBuildPermissionRules(unittest.TestCase):
    """Test permission rule generation."""

    def test_default_tools(self) -> None:
        config = HarnessConfig()
        rules = _build_permission_rules(config)
        self.assertIn("Read(./**)", rules)
        self.assertIn("Write(./**)", rules)
        self.assertIn("Edit(./**)", rules)
        self.assertIn("Glob(./**)", rules)
        self.assertIn("Grep(./**)", rules)
        self.assertIn("Bash(*)", rules)

    def test_custom_paths(self) -> None:
        config = HarnessConfig(
            security=SecurityConfig(allowed_paths=["./src/**", "./tests/**"])
        )
        rules = _build_permission_rules(config)
        self.assertIn("Read(./src/**)", rules)
        self.assertIn("Read(./tests/**)", rules)
        self.assertIn("Write(./src/**)", rules)

    def test_mcp_server_wildcard(self) -> None:
        config = HarnessConfig(
            tools=ToolsConfig(
                mcp_servers={
                    "puppeteer": McpServerConfig(command="npx", args=["puppeteer-mcp-server"])
                }
            )
        )
        rules = _build_permission_rules(config)
        self.assertIn("mcp__puppeteer__*", rules)


class TestBuildSettings(unittest.TestCase):
    """Test settings dict generation."""

    def test_default_settings(self) -> None:
        config = HarnessConfig()
        settings = _build_settings(config)
        self.assertTrue(settings["sandbox"]["enabled"])
        self.assertTrue(settings["sandbox"]["autoAllowBashIfSandboxed"])
        self.assertEqual(settings["permissions"]["defaultMode"], "acceptEdits")

    def test_sandbox_disabled(self) -> None:
        config = HarnessConfig(
            security=SecurityConfig(sandbox=SandboxConfig(enabled=False))
        )
        settings = _build_settings(config)
        self.assertFalse(settings["sandbox"]["enabled"])


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
            self.assertIn("sandbox", data)
            self.assertIn("permissions", data)

    def test_writes_to_config_dir(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(harness_dir=config_dir)
            settings_file = _write_settings(config)
            self.assertEqual(settings_file, config_dir / ".claude_settings.json")


class TestBuildAllowedTools(unittest.TestCase):
    """Test allowed tools list generation."""

    def test_builtin_tools(self) -> None:
        config = HarnessConfig()
        tools = _build_allowed_tools(config)
        self.assertEqual(tools[:6], ["Read", "Write", "Edit", "Glob", "Grep", "Bash"])

    def test_mcp_tools_included(self) -> None:
        config = HarnessConfig(
            tools=ToolsConfig(
                mcp_servers={
                    "puppeteer": McpServerConfig(command="npx", args=[])
                }
            )
        )
        tools = _build_allowed_tools(config)
        self.assertIn("mcp__puppeteer__*", tools)


class TestBuildMcpServers(unittest.TestCase):
    """Test MCP server config generation."""

    def test_no_servers(self) -> None:
        config = HarnessConfig()
        servers = _build_mcp_servers(config)
        self.assertEqual(servers, {})

    def test_single_server(self) -> None:
        config = HarnessConfig(
            tools=ToolsConfig(
                mcp_servers={
                    "puppeteer": McpServerConfig(
                        command="npx", args=["puppeteer-mcp-server"]
                    )
                }
            )
        )
        servers = _build_mcp_servers(config)
        self.assertEqual(servers["puppeteer"]["command"], "npx")
        self.assertEqual(servers["puppeteer"]["args"], ["puppeteer-mcp-server"])


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
    def test_bash_hook_installed_when_configured(self, mock_client_cls: MagicMock) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(
                harness_dir=config_dir,
                project_dir=Path(tmpdir),
                security=SecurityConfig(
                    bash=BashSecurityConfig(
                        allowed_commands=["ls", "cat"],
                        extra_validators={},
                    )
                ),
            )
            create_client(config)
            call_kwargs = mock_client_cls.call_args
            options = call_kwargs.kwargs.get("options") or call_kwargs.args[0]
            # The options should have hooks
            self.assertIsNotNone(options.hooks)
            self.assertIn("PreToolUse", options.hooks)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"})
    @patch("agent_harness.client_factory.ClaudeSDKClient")
    def test_no_bash_hook_when_not_configured(self, mock_client_cls: MagicMock) -> None:
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
            # No hooks should be set
            self.assertFalse(hasattr(options, "hooks") and options.hooks)

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
