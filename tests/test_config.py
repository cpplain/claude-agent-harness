"""
Configuration Tests
===================

Tests for config loading, validation, defaults, and file: resolution.
"""

import logging
import logging.handlers
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent_harness.config import (
    ConfigError,
    DEFAULT_BUILTIN_TOOLS,
    HarnessConfig,
    load_config,
    resolve_file_reference,
)


class TestConfigDefaults(unittest.TestCase):
    """Test default configuration values."""

    def test_default_model(self) -> None:
        config = HarnessConfig()
        self.assertEqual(config.model, "claude-sonnet-4-5-20250929")

    def test_default_max_turns(self) -> None:
        config = HarnessConfig()
        self.assertEqual(config.max_turns, 1000)

    def test_default_auto_continue_delay(self) -> None:
        config = HarnessConfig()
        self.assertEqual(config.auto_continue_delay, 3)

    def test_default_tools(self) -> None:
        config = HarnessConfig()
        self.assertEqual(config.tools.builtin, DEFAULT_BUILTIN_TOOLS)

    def test_default_security(self) -> None:
        config = HarnessConfig()
        self.assertEqual(config.security.permission_mode, "acceptEdits")
        self.assertTrue(config.security.sandbox.enabled)
        self.assertFalse(config.security.sandbox.allow_unsandboxed_commands)
        self.assertEqual(config.security.permissions.allow, [])
        self.assertEqual(config.security.permissions.deny, [])

    def test_default_tracking(self) -> None:
        config = HarnessConfig()
        self.assertEqual(config.tracking.type, "none")

    def test_default_phases(self) -> None:
        config = HarnessConfig()
        self.assertEqual(config.phases, [])


