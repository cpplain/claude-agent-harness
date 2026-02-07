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
    create_bash_security_hook,
    extract_commands,
    validate_chmod_command,
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
        result = asyncio.run(self.hook(input_data))
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

    def test_validate_init_script(self) -> None:
        """Test init.sh script execution validation."""
        test_cases = [
            ("./init.sh", True, "basic ./init.sh"),
            ("./init.sh arg1 arg2", True, "with arguments"),
            ("/path/to/init.sh", True, "absolute path"),
            ("../dir/init.sh", True, "relative path with init.sh"),
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
            "git commit -m 'test'",
            "git add . && git commit -m 'msg'",
            "ps aux",
            "lsof -i :3000",
            "sleep 2",
            "pkill node",
            "pkill npm",
            "pkill -f node",
            "pkill -f 'node server.js'",
            "pkill vite",
            "npm install && npm run build",
            "ls | grep test",
            "/usr/local/bin/node app.js",
            "chmod +x init.sh",
            "chmod +x script.sh",
            "chmod u+x init.sh",
            "chmod a+x init.sh",
            "./init.sh",
            "./init.sh --production",
            "/path/to/init.sh",
            "chmod +x init.sh && ./init.sh",
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
        result = asyncio.run(hook(input_data))
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
        result = asyncio.run(hook(input_data))
        self.assertEqual(result.get("decision", "allow"), "allow")

        # npm should be blocked
        input_data = cast(
            HookInput, {"tool_name": "Bash", "tool_input": {"command": "npm install"}}
        )
        result = asyncio.run(hook(input_data))
        self.assertEqual(result.get("decision"), "block")

    def test_validate_pkill_with_custom_targets(self) -> None:
        """pkill validation should use configured targets."""
        allowed, _ = validate_pkill_command("pkill python", ["python", "java"])
        self.assertTrue(allowed)
        allowed, _ = validate_pkill_command("pkill node", ["python", "java"])
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
