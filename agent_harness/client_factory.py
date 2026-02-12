"""
Client Factory
==============

Builds ClaudeSDKClient from HarnessConfig.
Passes sandbox and permission settings directly to SDK.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from agent_harness.config import HarnessConfig


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

    # Build settings as JSON string
    settings_dict = {
        "permissions": {
            "allow": config.security.permissions.allow.copy(),
            "deny": config.security.permissions.deny.copy(),
        },
    }
    settings_json = json.dumps(settings_dict)

    # Build MCP servers
    mcp_servers = {
        name: {"command": sc.command, "args": sc.args, **({"env": sc.env} if sc.env else {})}
        for name, sc in config.tools.mcp_servers.items()
    }

    # Build sandbox settings dict for SDK
    sandbox_settings = {
        "enabled": config.security.sandbox.enabled,
        "autoAllowBashIfSandboxed": config.security.sandbox.auto_allow_bash_if_sandboxed,
        "allowUnsandboxedCommands": config.security.sandbox.allow_unsandboxed_commands,
        "excludedCommands": config.security.sandbox.excluded_commands,
        "network": {
            "allowedDomains": config.security.sandbox.network.allowed_domains,
            "allowLocalBinding": config.security.sandbox.network.allow_local_binding,
            "allowUnixSockets": config.security.sandbox.network.allow_unix_sockets,
        },
    }

    # Log setup summary
    logger.info("Permission rules configured:")
    if config.security.permissions.allow:
        logger.info("   - Allow: %s", ", ".join(config.security.permissions.allow[:3]) + ("..." if len(config.security.permissions.allow) > 3 else ""))
    if config.security.permissions.deny:
        logger.info("   - Deny: %s", ", ".join(config.security.permissions.deny[:3]) + ("..." if len(config.security.permissions.deny) > 3 else ""))
    logger.info("   - Sandbox %s", "enabled" if config.security.sandbox.enabled else "disabled")
    logger.info("   - Permission mode: %s", config.security.permission_mode)
    logger.info("   - Working directory: %s", config.project_dir.resolve())
    if mcp_servers:
        logger.info("   - MCP servers: %s", ", ".join(mcp_servers.keys()))

    options = ClaudeAgentOptions(
        model=config.model,
        system_prompt=config.system_prompt,
        allowed_tools=list(config.tools.builtin) + [f"mcp__{server_name}__*" for server_name in config.tools.mcp_servers],
        max_turns=config.max_turns,
        cwd=str(config.project_dir.resolve()),
        settings=settings_json,
        env=auth_env,
        mcp_servers=mcp_servers,
        permission_mode=config.security.permission_mode,
        sandbox=sandbox_settings,
    )
    return ClaudeSDKClient(options=options)
