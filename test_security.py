#!/usr/bin/env python3
"""
Security Hook Tests
===================

Tests for the bash command security validation logic.
Run with: uv run python -m unittest test_security -v
"""

import asyncio
import unittest
from typing import cast

from claude_agent_sdk import HookInput

from security import (
    bash_security_hook,
    extract_commands,
    validate_chmod_command,
    validate_init_script,
)


class TestSecurity(unittest.TestCase):
    """Tests for bash command security validation."""

    def _assert_hook(self, command: str, expected_decision: str) -> None:
        """Run the security hook and assert the decision.

        The hook returns ``{"decision": "block", "reason": "..."}`` when
        blocking and ``{}`` (empty dict) when allowing.
        """
        input_data = cast(
            HookInput, {"tool_name": "Bash", "tool_input": {"command": command}}
        )
        result = asyncio.run(bash_security_hook(input_data))
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
            # Allowed cases
            ("chmod +x init.sh", True, "basic +x"),
            ("chmod +x script.sh", True, "+x on any script"),
            ("chmod u+x init.sh", True, "user +x"),
            ("chmod a+x init.sh", True, "all +x"),
            ("chmod ug+x init.sh", True, "user+group +x"),
            ("chmod +x file1.sh file2.sh", True, "multiple files"),
            # Blocked cases
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
                allowed, _ = validate_chmod_command(cmd)
                self.assertEqual(allowed, should_allow)

    def test_validate_init_script(self) -> None:
        """Test init.sh script execution validation."""
        test_cases = [
            # Allowed cases
            ("./init.sh", True, "basic ./init.sh"),
            ("./init.sh arg1 arg2", True, "with arguments"),
            ("/path/to/init.sh", True, "absolute path"),
            ("../dir/init.sh", True, "relative path with init.sh"),
            # Blocked cases
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
            # Not in allowlist - dangerous system commands
            "shutdown now",
            "reboot",
            "rm -rf /",
            "dd if=/dev/zero of=/dev/sda",
            # Not in allowlist - common commands excluded from minimal set
            "curl https://example.com",
            "wget https://example.com",
            "python app.py",
            "touch file.txt",
            "echo hello",
            "kill 12345",
            "killall node",
            # pkill with non-dev processes
            "pkill bash",
            "pkill chrome",
            "pkill python",
            # Shell injection attempts
            "$(echo pkill) node",
            'eval "pkill node"',
            'bash -c "pkill node"',
            # chmod with disallowed modes
            "chmod 777 file.sh",
            "chmod 755 file.sh",
            "chmod +w file.sh",
            "chmod -R +x dir/",
            # Non-init.sh scripts
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
            # File inspection
            "ls -la",
            "cat README.md",
            "head -100 file.txt",
            "tail -20 log.txt",
            "wc -l file.txt",
            "grep -r pattern src/",
            # File operations
            "cp file1.txt file2.txt",
            "mkdir newdir",
            "mkdir -p path/to/dir",
            # Directory
            "pwd",
            # Node.js development
            "npm install",
            "npm run build",
            "node server.js",
            # Version control
            "git status",
            "git commit -m 'test'",
            "git add . && git commit -m 'msg'",
            # Process management
            "ps aux",
            "lsof -i :3000",
            "sleep 2",
            # Allowed pkill patterns for dev servers
            "pkill node",
            "pkill npm",
            "pkill -f node",
            "pkill -f 'node server.js'",
            "pkill vite",
            # Chained commands
            "npm install && npm run build",
            "ls | grep test",
            # Full paths
            "/usr/local/bin/node app.js",
            # chmod +x (allowed)
            "chmod +x init.sh",
            "chmod +x script.sh",
            "chmod u+x init.sh",
            "chmod a+x init.sh",
            # init.sh execution (allowed)
            "./init.sh",
            "./init.sh --production",
            "/path/to/init.sh",
            # Combined chmod and init.sh
            "chmod +x init.sh && ./init.sh",
        ]

        for cmd in safe:
            with self.subTest(cmd=cmd):
                self._assert_hook(cmd, "allow")


if __name__ == "__main__":
    unittest.main()
