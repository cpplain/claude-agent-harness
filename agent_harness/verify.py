"""
Setup Verification
==================

Checks that the environment and configuration are ready to run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from agent_harness.config import (
    CONFIG_DIR_NAME,
    ConfigError,
    HarnessConfig,
    load_config,
)


class CheckResult:
    """Result of a single verification check."""

    def __init__(self, name: str, status: str, message: str = "") -> None:
        self.name = name
        self.status = status  # "PASS", "WARN", "FAIL"
        self.message = message

    def __str__(self) -> str:
        line = f"  {f'[{self.status}]':8s} {self.name}"
        if self.message:
            line += f" - {self.message}"
        return line


def check_python_version() -> CheckResult:
    """Check Python version >= 3.10."""
    version = sys.version_info
    version_str = f"{version[0]}.{version[1]}.{version[2]}"
    if version >= (3, 10):
        return CheckResult("Python version", "PASS", version_str)
    return CheckResult(
        "Python version", "FAIL", f"Requires >= 3.10, got {version_str}"
    )


def check_authentication() -> CheckResult:
    """Check for API key or OAuth token."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return CheckResult("Authentication", "PASS", "ANTHROPIC_API_KEY set")
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return CheckResult("Authentication", "PASS", "CLAUDE_CODE_OAUTH_TOKEN set")
    return CheckResult(
        "Authentication",
        "FAIL",
        "Set ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN",
    )


def check_api_connectivity() -> CheckResult:
    """Check that API credentials are valid by sending a test query.

    Only runs if authentication check passed.
    """
    import asyncio

    try:
        from claude_agent_sdk import ClaudeAgentOptions
        from claude_agent_sdk.client import ClaudeSDKClient

        async def _check() -> str:
            text_parts: list[str] = []
            async with ClaudeSDKClient(
                options=ClaudeAgentOptions(model="claude-haiku-4-5-20251001"),
            ) as client:
                await client.query("Reply with only the word OK")
                async for msg in client.receive_response():
                    content = getattr(msg, "content", None)
                    if content and isinstance(content, list):
                        for block in content:
                            text = getattr(block, "text", None)
                            if text:
                                text_parts.append(text)
                    elif content:
                        text_parts.append(str(content))
            return " ".join(text_parts)

        result = asyncio.run(asyncio.wait_for(_check(), timeout=30))
        if result:
            return CheckResult("API connectivity", "PASS", "Credentials valid")
        return CheckResult("API connectivity", "FAIL", "No response from API")
    except ImportError:
        return CheckResult(
            "API connectivity",
            "WARN",
            "Skipped (claude-agent-sdk not installed)",
        )
    except asyncio.TimeoutError:
        return CheckResult("API connectivity", "FAIL", "Timed out after 30s")
    except Exception as e:
        return CheckResult("API connectivity", "FAIL", str(e)[:100])


def check_sdk_installed() -> CheckResult:
    """Check that claude-agent-sdk is installed."""
    try:
        import claude_agent_sdk
        version = getattr(claude_agent_sdk, "__version__", "unknown")
        return CheckResult("Claude Agent SDK", "PASS", f"version {version}")
    except ImportError:
        return CheckResult(
            "Claude Agent SDK",
            "FAIL",
            "Not installed. Run: pip install -r requirements.txt",
        )


def check_claude_cli() -> CheckResult:
    """Check that claude CLI is available (system PATH or bundled with SDK)."""
    # First check system PATH
    claude_path = shutil.which("claude")
    if claude_path:
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version = result.stdout.strip() or result.stderr.strip()
            return CheckResult("Claude CLI", "PASS", f"{version} (system)")
        except (subprocess.TimeoutExpired, OSError):
            return CheckResult("Claude CLI", "WARN", "Found but could not get version")

    # If not on PATH, check for bundled CLI in claude-agent-sdk
    try:
        import claude_agent_sdk
        sdk_file = claude_agent_sdk.__file__
        if sdk_file:
            bundled_path = Path(sdk_file).parent / "_bundled" / "claude"
            if bundled_path.exists():
                return CheckResult("Claude CLI", "PASS", "bundled with SDK")
    except ImportError:
        pass

    return CheckResult("Claude CLI", "FAIL", "Not found on PATH or bundled with SDK")


