"""
Schema Generation
=================

Generates JSON schema from config dataclasses for documentation and validation.
Uses dataclass introspection to extract defaults, types, and enums automatically.
"""

from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from typing import Any, get_args, get_origin

from agent_harness.config import (
    AVAILABLE_MODELS,
    DEFAULT_BUILTIN_TOOLS,
    ErrorRecoveryConfig,
    HarnessConfig,
    McpServerConfig,
    PermissionMode,
    PermissionRulesConfig,
    PhaseConfig,
    SandboxConfig,
    SandboxNetworkConfig,
    SecurityConfig,
    ToolsConfig,
    TrackingConfig,
    TrackingType,
)


# Description metadata (not stored in dataclasses)
DESCRIPTIONS = {
    "model": "Claude model to use for agent execution",
    "system_prompt": "System prompt for the agent (supports file: references)",
    "max_turns": "Maximum API turns per session before auto-continuing",
    "max_iterations": "Maximum total sessions before stopping (null = unlimited)",
    "auto_continue_delay": "Delay in seconds before auto-continuing to next session",
    "tools": "Tool configuration",
    "tools.builtin": "Built-in Claude SDK tools to enable",
    "tools.mcp_servers": "MCP (Model Context Protocol) servers to connect",
    "tools.mcp_servers.command": "Command to launch the MCP server",
    "tools.mcp_servers.args": "Command-line arguments for the server",
    "tools.mcp_servers.env": "Environment variables (supports ${VAR} expansion)",
    "security": "Security configuration",
    "security.permission_mode": "Permission mode controls how tool calls are approved",
    "security.sandbox": "OS-level sandbox configuration",
    "security.sandbox.enabled": "Enable OS-level sandbox (strongly recommended)",
    "security.sandbox.auto_allow_bash_if_sandboxed": "Auto-allow all Bash commands when sandbox is enabled",
    "security.sandbox.allow_unsandboxed_commands": "Allow commands to run outside the sandbox",
    "security.sandbox.excluded_commands": "Commands to exclude from sandboxing",
    "security.sandbox.network": "Network access restrictions for sandboxed commands",
    "security.sandbox.network.allowed_domains": "Domains the agent can access via network",
    "security.sandbox.network.allow_local_binding": "Allow binding to localhost addresses",
    "security.sandbox.network.allow_unix_sockets": "Unix socket paths the agent can access",
    "security.permissions": "Declarative allow/deny permission rules",
    "security.permissions.allow": "Patterns to explicitly allow (glob patterns)",
    "security.permissions.deny": "Patterns to explicitly deny (takes precedence over allow)",
    "tracking": "Progress tracking configuration",
    "tracking.type": "Tracker type controls how progress is monitored",
    "tracking.file": "Tracking file path (relative to .agent-harness/)",
    "tracking.passing_field": "Field name indicating completion (for json_checklist)",
    "error_recovery": "Error recovery and circuit breaker configuration",
    "error_recovery.max_consecutive_errors": "Maximum consecutive session errors before stopping",
    "error_recovery.initial_backoff_seconds": "Initial backoff delay after first error (seconds)",
    "error_recovery.max_backoff_seconds": "Maximum backoff delay (capped exponential backoff)",
    "error_recovery.backoff_multiplier": "Multiplier for exponential backoff",
    "phases": "Multi-phase workflow configuration",
    "phases.name": "Phase identifier (required, must be unique)",
    "phases.prompt": "Phase prompt (required, supports file: references)",
    "phases.run_once": "Only execute this phase once across all sessions",
    "phases.condition": "Path-based condition for running phase (exists: or not_exists:)",
    "post_run_instructions": "Commands to display after agent completes",
}


def _get_enum_values(enum_class) -> list[str]:
    """Extract string values from an Enum class."""
    return [e.value for e in enum_class]


def _python_type_to_schema_type(python_type: Any) -> str:
    """Convert Python type to JSON schema type string."""
    origin = get_origin(python_type)

    # Handle Optional[T] -> treat as nullable T
    if origin is type(None) or python_type is type(None):
        return "null"

    # Handle list[T]
    if origin is list:
        return "array"

    # Handle dict[K, V]
    if origin is dict:
        return "object"

    # Handle basic types
    if python_type is str or python_type == "str":
        return "string"
    if python_type is int or python_type == "int":
        return "integer"
    if python_type is float or python_type == "float":
        return "number"
    if python_type is bool or python_type == "bool":
        return "boolean"

    # Default to string for unknown types
    return "string"


def _dataclass_to_schema(cls, prefix: str = "") -> dict:
    """Convert a dataclass to a schema dict using introspection.

    Args:
        cls: Dataclass type to introspect
        prefix: Key prefix for nested fields (e.g., "security.sandbox.")

    Returns:
        Schema dict with type, default, description, enum, fields, etc.
    """
    if not is_dataclass(cls):
        return {}

    schema = {}

    for f in fields(cls):
        key = f"{prefix}{f.name}" if prefix else f.name
        field_info = {}

        # Determine type
        field_type = _python_type_to_schema_type(f.type)
        field_info["type"] = field_type

        # Add description if available
        if key in DESCRIPTIONS:
            field_info["description"] = DESCRIPTIONS[key]

        # Extract default value
        if f.default is not MISSING:
            # Skip Path objects - they're runtime-only, not configuration
            if not isinstance(f.default, Path):
                field_info["default"] = f.default
        elif f.default_factory is not MISSING:
            default_value = f.default_factory()

            # Skip Path objects - they're runtime-only, not configuration
            if isinstance(default_value, Path):
                pass  # Don't include in schema
            # Handle nested dataclasses
            elif is_dataclass(default_value):
                nested_schema = _dataclass_to_schema(type(default_value), f"{key}.")
                field_info["fields"] = nested_schema
                # Don't set a default for nested objects
            else:
                field_info["default"] = default_value

        # Check if this field's type is an Enum or references enums
        # Special handling for permission_mode and tracking.type
        if key == "security.permission_mode":
            field_info["enum"] = _get_enum_values(PermissionMode)
        elif key == "tracking.type":
            field_info["enum"] = _get_enum_values(TrackingType)

        # Special handling for model options
        if key == "model":
            field_info["options"] = AVAILABLE_MODELS

        # Special handling for builtin tools (known list options)
        if key == "tools.builtin":
            field_info["options"] = DEFAULT_BUILTIN_TOOLS

        # Special handling for MCP servers (dict of nested objects)
        if key == "tools.mcp_servers":
            field_info["additionalProperties"] = {
                "type": "object",
                "fields": _dataclass_to_schema(McpServerConfig, f"{key}."),
            }

        # Special handling for phases (array of objects)
        if key == "phases":
            field_info["items"] = {
                "type": "object",
                "fields": _dataclass_to_schema(PhaseConfig, f"{key}."),
            }

        # For array types, add items schema
        if field_type == "array" and key not in ["phases", "tools.builtin"]:
            # Detect item type from type annotation
            args = get_args(f.type)
            if args:
                item_type = _python_type_to_schema_type(args[0])
                field_info["items"] = {"type": item_type}

        schema[f.name] = field_info

    return schema


def generate_schema() -> dict:
    """Generate complete configuration schema from dataclasses.

    Returns:
        Schema dict describing all configuration options with types,
        defaults, descriptions, and enum constraints.
    """
    return _dataclass_to_schema(HarnessConfig)