class TestFileReference(unittest.TestCase):
    """Test file: reference resolution."""

    def test_inline_string_returned_as_is(self) -> None:
        result = resolve_file_reference("Hello world", Path("/tmp"))
        self.assertEqual(result, "Hello world")

    def test_file_reference_loads_content(self) -> None:
        with TemporaryDirectory() as tmpdir:
            prompt_file = Path(tmpdir) / "system.md"
            prompt_file.write_text("You are a coding assistant.")
            result = resolve_file_reference("file:system.md", Path(tmpdir))
            self.assertEqual(result, "You are a coding assistant.")

    def test_file_reference_missing_file_raises(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(ConfigError):
                resolve_file_reference("file:missing.md", Path(tmpdir))


class TestLoadConfig(unittest.TestCase):
    """Test TOML loading and merging."""

    def _write_config(self, tmpdir: str, content: str) -> Path:
        """Write a config.toml and return the project dir."""
        project_dir = Path(tmpdir)
        config_dir = project_dir / ".agent-harness"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(content)
        return project_dir

    def test_minimal_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_dir = self._write_config(tmpdir, "")
            config = load_config(project_dir)
            self.assertEqual(config.model, "claude-sonnet-4-5-20250929")
            self.assertEqual(config.max_turns, 1000)

    def test_custom_model(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_dir = self._write_config(tmpdir, 'model = "claude-opus-4-6"')
            config = load_config(project_dir)
            self.assertEqual(config.model, "claude-opus-4-6")

    def test_cli_override_model(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_dir = self._write_config(tmpdir, 'model = "claude-opus-4-6"')
            config = load_config(
                project_dir, cli_overrides={"model": "claude-haiku-4-5-20251001"}
            )
            self.assertEqual(config.model, "claude-haiku-4-5-20251001")

    def test_cli_override_none_does_not_override(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_dir = self._write_config(tmpdir, 'model = "claude-opus-4-6"')
            config = load_config(
                project_dir, cli_overrides={"model": None}
            )
            self.assertEqual(config.model, "claude-opus-4-6")

    def test_cli_override_max_iterations(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_dir = self._write_config(tmpdir, "max_iterations = 10")
            config = load_config(
                project_dir, cli_overrides={"max_iterations": 5}
            )
            self.assertEqual(config.max_iterations, 5)

    def test_missing_config_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(ConfigError) as ctx:
                load_config(Path(tmpdir))
            self.assertIn("Config file not found", str(ctx.exception))

    def test_invalid_toml(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            config_dir = project_dir / ".agent-harness"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text("invalid [[[toml")
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("Failed to parse", str(ctx.exception))

    def test_system_prompt_file_reference(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            config_dir = project_dir / ".agent-harness"
            config_dir.mkdir()
            prompts_dir = config_dir / "prompts"
            prompts_dir.mkdir()
            (prompts_dir / "system.md").write_text("Be helpful.")
            (config_dir / "config.toml").write_text(
                'system_prompt = "file:prompts/system.md"'
            )
            config = load_config(project_dir)
            self.assertEqual(config.system_prompt, "Be helpful.")

    def test_phase_prompt_file_reference(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            config_dir = project_dir / ".agent-harness"
            config_dir.mkdir()
            prompts_dir = config_dir / "prompts"
            prompts_dir.mkdir()
            (prompts_dir / "init.md").write_text("Initialize stuff.")
            toml_content = """
[[phases]]
name = "initializer"
prompt = "file:prompts/init.md"
run_once = true
"""
            (config_dir / "config.toml").write_text(toml_content)
            config = load_config(project_dir)
            self.assertEqual(len(config.phases), 1)
            self.assertEqual(config.phases[0].prompt, "Initialize stuff.")
            self.assertTrue(config.phases[0].run_once)

    def test_harness_dir_defaults_to_project_dir_subdir(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_dir = self._write_config(tmpdir, "")
            config = load_config(project_dir)
            self.assertEqual(config.harness_dir, project_dir / ".agent-harness")

    def test_harness_dir_override(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_dir = self._write_config(tmpdir, "")
            harness_dir = project_dir / ".agent-harness"
            config = load_config(project_dir, harness_dir=harness_dir)
            self.assertEqual(config.harness_dir, harness_dir)

    def test_tools_with_mcp_servers(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[tools]
builtin = ["Read", "Write", "Bash"]

[tools.mcp_servers.puppeteer]
command = "npx"
args = ["puppeteer-mcp-server"]
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(config.tools.builtin, ["Read", "Write", "Bash"])
            self.assertIn("puppeteer", config.tools.mcp_servers)
            self.assertEqual(config.tools.mcp_servers["puppeteer"].command, "npx")

    def test_sandbox_config_with_network(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[security.sandbox]
enabled = true
allow_unsandboxed_commands = false
excluded_commands = ["curl", "wget"]

[security.sandbox.network]
allowed_domains = ["github.com", "npmjs.org"]
allow_local_binding = true
allow_unix_sockets = ["/var/run/docker.sock"]
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertTrue(config.security.sandbox.enabled)
            self.assertFalse(config.security.sandbox.allow_unsandboxed_commands)
            self.assertEqual(config.security.sandbox.excluded_commands, ["curl", "wget"])
            self.assertEqual(config.security.sandbox.network.allowed_domains, ["github.com", "npmjs.org"])
            self.assertTrue(config.security.sandbox.network.allow_local_binding)
            self.assertEqual(config.security.sandbox.network.allow_unix_sockets, ["/var/run/docker.sock"])

    def test_permissions_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[security.permissions]
allow = ["Bash(npm *)", "Bash(git *)"]
deny = ["Bash(curl *)", "Read(./.env)"]
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(config.security.permissions.allow, ["Bash(npm *)", "Bash(git *)"])
            self.assertEqual(config.security.permissions.deny, ["Bash(curl *)", "Read(./.env)"])

    def test_default_permission_mode_accepted(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[security]
permission_mode = "default"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(config.security.permission_mode, "default")

    def test_tracking_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[tracking]
type = "json_checklist"
file = "feature_list.json"
passing_field = "passes"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(config.tracking.type, "json_checklist")
            self.assertEqual(config.tracking.file, "feature_list.json")

    def test_init_files_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[[init_files]]
source = "prompts/app_spec.txt"
dest = "app_spec.txt"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(len(config.init_files), 1)
            self.assertEqual(config.init_files[0].source, "prompts/app_spec.txt")
            self.assertEqual(config.init_files[0].dest, "app_spec.txt")

    def test_error_recovery_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
max_consecutive_errors = 3
initial_backoff_seconds = 2.0
max_backoff_seconds = 60.0
backoff_multiplier = 3.0
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(config.error_recovery.max_consecutive_errors, 3)
            self.assertEqual(config.error_recovery.initial_backoff_seconds, 2.0)
            self.assertEqual(config.error_recovery.max_backoff_seconds, 60.0)
            self.assertEqual(config.error_recovery.backoff_multiplier, 3.0)


class TestConfigValidation(unittest.TestCase):
    """Test configuration validation."""

    def _write_config(self, tmpdir: str, content: str) -> Path:
        project_dir = Path(tmpdir)
        config_dir = project_dir / ".agent-harness"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(content)
        return project_dir

    def test_invalid_permission_mode(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[security]
permission_mode = "invalid"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("permission_mode", str(ctx.exception))

    def test_invalid_tracking_type(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[tracking]
type = "invalid"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("tracking.type", str(ctx.exception))

    def test_tracking_file_required_for_json_checklist(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[tracking]
type = "json_checklist"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("tracking.file", str(ctx.exception))

    def test_phase_missing_name(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[[phases]]
prompt = "Do stuff"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("phases[0].name", str(ctx.exception))

    def test_phase_missing_prompt(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[[phases]]
name = "init"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("phases[0].prompt", str(ctx.exception))

    def test_init_file_missing_source(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[[init_files]]
dest = "app_spec.txt"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("init_files[0].source", str(ctx.exception))

    def test_phase_invalid_condition_prefix(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[[phases]]
name = "init"
prompt = "Do stuff"
condition = "unknown:something"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("phases[0].condition must start with", str(ctx.exception))

    def test_phase_valid_condition_prefix_exists(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[[phases]]
name = "init"
prompt = "Do stuff"
condition = "exists:file.txt"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(config.phases[0].condition, "exists:file.txt")

    def test_phase_valid_condition_prefix_not_exists(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[[phases]]
name = "init"
prompt = "Do stuff"
condition = "not_exists:file.txt"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(config.phases[0].condition, "not_exists:file.txt")

    def test_missing_file_reference(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = 'system_prompt = "file:missing.md"'
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("does not exist", str(ctx.exception))

    def test_error_recovery_max_consecutive_errors_negative(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
max_consecutive_errors = -1
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("error_recovery.max_consecutive_errors must be positive", str(ctx.exception))

    def test_error_recovery_max_consecutive_errors_zero(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
max_consecutive_errors = 0
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("error_recovery.max_consecutive_errors must be positive", str(ctx.exception))

    def test_error_recovery_initial_backoff_zero(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
initial_backoff_seconds = 0
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("error_recovery.initial_backoff_seconds must be positive", str(ctx.exception))

    def test_error_recovery_initial_backoff_negative(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
initial_backoff_seconds = -5
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("error_recovery.initial_backoff_seconds must be positive", str(ctx.exception))

    def test_error_recovery_max_backoff_less_than_initial(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
initial_backoff_seconds = 10
max_backoff_seconds = 5
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("error_recovery.max_backoff_seconds must be >= initial_backoff_seconds", str(ctx.exception))

    def test_error_recovery_max_backoff_equals_initial_accepted(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
initial_backoff_seconds = 10
max_backoff_seconds = 10
"""
            project_dir = self._write_config(tmpdir, toml_content)
            # Should load successfully - equal values are allowed
            config = load_config(project_dir)
            self.assertEqual(config.error_recovery.initial_backoff_seconds, 10.0)
            self.assertEqual(config.error_recovery.max_backoff_seconds, 10.0)

    def test_error_recovery_backoff_multiplier_one_accepted(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
backoff_multiplier = 1.0
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(config.error_recovery.backoff_multiplier, 1.0)

    def test_error_recovery_backoff_multiplier_below_one(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
backoff_multiplier = 0.99
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("error_recovery.backoff_multiplier must be >= 1.0", str(ctx.exception))

    def test_error_recovery_backoff_multiplier_half(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
backoff_multiplier = 0.5
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("error_recovery.backoff_multiplier must be >= 1.0", str(ctx.exception))

    def test_max_iterations_zero_raises(self) -> None:
        """Test that max_iterations=0 raises validation error."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
max_iterations = 0
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("max_iterations must be positive when set", str(ctx.exception))

    def test_max_iterations_negative_raises(self) -> None:
        """Test that negative max_iterations raises validation error."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
max_iterations = -5
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("max_iterations must be positive when set", str(ctx.exception))

    def test_max_iterations_positive_accepted(self) -> None:
        """Test that positive max_iterations is accepted."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
max_iterations = 10
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(config.max_iterations, 10)

    def test_max_iterations_none_accepted(self) -> None:
        """Test that max_iterations=None is accepted (unlimited)."""
        with TemporaryDirectory() as tmpdir:
            toml_content = ""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertIsNone(config.max_iterations)

    def test_duplicate_phase_names_raises(self) -> None:
        """Test that duplicate phase names raise validation error."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[[phases]]
name = "setup"
prompt = "First setup"

[[phases]]
name = "build"
prompt = "Build something"

[[phases]]
name = "setup"
prompt = "Second setup"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("Duplicate phase name", str(ctx.exception))
            self.assertIn("setup", str(ctx.exception))

    def test_unique_phase_names_accepted(self) -> None:
        """Test that unique phase names are accepted."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[[phases]]
name = "setup"
prompt = "Setup"

[[phases]]
name = "build"
prompt = "Build"

[[phases]]
name = "deploy"
prompt = "Deploy"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(len(config.phases), 3)
            self.assertEqual([p.name for p in config.phases], ["setup", "build", "deploy"])


class TestMcpServerEnv(unittest.TestCase):
    """Test MCP server env field."""

    def _write_config(self, tmpdir: str, content: str) -> Path:
        project_dir = Path(tmpdir)
        config_dir = project_dir / ".agent-harness"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(content)
        return project_dir

    def test_mcp_server_with_env(self) -> None:
        """Test that env dict is parsed correctly from TOML."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[tools.mcp_servers.test_server]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-puppeteer"]

[tools.mcp_servers.test_server.env]
API_KEY = "secret123"
PORT = "8080"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertIn("test_server", config.tools.mcp_servers)
            server = config.tools.mcp_servers["test_server"]
            self.assertEqual(server.env, {"API_KEY": "secret123", "PORT": "8080"})

    def test_mcp_server_without_env_defaults_empty(self) -> None:
        """Test that missing env defaults to empty dict."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[tools.mcp_servers.test_server]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-puppeteer"]
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertIn("test_server", config.tools.mcp_servers)
            server = config.tools.mcp_servers["test_server"]
            self.assertEqual(server.env, {})

    @patch.dict(os.environ, {"MY_API_KEY": "expanded_secret", "MY_PORT": "9090"})
    def test_mcp_server_env_var_expansion(self) -> None:
        """Test that ${VAR} syntax in env values is expanded."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[tools.mcp_servers.test_server]
command = "npx"
args = ["-y", "test-server"]

[tools.mcp_servers.test_server.env]
API_KEY = "${MY_API_KEY}"
PORT = "${MY_PORT}"
STATIC = "no-expansion"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            server = config.tools.mcp_servers["test_server"]
            self.assertEqual(server.env["API_KEY"], "expanded_secret")
            self.assertEqual(server.env["PORT"], "9090")
            self.assertEqual(server.env["STATIC"], "no-expansion")

    def test_mcp_server_env_unset_var_warns(self) -> None:
        """Test that undefined env vars trigger a warning."""
        import logging
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[tools.mcp_servers.test_server]
command = "npx"
args = []

[tools.mcp_servers.test_server.env]
MISSING = "${UNLIKELY_TO_EXIST_VAR_12345}"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertLogs("agent_harness.config", level=logging.WARNING) as cm:
                load_config(project_dir)
            self.assertTrue(any("undefined variable" in msg for msg in cm.output))

    def test_mcp_server_env_unset_var_preserved(self) -> None:
        """Test that ${VAR} for unset vars is left as-is by expandvars."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[tools.mcp_servers.test_server]
command = "npx"
args = []

[tools.mcp_servers.test_server.env]
MISSING = "${UNLIKELY_TO_EXIST_VAR_12345}"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            server = config.tools.mcp_servers["test_server"]
            # os.path.expandvars leaves unset vars as-is
            self.assertEqual(server.env["MISSING"], "${UNLIKELY_TO_EXIST_VAR_12345}")

    @patch.dict(os.environ, {"EMPTY_VAR": ""})
    def test_mcp_server_env_empty_expansion_warns(self) -> None:
        """Test that expansion to empty string triggers a warning."""
        import logging
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[tools.mcp_servers.test_server]
command = "npx"
args = []

[tools.mcp_servers.test_server.env]
API_KEY = "${EMPTY_VAR}"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertLogs("agent_harness.config", level=logging.WARNING) as cm:
                config = load_config(project_dir)
            # Should warn about empty expansion
            self.assertTrue(any("expanded to empty string" in msg for msg in cm.output))
            # Should still set the value to empty string
            server = config.tools.mcp_servers["test_server"]
            self.assertEqual(server.env["API_KEY"], "")


class TestNumericValidation(unittest.TestCase):
    """Test type-checking for numeric config values (C2)."""

    def _write_config(self, tmpdir: str, content: str) -> Path:
        project_dir = Path(tmpdir)
        config_dir = project_dir / ".agent-harness"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(content)
        return project_dir

    def test_max_turns_string_raises_clear_error(self) -> None:
        """Test that max_turns = 'string' raises ConfigError, not TypeError."""
        with TemporaryDirectory() as tmpdir:
            toml_content = 'max_turns = "string"'
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("max_turns must be an integer", str(ctx.exception))
            self.assertNotIn("TypeError", type(ctx.exception).__name__)

    def test_auto_continue_delay_string_raises_clear_error(self) -> None:
        """Test that auto_continue_delay = 'string' raises ConfigError."""
        with TemporaryDirectory() as tmpdir:
            toml_content = 'auto_continue_delay = "5"'
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("auto_continue_delay must be an integer", str(ctx.exception))

    def test_max_iterations_string_raises_clear_error(self) -> None:
        """Test that max_iterations = 'string' raises ConfigError."""
        with TemporaryDirectory() as tmpdir:
            toml_content = 'max_iterations = "10"'
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("max_iterations must be an integer", str(ctx.exception))

    def test_error_recovery_max_consecutive_errors_string_raises(self) -> None:
        """Test that error_recovery.max_consecutive_errors = 'string' raises ConfigError."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
max_consecutive_errors = "5"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("error_recovery.max_consecutive_errors must be an integer", str(ctx.exception))

    def test_error_recovery_initial_backoff_string_raises(self) -> None:
        """Test that error_recovery.initial_backoff_seconds = 'string' raises ConfigError."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
initial_backoff_seconds = "5.0"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("error_recovery.initial_backoff_seconds must be a number", str(ctx.exception))

    def test_error_recovery_max_backoff_string_raises(self) -> None:
        """Test that error_recovery.max_backoff_seconds = 'string' raises ConfigError."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
max_backoff_seconds = "120.0"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("error_recovery.max_backoff_seconds must be a number", str(ctx.exception))

    def test_error_recovery_backoff_multiplier_string_raises(self) -> None:
        """Test that error_recovery.backoff_multiplier = 'string' raises ConfigError."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[error_recovery]
backoff_multiplier = "2.0"
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("error_recovery.backoff_multiplier must be a number", str(ctx.exception))


class TestUnknownKeysWarning(unittest.TestCase):
    """Test warnings for unrecognized config keys (C3)."""

    def _write_config(self, tmpdir: str, content: str) -> Path:
        project_dir = Path(tmpdir)
        config_dir = project_dir / ".agent-harness"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(content)
        return project_dir

    def test_unknown_key_produces_warning(self) -> None:
        """Test that an unrecognized key like 'modell' produces a warning."""
        import logging
        with TemporaryDirectory() as tmpdir:
            toml_content = 'modell = "claude-opus-4-6"'
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertLogs("agent_harness.config", level=logging.WARNING) as cm:
                load_config(project_dir)
            self.assertTrue(any("Unrecognized config key" in msg for msg in cm.output))
            self.assertTrue(any("modell" in msg for msg in cm.output))

    def test_valid_keys_produce_no_warning(self) -> None:
        """Test that valid keys do not produce warnings."""
        import logging
        with TemporaryDirectory() as tmpdir:
            toml_content = """
model = "claude-opus-4-6"
max_turns = 500
auto_continue_delay = 5
"""
            project_dir = self._write_config(tmpdir, toml_content)
            # Capture logs and check for warnings
            # Using logging.INFO since config module might not emit DEBUG logs
            handler = logging.handlers.MemoryHandler(capacity=100)
            logger = logging.getLogger("agent_harness.config")
            original_level = logger.level
            logger.setLevel(logging.DEBUG)
            logger.addHandler(handler)
            try:
                load_config(project_dir)
                handler.flush()
                # Verify no WARNING messages were logged
                warning_logs = [
                    record for record in handler.buffer
                    if record.levelno >= logging.WARNING
                ]
                self.assertEqual(len(warning_logs), 0)
            finally:
                logger.removeHandler(handler)
                logger.setLevel(original_level)


class TestAdditionalValidation(unittest.TestCase):
    """Test additional validation gaps (C4)."""

    def _write_config(self, tmpdir: str, content: str) -> Path:
        project_dir = Path(tmpdir)
        config_dir = project_dir / ".agent-harness"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(content)
        return project_dir

    def test_empty_model_raises(self) -> None:
        """Test that empty model string raises validation error."""
        with TemporaryDirectory() as tmpdir:
            toml_content = 'model = ""'
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("model must be a non-empty string", str(ctx.exception))

    def test_empty_mcp_command_raises(self) -> None:
        """Test that empty MCP server command raises validation error."""
        with TemporaryDirectory() as tmpdir:
            toml_content = """
[tools.mcp_servers.test]
command = ""
args = []
"""
            project_dir = self._write_config(tmpdir, toml_content)
            with self.assertRaises(ConfigError) as ctx:
                load_config(project_dir)
            self.assertIn("tools.mcp_servers.test.command must be a non-empty string", str(ctx.exception))

    def test_valid_builtin_tools_accepted(self) -> None:
        """Test that all valid builtin tools are accepted."""
        with TemporaryDirectory() as tmpdir:
            # Test a few valid tools
            toml_content = """
[tools]
builtin = ["Read", "Write", "Edit", "Bash", "LSP", "WebSearch"]
"""
            project_dir = self._write_config(tmpdir, toml_content)
            config = load_config(project_dir)
            self.assertEqual(config.tools.builtin, ["Read", "Write", "Edit", "Bash", "LSP", "WebSearch"])


if __name__ == "__main__":
    unittest.main()
