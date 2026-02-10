"""
Configurable Bash Security Hooks
=================================

Pre-tool-use hooks that validate bash commands for security.
Uses an allowlist approach - only explicitly permitted commands can run.

The allowlist and extra validators are configured via config.toml,
not hardcoded as module-level constants.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from typing import Any

from claude_agent_sdk import HookContext, HookInput, HookJSONOutput

from agent_harness.config import BashSecurityConfig


def _strip_outer_balanced_parens(s: str) -> str:
    """Strip matched balanced outer parentheses from a string.

    Repeatedly removes one layer of outer parens if they form a balanced pair.

    Args:
        s: String to strip balanced outer parens from

    Returns:
        String with balanced outer parens removed
    """
    while len(s) >= 2 and s[0] == "(" and s[-1] == ")":
        # Check if inner content has balanced parentheses
        inner = s[1:-1]
        depth = 0
        for char in inner:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0:
                    break
        if depth != 0:
            break
        s = s[1:-1]
    return s


def _check_command_substitution(command_string: str) -> bool:
    """Check if a command contains dangerous command substitution patterns.

    Scans for $(, `, <(, >( outside of single quotes using a character-by-character
    state machine to track quote context.

    Args:
        command_string: The command string to check

    Returns:
        True if command substitution pattern is detected (should block), False otherwise
    """
    in_single_quote = False
    in_double_quote = False
    prev_char = ""

    for i, char in enumerate(command_string):
        # Track quote state
        if char == "'" and not in_double_quote and prev_char != "\\":
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote and prev_char != "\\":
            in_double_quote = not in_double_quote

        # Check for command substitution patterns only outside single quotes
        if not in_single_quote:
            # Check for $(
            if char == "$" and i + 1 < len(command_string) and command_string[i + 1] == "(":
                return True
            # Check for backtick `
            if char == "`":
                return True
            # Check for <( or >(
            if char in ("<", ">") and i + 1 < len(command_string) and command_string[i + 1] == "(":
                return True

        prev_char = char

    return False


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
    token = _strip_outer_balanced_parens(token)

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
    # Strip balanced outer parentheses from the full command string
    command_string = _strip_outer_balanced_parens(command_string.strip()).strip()

    segments = re.split(r"\s*(?:&&|\|\|)\s*", command_string)

    return [
        stripped
        for segment in segments
        for sub in re.split(r'(?<!["\'])\s*;\s*(?!["\'])', segment)
        if (stripped := _strip_outer_balanced_parens(sub.strip()).strip())
    ]


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
            return ["__UNPARSEABLE__"]

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

    target = None
    for token in tokens[1:]:
        if not token.startswith("-"):
            target = token

    if target is None:
        return False, "pkill requires a process name"

    if target in allowed_targets:
        return True, ""
    return False, f"pkill only allowed for dev processes: {allowed_targets}"


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

    mode = None
    for token in tokens[1:]:
        if token.startswith("-"):
            return False, "chmod flags are not allowed"
        elif mode is None:
            mode = token

    if mode is None:
        return False, "chmod requires a mode"

    if len(tokens) < 3:
        return False, "chmod requires at least one file"

    if not any(
        mode == a or (a.startswith(("+", "-")) and re.match(r"^[ugoa]+" + re.escape(a) + "$", mode))
        for a in allowed_modes
    ):
        return False, f"chmod mode '{mode}' not in allowed modes: {allowed_modes}"

    return True, ""


def validate_init_script(command_string: str) -> tuple[bool, str]:
    """Validate init.sh script execution - only allow ./init.sh."""
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse init script command"

    if tokens[0] == "./init.sh":
        return True, ""
    return False, f"Only ./init.sh is allowed, got: {tokens[0]}"


def validate_git_command(command_string: str) -> tuple[bool, str]:
    """Validate git commands - block destructive operations.

    Blocks:
    - git clean (removes untracked files)
    - git reset --hard (discards changes)
    - git checkout -- <path> (discards changes to files)
    - git restore (discards uncommitted changes)
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

    if len(tokens) < 2:
        return False, "git requires a subcommand"

    subcommand = tokens[1]

    # Block destructive subcommands
    if subcommand == "clean":
        return False, "git clean is not allowed (removes untracked files)"

    # Block git restore (discards uncommitted changes)
    if subcommand == "restore":
        return False, "git restore is not allowed (discards uncommitted changes)"

    # Block git reset --hard
    if subcommand == "reset":
        if "--hard" in tokens:
            return False, "git reset --hard is not allowed (discards all changes)"
        # Other reset modes (--soft, --mixed) are allowed
        return True, ""

    # Block git checkout -- <path> (discards changes)
    # Block git checkout -f / --force (discards uncommitted changes)
    # But allow git checkout <branch>
    if subcommand == "checkout":
        if "--" in tokens:
            return False, "git checkout -- <path> is not allowed (discards changes)"
        if "-f" in tokens or "--force" in tokens:
            return False, "git checkout -f/--force is not allowed (discards uncommitted changes)"
        # Allow branch switching
        return True, ""

    # Block git push --force/-f and variants
    if subcommand == "push":
        for token in tokens[2:]:
            if token in ("--force", "-f", "--force-with-lease", "--force-if-includes"):
                return False, "force push is not allowed (overwrites remote history)"
            if token.startswith("--force-with-lease=") or token.startswith("--force-if-includes="):
                return False, "force push is not allowed (overwrites remote history)"
        return True, ""

    # All other git subcommands are allowed
    return True, ""


def create_bash_security_hook(bash_config: BashSecurityConfig):
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
    commands_needing_extra = set(extra_validators) | ({"init.sh", "git"} & allowed_commands)

    async def bash_security_hook(
        input_data: HookInput,
        _tool_use_id: str | None = None,
        _context: HookContext | None = None,
    ) -> HookJSONOutput:
        tool_input: dict[str, Any] = input_data.get("tool_input", {})
        command: str = tool_input.get("command", "")
        if not command:
            return {}

        # Check for command substitution patterns first
        if _check_command_substitution(command):
            return {
                "decision": "block",
                "reason": "Command substitution patterns ($(, `, <(, >() are not allowed",
            }

        segments = split_command_segments(command)

        # Build (command_name, segment) pairs for each command in each segment
        # This ensures that every command occurrence is paired with its own segment,
        # preventing a bypass where duplicate command names (e.g., two 'git' commands)
        # would always match the first segment.
        # Also splits on pipes (|) so that each piped sub-command is paired with only
        # its own text, preventing bypasses like "git status | git push --force".
        pairs = []
        for segment in segments:
            # Split on single pipes (| but not ||) to handle piped commands separately
            pipe_segments = re.split(r"(?<!\|)\|(?!\|)", segment)
            for pipe_segment in pipe_segments:
                pipe_segment = pipe_segment.strip()
                if not pipe_segment:
                    continue
                segment_commands = extract_commands(pipe_segment)
                for cmd in segment_commands:
                    pairs.append((cmd, pipe_segment))

        if not pairs:
            return {
                "decision": "block",
                "reason": f"Could not parse command for security validation: {command}",
            }

        for cmd, cmd_segment in pairs:
            if cmd not in allowed_commands:
                return {
                    "decision": "block",
                    "reason": f"Command '{cmd}' is not in the allowed commands list",
                }

            if cmd in commands_needing_extra:
                if cmd == "pkill":
                    validator_config = extra_validators["pkill"]
                    allowed, reason = validate_pkill_command(
                        cmd_segment, validator_config.allowed_targets
                    )
                elif cmd == "chmod":
                    validator_config = extra_validators["chmod"]
                    allowed, reason = validate_chmod_command(
                        cmd_segment, validator_config.allowed_modes
                    )
                elif cmd == "init.sh":
                    allowed, reason = validate_init_script(cmd_segment)
                elif cmd == "git":
                    allowed, reason = validate_git_command(cmd_segment)
                else:
                    continue
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
        _tool_use_id: str | None = None,
        _context: HookContext | None = None,
    ) -> HookJSONOutput:
        """Pre-tool-use hook that validates MCP tool arguments.

        Args:
            input_data: Dict containing tool_name and tool_input
            _tool_use_id: Optional tool use ID (unused, required by hook signature)
            _context: Optional context (unused, required by hook signature)

        Returns:
            Empty dict to allow, or {"decision": "block", "reason": "..."} to block
        """
        if input_data.get("tool_name") != tool_name:
            return {}

        tool_input = input_data.get("tool_input", {})

        # Check blocked patterns in all input values
        if blocked_patterns:
            input_str = json.dumps(tool_input)
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
