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


def strip_balanced_parens(token: str) -> str:
    """Strip parentheses from a token, handling shlex artifacts safely.

    When shlex splits "(git status)" it produces ["(git", "status)"] because
    parentheses without spaces are attached to adjacent words. We want to strip
    these shell syntax characters to extract the command name.

    However, we must prevent security bypasses where multiple unbalanced parens
    could hide a dangerous command. The key rule: only strip if we can match
    parens in balanced pairs.

    Examples:
        "(ls)" -> "ls"        (balanced pair)
        "((ls))" -> "ls"      (multiple balanced pairs)
        "(git" -> "git"       (single leading paren - shlex artifact, safe to strip)
        "status)" -> "status" (single trailing paren - shlex artifact, safe to strip)
        "((rm" -> "((rm"      (multiple leading parens - prevents bypass)
        "rm))" -> "rm))"      (multiple trailing parens - prevents bypass)

    Args:
        token: String to strip balanced parens from

    Returns:
        Token with balanced outer parens removed
    """
    # First strip matched pairs (balanced parens)
    while len(token) >= 2 and token[0] == "(" and token[-1] == ")":
        # Check if the outer parens form a valid balanced pair
        depth = 0
        balanced = True
        for char in token[1:-1]:  # Check the string between outer parens
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0:
                    balanced = False
                    break

        if not balanced or depth != 0:
            break

        token = token[1:-1]

    # After stripping balanced pairs, handle single unbalanced parens (shlex artifacts)
    # Only strip if there's exactly ONE paren on each side
    if len(token) >= 2:
        # Strip single leading '(' if not followed by another '('
        if token[0] == "(" and token[1] != "(":
            token = token[1:]
        # Strip single trailing ')' if not preceded by another ')'
        if len(token) >= 2 and token[-1] == ")" and token[-2] != ")":
            token = token[:-1]

    return token


def split_command_segments(command_string: str) -> list[str]:
    """Split a compound command into individual command segments.

    Handles command chaining (&&, ||, ;) but not pipes (those are single commands).
    """
    # Strip outer parentheses from the full command string
    command_string = command_string.strip()
    while command_string.startswith("(") and command_string.endswith(")"):
        command_string = command_string[1:-1].strip()

    segments = re.split(r"\s*(?:&&|\|\|)\s*", command_string)

    result = []
    for segment in segments:
        sub_segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', segment)
        for sub in sub_segments:
            sub = sub.strip()
            # Strip outer parentheses from segments
            while sub.startswith("(") and sub.endswith(")"):
                sub = sub[1:-1].strip()
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
            # Strip balanced parentheses from tokens
            token = strip_balanced_parens(token)

            # Skip empty tokens after stripping
            if not token:
                continue

            if token in ("|", "||", "&&", "&"):
                expect_command = True
                continue

            if token in (
                "if", "then", "else", "elif", "fi",
                "for", "while", "until", "do", "done",
                "case", "esac", "in", "!", "{", "}",
                "(", ")", "((", "))",
            ):
                # Expect command after opening parentheses
                if token in ("(", "(("):
                    expect_command = True
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


def validate_git_command(command_string: str) -> tuple[bool, str]:
    """Validate git commands - block destructive operations.

    Blocks:
    - git clean (removes untracked files)
    - git reset --hard (discards changes)
    - git checkout -- <path> (discards changes to files)
    - git push --force/-f (overwrites remote history)

    Allows:
    - git status/add/commit/diff/log/branch/checkout <branch>/push/stash/etc.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse git command"

    if not tokens or tokens[0] != "git":
        return False, "Not a git command"

    if len(tokens) < 2:
        return False, "git requires a subcommand"

    subcommand = tokens[1]

    # Block destructive subcommands
    if subcommand == "clean":
        return False, "git clean is not allowed (removes untracked files)"

    # Block git reset --hard
    if subcommand == "reset":
        if "--hard" in tokens:
            return False, "git reset --hard is not allowed (discards all changes)"
        # Other reset modes (--soft, --mixed) are allowed
        return True, ""

    # Block git checkout -- <path> (discards changes)
    # But allow git checkout <branch>
    if subcommand == "checkout":
        if "--" in tokens:
            return False, "git checkout -- <path> is not allowed (discards changes)"
        # Allow branch switching
        return True, ""

    # Block git push --force/-f
    if subcommand == "push":
        for token in tokens[2:]:
            if token in ("--force", "-f"):
                return False, "git push --force is not allowed (overwrites remote history)"
        return True, ""

    # All other git subcommands are allowed
    return True, ""


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
    # Also add init.sh and git if they're in the allowlist (always need validation)
    if "init.sh" in allowed_commands:
        commands_needing_extra.add("init.sh")
    if "git" in allowed_commands:
        commands_needing_extra.add("git")

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
                elif cmd == "git":
                    allowed, reason = validate_git_command(cmd_segment)
                    if not allowed:
                        return {"decision": "block", "reason": reason}

        return {}

    return bash_security_hook


def create_mcp_tool_hook(tool_name: str, restrictions: dict):
    """Factory function that creates an MCP tool validation hook.

    Args:
        tool_name: Name of the MCP tool to validate
        restrictions: Dict with validation rules. Supported keys:
            - "blocked_patterns": list[str] - regex patterns that block if matched in any arg
            - "allowed_args": list[str] - if present, only these exact args are allowed

    Returns:
        Async function that validates MCP tool use

    Example restrictions:
        {
            "blocked_patterns": [r"rm -rf", r"--force"],
            "allowed_args": ["status", "list"]
        }
    """
    blocked_patterns = restrictions.get("blocked_patterns", [])
    allowed_args = restrictions.get("allowed_args", None)

    async def mcp_tool_hook(
        input_data: HookInput,
        tool_use_id: str | None = None,
        context: HookContext | None = None,
    ) -> HookJSONOutput:
        """Pre-tool-use hook that validates MCP tool arguments.

        Args:
            input_data: Dict containing tool_name and tool_input
            tool_use_id: Optional tool use ID
            context: Optional context

        Returns:
            Empty dict to allow, or {"decision": "block", "reason": "..."} to block
        """
        if input_data.get("tool_name") != tool_name:
            return {}

        tool_input = input_data.get("tool_input", {})

        # Check blocked patterns in all input values
        if blocked_patterns:
            input_str = str(tool_input)
            for pattern in blocked_patterns:
                if re.search(pattern, input_str, re.IGNORECASE):
                    return {
                        "decision": "block",
                        "reason": f"MCP tool '{tool_name}' input contains blocked pattern: {pattern}",
                    }

        # Check allowed args restriction
        if allowed_args is not None:
            # For tools with an "action" or "command" parameter
            action = tool_input.get("action") or tool_input.get("command")
            if action and action not in allowed_args:
                return {
                    "decision": "block",
                    "reason": f"MCP tool '{tool_name}' action '{action}' not in allowed list: {allowed_args}",
                }

        return {}

    return mcp_tool_hook