def check_config_exists(harness_dir: Path) -> CheckResult:
    """Check that config.toml exists."""
    config_file = harness_dir / "config.toml"
    if config_file.exists():
        return CheckResult("Config file", "PASS", str(config_file))
    return CheckResult("Config file", "FAIL", f"Not found: {config_file}")


def check_config_valid(project_dir: Path) -> tuple[CheckResult, Optional[HarnessConfig]]:
    """Check that config loads and validates."""
    try:
        config = load_config(project_dir)
        return CheckResult("Config validation", "PASS"), config
    except ConfigError as e:
        return CheckResult("Config validation", "FAIL", str(e)), None


def check_file_references(config: HarnessConfig) -> CheckResult:
    """Check that all file: references point to existing files."""
    # All file: references are already resolved and validated by load_config
    # If we got here, they're all valid
    return CheckResult("File references", "PASS")


def check_mcp_commands(config: HarnessConfig) -> CheckResult:
    """Check that MCP server commands are available on PATH."""
    if not config.tools.mcp_servers:
        return CheckResult("MCP servers", "PASS", "None configured")

    missing = []
    missing_npx = False
    for name, server in config.tools.mcp_servers.items():
        if not shutil.which(server.command):
            if server.command == "npx":
                missing_npx = True
            else:
                missing.append(f"{name} ({server.command})")

    # If only npx is missing, warn with specific message
    if missing_npx and not missing:
        return CheckResult(
            "MCP servers",
            "WARN",
            "npx not found on PATH (packages will auto-download on first run)",
        )

    # If other commands are missing, prioritize those in the message
    if missing:
        return CheckResult(
            "MCP servers",
            "WARN",
            f"Commands not found: {', '.join(missing)}",
        )

    return CheckResult(
        "MCP servers",
        "PASS",
        ", ".join(config.tools.mcp_servers.keys()),
    )


def check_project_dir(project_dir: Path) -> CheckResult:
    """Check that project directory is writable."""
    if project_dir.exists():
        if os.access(project_dir, os.W_OK):
            return CheckResult("Project directory", "PASS", str(project_dir))
        return CheckResult(
            "Project directory", "FAIL", f"Not writable: {project_dir}"
        )
    # Directory doesn't exist yet — check parent
    parent = project_dir.parent
    if parent.exists() and os.access(parent, os.W_OK):
        return CheckResult(
            "Project directory", "PASS", f"Will be created: {project_dir}"
        )
    return CheckResult(
        "Project directory",
        "FAIL",
        f"Parent not writable: {parent}",
    )


def run_verify(project_dir: Path) -> list[CheckResult]:
    """Run all verification checks.

    All checks run regardless of failures.

    Args:
        project_dir: Agent's working directory

    Returns:
        List of CheckResults
    """
    harness_dir = project_dir / CONFIG_DIR_NAME

    results: list[CheckResult] = []

    # Independent checks
    results.append(check_python_version())
    sdk_result = check_sdk_installed()
    results.append(sdk_result)
    results.append(check_claude_cli())

    auth_result = check_authentication()
    results.append(auth_result)

    # API connectivity check (only if SDK and auth both passed)
    if sdk_result.status == "PASS" and auth_result.status == "PASS":
        results.append(check_api_connectivity())

    results.append(check_config_exists(harness_dir))

    # Config-dependent checks
    config_result, config = check_config_valid(project_dir)
    results.append(config_result)

    if config is not None:
        results.append(check_file_references(config))
        results.append(check_mcp_commands(config))
        results.append(check_project_dir(project_dir))

    return results
