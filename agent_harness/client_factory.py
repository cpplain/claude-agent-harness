"""
Client Factory
==============

Builds ClaudeSDKClient from HarnessConfig.
Generates security settings, installs hooks, configures MCP servers.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

from agent_harness.config import HarnessConfig
from agent_harness.security import create_bash_security_hook, create_mcp_tool_hook


def _write_settings(config: HarnessConfig) -> Path:
    """Write .claude_settings.json to .agent-harness/ and return the path.

    Only writes if the content has changed to avoid unnecessary file writes.
    """
    # Build permission rules
    rules = []
    for tool in config.tools.builtin:
        if tool in {"Read", "Write", "Edit", "Glob", "Grep"}:
            for path_pattern in config.security.allowed_paths:
                rules.append(f"{tool}({path_pattern})")
        elif tool == "Bash":
            rules.append("Bash(*)")
        else:
            rules.append(tool)
    for server_name in config.tools.mcp_servers:
        rules.append(f"mcp__{server_name}__*")

    # Build settings dict
    settings = {
        "sandbox": {
            "enabled": config.security.sandbox.enabled,
            "autoAllowBashIfSandboxed": config.security.sandbox.auto_allow_bash_if_sandboxed,
        },
        "permissions": {
            "defaultMode": config.security.permission_mode,
            "allow": rules,
        },
    }

    settings_file = config.harness_dir / ".claude_settings.json"

    # Only write if content has changed
    new_content = json.dumps(settings, indent=2)
    try:
        if settings_file.read_text() == new_content:
            return settings_file
    except OSError:
        pass
    settings_file.write_text(new_content)

    return settings_file


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
        if not oauth_token:
            # All whitespace — treat as unset
            oauth_token = None
        elif ' ' in oauth_token or '\n' in oauth_token or '\r' in oauth_token or '\t' in oauth_token:
            raise ValueError(
                "OAuth token appears malformed (contains whitespace).\n"
                f"Token length: {len(oauth_token)}\n"
                "Check for copy/paste issues or environment variable corruption.\n"
                "Set CLAUDE_CODE_OAUTH_TOKEN with a valid token from 'claude setup-token'"
            )
        elif len(oauth_token) < 20:
            raise ValueError(
                "OAuth token appears too short (expected 20+ characters).\n"
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
    hook_matchers = []

    if config.security.bash is not None:
        hook_matchers.append(HookMatcher(
            matcher="Bash", hooks=[create_bash_security_hook(config.security.bash)],
        ))

    for tool_name, restrictions in config.security.mcp_tool_restrictions.items():
        hook_matchers.append(HookMatcher(
            matcher=tool_name, hooks=[create_mcp_tool_hook(tool_name, restrictions)],
        ))

    hooks = {"PreToolUse": hook_matchers} if hook_matchers else None

    # Build MCP servers
    mcp_servers = {
        name: {"command": sc.command, "args": sc.args, **({"env": sc.env} if sc.env else {})}
        for name, sc in config.tools.mcp_servers.items()
    }

    # Log setup summary
    logger.info("Settings written to %s", settings_file)
    logger.info("   - Sandbox %s", "enabled" if config.security.sandbox.enabled else "disabled")
    logger.info("   - Working directory: %s", config.project_dir.resolve())
    if config.security.bash is not None:
        logger.info("   - Bash commands restricted to allowlist (%d commands)", len(config.security.bash.allowed_commands))
    else:
        if config.security.sandbox.enabled:
            logger.info("   - No bash security hook (sandbox handles security)")
        else:
            logger.info("   - No bash security hook (no bash restrictions configured)")
    if mcp_servers:
        logger.info("   - MCP servers: %s", ", ".join(mcp_servers.keys()))

    options = ClaudeAgentOptions(
        model=config.model,
        system_prompt=config.system_prompt,
        allowed_tools=list(config.tools.builtin) + [f"mcp__{server_name}__*" for server_name in config.tools.mcp_servers],
        max_turns=config.max_turns,
        cwd=str(config.project_dir.resolve()),
        settings=str(settings_file.resolve()),
        env=auth_env,
        mcp_servers=mcp_servers,
        hooks=hooks,
    )
    return ClaudeSDKClient(options=options)
