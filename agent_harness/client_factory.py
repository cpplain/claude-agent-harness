"""
Client Factory
==============

Builds ClaudeSDKClient from HarnessConfig.
Generates security settings, installs hooks, configures MCP servers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

from agent_harness.config import HarnessConfig
from agent_harness.security import create_bash_security_hook, create_mcp_tool_hook


def _build_permission_rules(config: HarnessConfig) -> list[str]:
    """Build permission allow rules from config."""
    rules = []

    # File operation tools get path-based permissions
    path_tools = {"Read", "Write", "Edit", "Glob", "Grep"}
    for tool in config.tools.builtin:
        if tool in path_tools:
            for path_pattern in config.security.allowed_paths:
                rules.append(f"{tool}({path_pattern})")
        elif tool == "Bash":
            rules.append("Bash(*)")
        else:
            rules.append(tool)

    # MCP server tools get wildcard permissions
    for server_name in config.tools.mcp_servers:
        rules.append(f"mcp__{server_name}__*")

    return rules


def _build_settings(config: HarnessConfig) -> dict:
    """Build security settings dict from config."""
    return {
        "sandbox": {
            "enabled": config.security.sandbox.enabled,
            "autoAllowBashIfSandboxed": config.security.sandbox.auto_allow_bash_if_sandboxed,
        },
        "permissions": {
            "defaultMode": config.security.permission_mode,
            "allow": _build_permission_rules(config),
        },
    }


def _write_settings(config: HarnessConfig) -> Path:
    """Write .claude_settings.json to .agent-harness/ and return the path."""
    settings = _build_settings(config)
    settings_file = config.harness_dir / ".claude_settings.json"
    with open(settings_file, "w") as f:
        json.dump(settings, f, indent=2)

    return settings_file


def _build_allowed_tools(config: HarnessConfig) -> list[str]:
    """Build the list of allowed tool names."""
    tools = list(config.tools.builtin)

    # Add MCP server tool wildcards
    for server_name in config.tools.mcp_servers:
        tools.append(f"mcp__{server_name}__*")

    return tools


def _build_mcp_servers(config: HarnessConfig) -> dict:
    """Build MCP server configuration dict."""
    servers = {}
    for name, server_config in config.tools.mcp_servers.items():
        servers[name] = {
            "command": server_config.command,
            "args": server_config.args,
        }
        if server_config.env:
            servers[name]["env"] = server_config.env
    return servers


def create_client(config: HarnessConfig) -> ClaudeSDKClient:
    """Create a ClaudeSDKClient from HarnessConfig.

    Args:
        config: Harness configuration

    Returns:
        Configured ClaudeSDKClient

    Raises:
        ValueError: If no authentication is configured
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")

    # Validate OAuth token if present
    if oauth_token:
        oauth_token = oauth_token.strip()
        if ' ' in oauth_token or '\n' in oauth_token or '\r' in oauth_token:
            raise ValueError(
                "OAuth token appears malformed (contains whitespace).\n"
                f"Token length: {len(oauth_token)}\n"
                "Check for copy/paste issues or environment variable corruption.\n"
                "Set CLAUDE_CODE_OAUTH_TOKEN with a valid token from 'claude setup-token'"
            )

    if not api_key and not oauth_token:
        raise ValueError(
            "No authentication configured.\n"
            "Set one of:\n"
            "  ANTHROPIC_API_KEY  - API key from https://console.anthropic.com/\n"
            "  CLAUDE_CODE_OAUTH_TOKEN - OAuth token from 'claude setup-token'"
        )

    # Build environment with auth credentials
    auth_env = {}
    if api_key:
        auth_env["ANTHROPIC_API_KEY"] = api_key
    if oauth_token:
        auth_env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

    # Ensure project directory exists
    config.project_dir.mkdir(parents=True, exist_ok=True)

    # Write settings file
    settings_file = _write_settings(config)

    # Build hooks
    hooks = {}
    hook_matchers = []

    # Bash security hook
    if config.security.bash is not None:
        hook_fn = create_bash_security_hook(config.security.bash)
        hook_matchers.append(HookMatcher(matcher="Bash", hooks=[hook_fn]))

    # MCP tool security hooks
    if config.security.mcp is not None:
        for tool_name, restrictions in config.security.mcp.tool_restrictions.items():
            mcp_hook = create_mcp_tool_hook(tool_name, restrictions)
            hook_matchers.append(HookMatcher(matcher=tool_name, hooks=[mcp_hook]))

    if hook_matchers:
        hooks["PreToolUse"] = hook_matchers

    # Build MCP servers
    mcp_servers = _build_mcp_servers(config)

    # Print setup summary
    print(f"Settings written to {settings_file}")
    sandbox_status = "enabled" if config.security.sandbox.enabled else "disabled"
    print(f"   - Sandbox {sandbox_status}")
    print(f"   - Working directory: {config.project_dir.resolve()}")
    if config.security.bash is not None:
        print(f"   - Bash commands restricted to allowlist ({len(config.security.bash.allowed_commands)} commands)")
    else:
        print("   - No bash security hook (sandbox handles security)")
    if mcp_servers:
        print(f"   - MCP servers: {', '.join(mcp_servers.keys())}")
    print()

    options_kwargs = dict(
        model=config.model,
        system_prompt=config.system_prompt,
        allowed_tools=_build_allowed_tools(config),
        max_turns=config.max_turns,
        cwd=str(config.project_dir.resolve()),
        settings=str(settings_file.resolve()),
        env=auth_env,
    )

    if mcp_servers:
        options_kwargs["mcp_servers"] = mcp_servers

    if hooks:
        options_kwargs["hooks"] = hooks

    return ClaudeSDKClient(options=ClaudeAgentOptions(**options_kwargs))
