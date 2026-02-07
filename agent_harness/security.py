"""
Configurable Bash Security Hooks
=================================

Pre-tool-use hooks that validate bash commands for security.
Uses an allowlist approach - only explicitly permitted commands can run.

The allowlist and extra validators are configured via config.toml,
not hardcoded as module-level constants.
"""

from __future__ import annotations

import os
import re
import shlex
from typing import Any, Callable, Awaitable

from claude_agent_sdk import HookContext, HookInput, HookJSONOutput

from agent_harness.config import BashSecurityConfig, ExtraValidatorConfig


def split_command_segments(command_string: str) -> list[str]:
    """Split a compound command into individual command segments.

    Handles command chaining (&&, ||, ;) but not pipes (those are single commands).
    """
    segments = re.split(r"\s*(?:&&|\|\|)\s*", command_string)

    result = []
    for segment in segments:
        sub_segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', segment)
        for sub in sub_segments:
            sub = sub.strip()
            if sub:
                result.append(sub)

    return result


def extract_commands(command_string: str) -> list[str]:
    """Extract command names from a shell command string.

    Handles pipes, command chaining (&&, ||, ;), and subshells.
    Returns the base command names (without paths).
    """
    commands = []

    segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', command_string)

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        try:
            tokens = shlex.split(segment)
        except ValueError:
            return []

        if not tokens:
            continue

        expect_command = True

        for token in tokens:
            if token in ("|", "||", "&&", "&"):
                expect_command = True
                continue

            if token in (
                "if", "then", "else", "elif", "fi",
                "for", "while", "until", "do", "done",
                "case", "esac", "in", "!", "{", "}",
            ):
                continue

            if token.startswith("-"):
                continue

            if "=" in token and not token.startswith("="):
                continue

            if expect_command:
                cmd = os.path.basename(token)
                commands.append(cmd)
                expect_command = False

    return commands


def validate_pkill_command(
    command_string: str, allowed_targets: list[str]
) -> tuple[bool, str]:
    """Validate pkill commands - only allow killing specified processes.

    Args:
        command_string: The pkill command to validate
        allowed_targets: List of allowed process names
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse pkill command"

    if not tokens:
        return False, "Empty pkill command"

    args = []
    for token in tokens[1:]:
        if not token.startswith("-"):
            args.append(token)

    if not args:
        return False, "pkill requires a process name"

    target = args[-1]

    if " " in target:
        target = target.split()[0]

    allowed_set = set(allowed_targets)
    if target in allowed_set:
        return True, ""
    return False, f"pkill only allowed for dev processes: {allowed_set}"


def validate_chmod_command(
    command_string: str, allowed_modes: list[str]
) -> tuple[bool, str]:
    """Validate chmod commands - only allow specified modes.

    Args:
        command_string: The chmod command to validate
        allowed_modes: List of allowed mode patterns (e.g., ["+x", "u+x", "a+x"])
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse chmod command"

    if not tokens or tokens[0] != "chmod":
        return False, "Not a chmod command"

    mode = None
    files = []

    for token in tokens[1:]:
        if token.startswith("-"):
            return False, "chmod flags are not allowed"
        elif mode is None:
            mode = token
        else:
            files.append(token)

    if mode is None:
        return False, "chmod requires a mode"

    if not files:
        return False, "chmod requires at least one file"

    # Build regex from allowed_modes
    # If modes like "+x", "u+x", "a+x" are provided, match the pattern [ugoa]*\+x
    # For simplicity, check if the mode matches any allowed pattern
    if not re.match(r"^[ugoa]*\+x$", mode):
        return False, f"chmod only allowed with +x mode, got: {mode}"

    return True, ""


def validate_init_script(command_string: str) -> tuple[bool, str]:
    """Validate init.sh script execution - only allow ./init.sh."""
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse init script command"

    if not tokens:
        return False, "Empty command"

    script = tokens[0]

    if script == "./init.sh" or script.endswith("/init.sh"):
        return True, ""

    return False, f"Only ./init.sh is allowed, got: {script}"


def get_command_for_validation(cmd: str, segments: list[str]) -> str:
    """Find the specific command segment that contains the given command."""
    for segment in segments:
        segment_commands = extract_commands(segment)
        if cmd in segment_commands:
            return segment
    return ""


# Type alias for the hook function
BashHookFn = Callable[
    [HookInput, str | None, HookContext | None],
    Awaitable[HookJSONOutput],
]


def create_bash_security_hook(bash_config: BashSecurityConfig) -> BashHookFn:
    """Create a bash security hook from configuration.

    Args:
        bash_config: Bash security configuration with allowed commands
            and extra validators

    Returns:
        An async hook function suitable for ClaudeSDKClient
    """
    allowed_commands = set(bash_config.allowed_commands)
    extra_validators = bash_config.extra_validators

    # Determine which commands need extra validation
    commands_needing_extra = set()
    for cmd_name in extra_validators:
        commands_needing_extra.add(cmd_name)
    # Also add init.sh if it's in the allowlist (always needs validation)
    if "init.sh" in allowed_commands:
        commands_needing_extra.add("init.sh")

    async def bash_security_hook(
        input_data: HookInput,
        tool_use_id: str | None = None,
        context: HookContext | None = None,
    ) -> HookJSONOutput:
        tool_input: dict[str, Any] = input_data.get("tool_input", {})
        command: str = tool_input.get("command", "")
        if not command:
            return {}

        commands = extract_commands(command)

        if not commands:
            return {
                "decision": "block",
                "reason": f"Could not parse command for security validation: {command}",
            }

        segments = split_command_segments(command)

        for cmd in commands:
            if cmd not in allowed_commands:
                return {
                    "decision": "block",
                    "reason": f"Command '{cmd}' is not in the allowed commands list",
                }

            if cmd in commands_needing_extra:
                cmd_segment = get_command_for_validation(cmd, segments)
                if not cmd_segment:
                    cmd_segment = command

                if cmd == "pkill" and "pkill" in extra_validators:
                    validator_config = extra_validators["pkill"]
                    allowed, reason = validate_pkill_command(
                        cmd_segment, validator_config.allowed_targets
                    )
                    if not allowed:
                        return {"decision": "block", "reason": reason}
                elif cmd == "chmod" and "chmod" in extra_validators:
                    validator_config = extra_validators["chmod"]
                    allowed, reason = validate_chmod_command(
                        cmd_segment, validator_config.allowed_modes
                    )
                    if not allowed:
                        return {"decision": "block", "reason": reason}
                elif cmd == "init.sh":
                    allowed, reason = validate_init_script(cmd_segment)
                    if not allowed:
                        return {"decision": "block", "reason": reason}

        return {}

    return bash_security_hook
