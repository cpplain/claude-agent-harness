"""
Configuration Loading and Validation
=====================================

Loads and validates .agent-harness/config.toml, merges with defaults,
resolves file: references, and provides HarnessConfig dataclass.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]


CONFIG_DIR_NAME = ".agent-harness"
CONFIG_FILE_NAME = "config.toml"


@dataclass
class ExtraValidatorConfig:
    """Configuration for a command-specific extra validator."""

    allowed_targets: list[str] = field(default_factory=list)
    allowed_modes: list[str] = field(default_factory=list)


@dataclass
class BashSecurityConfig:
    """Configuration for bash command security hooks."""

    allowed_commands: list[str] = field(default_factory=list)
    extra_validators: dict[str, ExtraValidatorConfig] = field(default_factory=dict)


@dataclass
class SandboxConfig:
    """Configuration for OS-level sandbox."""

    enabled: bool = True
    auto_allow_bash_if_sandboxed: bool = True


@dataclass
class McpSecurityConfig:
    """Configuration for MCP tool restrictions."""

    tool_restrictions: dict[str, dict] = field(default_factory=dict)


@dataclass
class SecurityConfig:
    """Security configuration."""

    permission_mode: str = "acceptEdits"
    allowed_paths: list[str] = field(default_factory=lambda: ["./**"])
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    bash: Optional[BashSecurityConfig] = None
    mcp: Optional[McpSecurityConfig] = None


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
        default_factory=lambda: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
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
    model: str = "claude-sonnet-4-5-20250929"
    system_prompt: str = "You are a helpful coding assistant."

    # Session
    max_turns: int = 1000
    max_iterations: Optional[int] = None
    auto_continue_delay: int = 3
    max_budget_usd: Optional[float] = None

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
    file_path = harness_dir / rel_path
    if not file_path.exists():
        raise ConfigError(f"Referenced file does not exist: {file_path}")
    return file_path.read_text()


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def _parse_extra_validator(name: str, data: dict[str, Any]) -> ExtraValidatorConfig:
    """Parse an extra validator config from TOML data."""
    return ExtraValidatorConfig(
        allowed_targets=data.get("allowed_targets", []),
        allowed_modes=data.get("allowed_modes", []),
    )


def _parse_bash_security(data: dict[str, Any]) -> BashSecurityConfig:
    """Parse bash security config from TOML data."""
    extra_validators = {}
    for name, validator_data in data.get("extra_validators", {}).items():
        extra_validators[name] = _parse_extra_validator(name, validator_data)

    return BashSecurityConfig(
        allowed_commands=data.get("allowed_commands", []),
        extra_validators=extra_validators,
    )


def _parse_security(data: dict[str, Any]) -> SecurityConfig:
    """Parse security config from TOML data."""
    sandbox_data = data.get("sandbox", {})
    sandbox = SandboxConfig(
        enabled=sandbox_data.get("enabled", True),
        auto_allow_bash_if_sandboxed=sandbox_data.get(
            "auto_allow_bash_if_sandboxed", True
        ),
    )

    bash = None
    if "bash" in data:
        bash = _parse_bash_security(data["bash"])

    mcp = None
    if "mcp" in data:
        mcp = McpSecurityConfig(
            tool_restrictions=data["mcp"].get("tool_restrictions", {})
        )

    return SecurityConfig(
        permission_mode=data.get("permission_mode", "acceptEdits"),
        allowed_paths=data.get("allowed_paths", ["./**"]),
        sandbox=sandbox,
        bash=bash,
        mcp=mcp,
    )


def _parse_tools(data: dict[str, Any]) -> ToolsConfig:
    """Parse tools config from TOML data."""
    mcp_servers = {}
    for name, server_data in data.get("mcp_servers", {}).items():
        mcp_servers[name] = McpServerConfig(
            command=server_data.get("command", ""),
            args=server_data.get("args", []),
            env=server_data.get("env", {}),
        )

    return ToolsConfig(
        builtin=data.get(
            "builtin", ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
        ),
        mcp_servers=mcp_servers,
    )


def _parse_tracking(data: dict[str, Any]) -> TrackingConfig:
    """Parse tracking config from TOML data."""
    return TrackingConfig(
        type=data.get("type", "none"),
        file=data.get("file", ""),
        passing_field=data.get("passing_field", "passes"),
    )


def _parse_error_recovery(data: dict[str, Any]) -> ErrorRecoveryConfig:
    """Parse error recovery config from TOML data."""
    return ErrorRecoveryConfig(
        max_consecutive_errors=data.get("max_consecutive_errors", 5),
        initial_backoff_seconds=data.get("initial_backoff_seconds", 5.0),
        max_backoff_seconds=data.get("max_backoff_seconds", 120.0),
        backoff_multiplier=data.get("backoff_multiplier", 2.0),
    )


def _parse_phase(data: dict[str, Any]) -> PhaseConfig:
    """Parse a single phase config from TOML data."""
    return PhaseConfig(
        name=data.get("name", ""),
        prompt=data.get("prompt", ""),
        run_once=data.get("run_once", False),
        condition=data.get("condition", ""),
    )


def _parse_init_file(data: dict[str, Any]) -> InitFileConfig:
    """Parse an init file config from TOML data."""
    return InitFileConfig(
        source=data.get("source", ""),
        dest=data.get("dest", ""),
    )


def _validate_config(config: HarnessConfig) -> list[str]:
    """Validate a HarnessConfig and return a list of error messages."""
    errors = []

    # Validate permission mode
    valid_modes = {"acceptEdits", "bypassPermissions", "plan"}
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

    # Validate phases have names and prompts
    for i, phase in enumerate(config.phases):
        if not phase.name:
            errors.append(f"phases[{i}].name is required")
        if not phase.prompt:
            errors.append(f"phases[{i}].prompt is required")

    # Validate init files have source and dest
    for i, init_file in enumerate(config.init_files):
        if not init_file.source:
            errors.append(f"init_files[{i}].source is required")
        if not init_file.dest:
            errors.append(f"init_files[{i}].dest is required")

    # Validate max_turns is positive
    if config.max_turns < 1:
        errors.append("max_turns must be positive")

    # Validate auto_continue_delay is non-negative
    if config.auto_continue_delay < 0:
        errors.append("auto_continue_delay must be non-negative")

    # Validate error recovery settings
    if config.error_recovery.max_consecutive_errors < 1:
        errors.append("error_recovery.max_consecutive_errors must be positive")
    if config.error_recovery.initial_backoff_seconds <= 0:
        errors.append("error_recovery.initial_backoff_seconds must be positive")
    if config.error_recovery.max_backoff_seconds < config.error_recovery.initial_backoff_seconds:
        errors.append("error_recovery.max_backoff_seconds must be >= initial_backoff_seconds")
    if config.error_recovery.backoff_multiplier <= 1.0:
        errors.append("error_recovery.backoff_multiplier must be > 1.0")

    return errors


def load_config(
    project_dir: Path,
    harness_dir: Optional[Path] = None,
    cli_overrides: Optional[dict[str, Any]] = None,
) -> HarnessConfig:
    """Load configuration from .agent-harness/config.toml.

    Args:
        project_dir: Agent's working directory
        harness_dir: Path to .agent-harness/ directory (defaults to project_dir/.agent-harness/)
        cli_overrides: CLI flag overrides (model, max_iterations)

    Returns:
        Validated HarnessConfig

    Raises:
        ConfigError: If config file is missing, invalid, or fails validation
    """
    if harness_dir is None:
        harness_dir = project_dir / CONFIG_DIR_NAME

    config_file = harness_dir / CONFIG_FILE_NAME

    if not config_file.exists():
        raise ConfigError(f"Config file not found: {config_file}")

    try:
        with open(config_file, "rb") as f:
            raw = tomllib.load(f)
    except Exception as e:
        raise ConfigError(f"Failed to parse {config_file}: {e}") from e

    # Build config from TOML data
    config = HarnessConfig(
        model=raw.get("model", "claude-sonnet-4-5-20250929"),
        system_prompt=raw.get("system_prompt", "You are a helpful coding assistant."),
        max_turns=raw.get("max_turns", 1000),
        max_iterations=raw.get("max_iterations"),
        auto_continue_delay=raw.get("auto_continue_delay", 3),
        max_budget_usd=raw.get("max_budget_usd"),
        tools=_parse_tools(raw.get("tools", {})),
        security=_parse_security(raw.get("security", {})),
        tracking=_parse_tracking(raw.get("tracking", {})),
        error_recovery=_parse_error_recovery(raw.get("error_recovery", {})),
        phases=[_parse_phase(p) for p in raw.get("phases", [])],
        init_files=[_parse_init_file(f) for f in raw.get("init_files", [])],
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
