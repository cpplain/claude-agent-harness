"""
Configuration Loading and Validation
=====================================

Loads and validates .agent-harness/config.toml, merges with defaults,
resolves file: references, and provides HarnessConfig dataclass.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]


CONFIG_DIR_NAME = ".agent-harness"
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_BUILTIN_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
_KNOWN_TOP_LEVEL_KEYS = {"model", "system_prompt", "max_turns", "max_iterations", "auto_continue_delay", "tools", "security", "tracking", "error_recovery", "phases", "init_files", "post_run_instructions"}


@dataclass
class SandboxNetworkConfig:
    """Configuration for sandbox network isolation."""

    allowed_domains: list[str] = field(default_factory=list)
    allow_local_binding: bool = False
    allow_unix_sockets: list[str] = field(default_factory=list)


@dataclass
class SandboxConfig:
    """Configuration for OS-level sandbox."""

    enabled: bool = True
    auto_allow_bash_if_sandboxed: bool = True
    allow_unsandboxed_commands: bool = False
    excluded_commands: list[str] = field(default_factory=list)
    network: SandboxNetworkConfig = field(default_factory=SandboxNetworkConfig)


@dataclass
class PermissionRulesConfig:
    """Configuration for declarative allow/deny permission rules."""

    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)


@dataclass
class SecurityConfig:
    """Security configuration."""

    permission_mode: str = "acceptEdits"
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    permissions: PermissionRulesConfig = field(default_factory=PermissionRulesConfig)


@dataclass
class McpServerConfig:
    """Configuration for an MCP server."""

    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class ToolsConfig:
    """Tools configuration."""

    builtin: list[str] = field(
        default_factory=lambda: DEFAULT_BUILTIN_TOOLS.copy()
    )
    mcp_servers: dict[str, McpServerConfig] = field(default_factory=dict)


@dataclass
class TrackingConfig:
    """Progress tracking configuration."""

    type: str = "none"
    file: str = ""
    passing_field: str = "passes"


@dataclass
class PhaseConfig:
    """Configuration for a single agent phase."""

    name: str = ""
    prompt: str = ""
    run_once: bool = False
    condition: str = ""


@dataclass
class InitFileConfig:
    """Configuration for a file to copy on first run."""

    source: str = ""
    dest: str = ""


@dataclass
class ErrorRecoveryConfig:
    """Configuration for error recovery behavior."""

    max_consecutive_errors: int = 5
    initial_backoff_seconds: float = 5.0
    max_backoff_seconds: float = 120.0
    backoff_multiplier: float = 2.0


@dataclass
class HarnessConfig:
    """Top-level configuration for the agent harness."""

    # Agent
    model: str = DEFAULT_MODEL
    system_prompt: str = "You are a helpful coding assistant."

    # Session
    max_turns: int = 1000
    max_iterations: Optional[int] = None
    auto_continue_delay: int = 3
    # Tools
    tools: ToolsConfig = field(default_factory=ToolsConfig)

    # Security
    security: SecurityConfig = field(default_factory=SecurityConfig)

    # Tracking
    tracking: TrackingConfig = field(default_factory=TrackingConfig)

    # Error Recovery
    error_recovery: ErrorRecoveryConfig = field(default_factory=ErrorRecoveryConfig)

    # Phases
    phases: list[PhaseConfig] = field(default_factory=list)

    # Init files
    init_files: list[InitFileConfig] = field(default_factory=list)

    # Post-run instructions
    post_run_instructions: list[str] = field(default_factory=list)

    # Resolved paths (set by load_config, not from TOML)
    project_dir: Path = field(default_factory=lambda: Path("."))
    harness_dir: Path = field(default_factory=lambda: Path(".agent-harness"))


def resolve_file_reference(value: str, harness_dir: Path) -> str:
    """Resolve a file: reference to its contents.

    If value starts with "file:", read the referenced file relative to harness_dir.
    Otherwise return value as-is.
    """
    if not value.startswith("file:"):
        return value

    rel_path = value[5:]  # Strip "file:" prefix
    file_path = (harness_dir / rel_path).resolve()
    if not file_path.is_relative_to(harness_dir.resolve()):
        raise ConfigError(
            f"file: reference escapes harness directory: {value}"
        )
    if not file_path.exists():
        raise ConfigError(f"Referenced file does not exist: {file_path}")
    return file_path.read_text()


class ConfigError(Exception):
    """Raised when configuration is invalid."""



def _validate_config(config: HarnessConfig) -> list[str]:
    """Validate a HarnessConfig and return a list of error messages."""
    errors = []

    # Validate model is non-empty string
    if not isinstance(config.model, str) or not config.model:
        errors.append("model must be a non-empty string")

    # Validate permission mode
    valid_modes = {"default", "acceptEdits", "bypassPermissions", "plan"}
    if config.security.permission_mode not in valid_modes:
        errors.append(
            f"security.permission_mode must be one of {valid_modes}, "
            f"got: {config.security.permission_mode!r}"
        )

    # Validate tracking type
    valid_tracking = {"json_checklist", "notes_file", "none"}
    if config.tracking.type not in valid_tracking:
        errors.append(
            f"tracking.type must be one of {valid_tracking}, "
            f"got: {config.tracking.type!r}"
        )

    # Validate tracking file is set when type requires it
    if config.tracking.type in ("json_checklist", "notes_file") and not config.tracking.file:
        errors.append(
            f"tracking.file is required when tracking.type is {config.tracking.type!r}"
        )

    # Validate MCP server commands are non-empty
    for name, server in config.tools.mcp_servers.items():
        if not isinstance(server.command, str) or not server.command:
            errors.append(f"tools.mcp_servers.{name}.command must be a non-empty string")

    # Validate phases have names, prompts, and valid conditions
    phase_names = set()
    for i, phase in enumerate(config.phases):
        if not phase.name:
            errors.append(f"phases[{i}].name is required")
        else:
            # Check for duplicate phase names
            if phase.name in phase_names:
                errors.append(f"Duplicate phase name: {phase.name!r}")
            phase_names.add(phase.name)
        if not phase.prompt:
            errors.append(f"phases[{i}].prompt is required")
        if phase.condition and not phase.condition.startswith(("exists:", "not_exists:")):
            errors.append(
                f"phases[{i}].condition must start with one of ('exists:', 'not_exists:'), "
                f"got: {phase.condition!r}"
            )

    # Validate init files have source and dest
    for i, init_file in enumerate(config.init_files):
        if not init_file.source:
            errors.append(f"init_files[{i}].source is required")
        if not init_file.dest:
            errors.append(f"init_files[{i}].dest is required")

    # Validate max_turns
    if not isinstance(config.max_turns, int):
        errors.append(f"max_turns must be an integer, got: {type(config.max_turns).__name__}")
    elif config.max_turns < 1:
        errors.append("max_turns must be positive")

    # Validate auto_continue_delay
    if not isinstance(config.auto_continue_delay, int):
        errors.append(f"auto_continue_delay must be an integer, got: {type(config.auto_continue_delay).__name__}")
    elif config.auto_continue_delay < 0:
        errors.append("auto_continue_delay must be non-negative")

    # Validate max_iterations
    if config.max_iterations is not None:
        if not isinstance(config.max_iterations, int):
            errors.append(f"max_iterations must be an integer, got: {type(config.max_iterations).__name__}")
        elif config.max_iterations <= 0:
            errors.append("max_iterations must be positive when set")

    # Validate error recovery settings
    if not isinstance(config.error_recovery.max_consecutive_errors, int):
        errors.append(f"error_recovery.max_consecutive_errors must be an integer, got: {type(config.error_recovery.max_consecutive_errors).__name__}")
    elif config.error_recovery.max_consecutive_errors < 1:
        errors.append("error_recovery.max_consecutive_errors must be positive")

    if not isinstance(config.error_recovery.initial_backoff_seconds, (int, float)):
        errors.append(f"error_recovery.initial_backoff_seconds must be a number, got: {type(config.error_recovery.initial_backoff_seconds).__name__}")
    elif config.error_recovery.initial_backoff_seconds <= 0:
        errors.append("error_recovery.initial_backoff_seconds must be positive")

    if not isinstance(config.error_recovery.max_backoff_seconds, (int, float)):
        errors.append(f"error_recovery.max_backoff_seconds must be a number, got: {type(config.error_recovery.max_backoff_seconds).__name__}")
    elif isinstance(config.error_recovery.initial_backoff_seconds, (int, float)) and config.error_recovery.max_backoff_seconds < config.error_recovery.initial_backoff_seconds:
        errors.append("error_recovery.max_backoff_seconds must be >= initial_backoff_seconds")

    if not isinstance(config.error_recovery.backoff_multiplier, (int, float)):
        errors.append(f"error_recovery.backoff_multiplier must be a number, got: {type(config.error_recovery.backoff_multiplier).__name__}")
    elif config.error_recovery.backoff_multiplier < 1.0:
        errors.append("error_recovery.backoff_multiplier must be >= 1.0")

    return errors


def load_config(
    project_dir: Path,
    cli_overrides: Optional[dict[str, Any]] = None,
) -> HarnessConfig:
    """Load configuration from .agent-harness/config.toml.

    Args:
        project_dir: Agent's working directory
        cli_overrides: CLI flag overrides (model, max_iterations)

    Returns:
        Validated HarnessConfig

    Raises:
        ConfigError: If config file is missing, invalid, or fails validation
    """
    harness_dir = project_dir / CONFIG_DIR_NAME

    config_file = harness_dir / "config.toml"

    if not config_file.exists():
        raise ConfigError(f"Config file not found: {config_file}")

    try:
        with open(config_file, "rb") as f:
            raw = tomllib.load(f)
    except Exception as e:
        raise ConfigError(f"Failed to parse {config_file}: {e}") from e

    # Warn about unknown keys
    for key in raw:
        if key not in _KNOWN_TOP_LEVEL_KEYS:
            logger.warning(
                "Unrecognized config key: %r (did you mean %s?)",
                key,
                ", ".join(sorted(_KNOWN_TOP_LEVEL_KEYS)),
            )

    # Build config from TOML data
    raw_tracking = raw.get("tracking", {})
    raw_error = raw.get("error_recovery", {})
    raw_security = raw.get("security", {})
    raw_tools = raw.get("tools", {})

    # Parse tools config
    mcp_servers = {}
    for name, server_data in raw_tools.get("mcp_servers", {}).items():
        expanded_env = {}
        for k, v in server_data.get("env", {}).items():
            expanded = os.path.expandvars(v)
            if expanded == v and "$" in v:
                logger.warning(
                    "MCP server '%s' env var '%s' may contain undefined variable: %s",
                    name, k, v,
                )
            # Also warn when expansion produces empty string
            if expanded != v and expanded == "":
                logger.warning(
                    "MCP server '%s' env var '%s' expanded to empty string: %s",
                    name, k, v,
                )
            expanded_env[k] = expanded
        mcp_servers[name] = McpServerConfig(
            command=server_data.get("command", ""),
            args=server_data.get("args", []),
            env=expanded_env,
        )

    tools = ToolsConfig(
        builtin=raw_tools.get("builtin", DEFAULT_BUILTIN_TOOLS.copy()),
        mcp_servers=mcp_servers,
    )

    # Parse security config
    sandbox_data = raw_security.get("sandbox", {})
    network_data = sandbox_data.get("network", {})
    sandbox = SandboxConfig(
        enabled=sandbox_data.get("enabled", True),
        auto_allow_bash_if_sandboxed=sandbox_data.get(
            "auto_allow_bash_if_sandboxed", True
        ),
        allow_unsandboxed_commands=sandbox_data.get("allow_unsandboxed_commands", False),
        excluded_commands=sandbox_data.get("excluded_commands", []),
        network=SandboxNetworkConfig(
            allowed_domains=network_data.get("allowed_domains", []),
            allow_local_binding=network_data.get("allow_local_binding", False),
            allow_unix_sockets=network_data.get("allow_unix_sockets", []),
        ),
    )

    permissions_data = raw_security.get("permissions", {})
    permissions = PermissionRulesConfig(
        allow=permissions_data.get("allow", []),
        deny=permissions_data.get("deny", []),
    )

    security = SecurityConfig(
        permission_mode=raw_security.get("permission_mode", "acceptEdits"),
        sandbox=sandbox,
        permissions=permissions,
    )

    config = HarnessConfig(
        model=raw.get("model", DEFAULT_MODEL),
        system_prompt=raw.get("system_prompt", "You are a helpful coding assistant."),
        max_turns=raw.get("max_turns", 1000),
        max_iterations=raw.get("max_iterations"),
        auto_continue_delay=raw.get("auto_continue_delay", 3),
        tools=tools,
        security=security,
        tracking=TrackingConfig(
            type=raw_tracking.get("type", "none"),
            file=raw_tracking.get("file", ""),
            passing_field=raw_tracking.get("passing_field", "passes"),
        ),
        error_recovery=ErrorRecoveryConfig(
            max_consecutive_errors=raw_error.get("max_consecutive_errors", 5),
            initial_backoff_seconds=raw_error.get("initial_backoff_seconds", 5.0),
            max_backoff_seconds=raw_error.get("max_backoff_seconds", 120.0),
            backoff_multiplier=raw_error.get("backoff_multiplier", 2.0),
        ),
        phases=[
            PhaseConfig(
                name=p.get("name", ""),
                prompt=p.get("prompt", ""),
                run_once=p.get("run_once", False),
                condition=p.get("condition", ""),
            )
            for p in raw.get("phases", [])
        ],
        init_files=[
            InitFileConfig(
                source=f.get("source", ""),
                dest=f.get("dest", ""),
            )
            for f in raw.get("init_files", [])
        ],
        post_run_instructions=raw.get("post_run_instructions", []),
        project_dir=project_dir,
        harness_dir=harness_dir,
    )

    # Apply CLI overrides
    if cli_overrides:
        if "model" in cli_overrides and cli_overrides["model"] is not None:
            config.model = cli_overrides["model"]
        if "max_iterations" in cli_overrides and cli_overrides["max_iterations"] is not None:
            config.max_iterations = cli_overrides["max_iterations"]

    # Resolve file: references
    config.system_prompt = resolve_file_reference(config.system_prompt, harness_dir)
    for phase in config.phases:
        phase.prompt = resolve_file_reference(phase.prompt, harness_dir)

    # Validate
    errors = _validate_config(config)
    if errors:
        raise ConfigError("Configuration errors:\n  " + "\n  ".join(errors))

    return config
