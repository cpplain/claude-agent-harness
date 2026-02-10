"""
Display Tests
=============

Tests for console output formatting functions.
"""

import io
import sys
import unittest
from unittest.mock import MagicMock

from agent_harness.display import (
    BANNER_WIDTH,
    print_banner,
    print_final_summary,
    print_session_header,
)


class TestPrintSessionHeader(unittest.TestCase):
    """Test session header formatting."""

    def test_print_session_header_format(self) -> None:
        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_session_header(3, "coding")
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("SESSION 3", output)
        self.assertIn("CODING", output)
        self.assertIn("=" * BANNER_WIDTH, output)


class TestPrintBanner(unittest.TestCase):
    """Test startup banner formatting."""

    def test_print_banner_format(self) -> None:
        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_banner("TEST TITLE", {"Key1": "val1", "Key2": "val2"})
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("TEST TITLE", output)
        self.assertIn("Key1: val1", output)
        self.assertIn("Key2: val2", output)
        self.assertIn("=" * BANNER_WIDTH, output)

    def test_print_banner_long_key_truncation(self) -> None:
        """Test that very long keys don't cause negative truncation."""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            # Create a key that would cause negative max_val_len without clamping
            long_key = "A" * (BANNER_WIDTH + 10)
            print_banner("TEST", {long_key: "value"})
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        # Should not crash and should contain the title
        self.assertIn("TEST", output)
        # Value should be empty string since max_val_len would be 0
        lines = output.split("\n")
        # Find the line with the key
        key_line = [line for line in lines if long_key[:50] in line][0]
        # Should end with ": " (no value shown)
        self.assertTrue(key_line.endswith(": "))

    def test_print_banner_max_val_len_zero(self) -> None:
        """Test that max_val_len of 0 produces empty string."""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            # Create a key exactly BANNER_WIDTH - 2, so max_val_len = 0
            long_key = "A" * (BANNER_WIDTH - 2)
            print_banner("TEST", {long_key: "value"})
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        # Should not crash
        self.assertIn("TEST", output)
        # Value should be empty string (truncated "..." to 0 chars)
        lines = output.split("\n")
        # Find the line with the key
        key_line = [line for line in lines if long_key in line][0]
        # Should end with ": " (no value shown)
        self.assertTrue(key_line.endswith(": "))

    def test_print_banner_max_val_len_one(self) -> None:
        """Test that max_val_len of 1 produces single dot."""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            # Create a key exactly BANNER_WIDTH - 3, so max_val_len = 1
            long_key = "A" * (BANNER_WIDTH - 3)
            print_banner("TEST", {long_key: "value"})
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        # Should not crash
        self.assertIn("TEST", output)
        # Value should be "." (truncated "..." to 1 char)
        lines = output.split("\n")
        # Find the line with the key
        key_line = [line for line in lines if long_key in line][0]
        # Should end with ": ."
        self.assertTrue(key_line.endswith(": ."))

    def test_print_banner_max_val_len_three(self) -> None:
        """Test that max_val_len of 3 produces full ellipsis."""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            # Create a key exactly BANNER_WIDTH - 5, so max_val_len = 3
            long_key = "A" * (BANNER_WIDTH - 5)
            print_banner("TEST", {long_key: "value"})
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        # Should not crash
        self.assertIn("TEST", output)
        # Value should be "..." (full ellipsis)
        lines = output.split("\n")
        # Find the line with the key
        key_line = [line for line in lines if long_key in line][0]
        # Should end with ": ..."
        self.assertTrue(key_line.endswith(": ..."))


class TestPrintFinalSummary(unittest.TestCase):
    """Test final summary formatting."""

    def test_print_final_summary_with_instructions(self) -> None:
        tracker = MagicMock()
        tracker.display_summary = MagicMock()
        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_final_summary(
                exit_reason="ALL COMPLETE",
                output_dir="/tmp/out",
                tracker=tracker,
                post_run_instructions=["Run tests", "Check output"],
            )
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("ALL COMPLETE", output)
        self.assertIn("/tmp/out", output)
        self.assertIn("NEXT STEPS", output)
        self.assertIn("Run tests", output)
        self.assertIn("Check output", output)
        tracker.display_summary.assert_called_once()

    def test_print_final_summary_without_instructions(self) -> None:
        tracker = MagicMock()
        tracker.display_summary = MagicMock()
        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_final_summary(
                exit_reason="MAX ITERATIONS",
                output_dir="/tmp/out",
                tracker=tracker,
                post_run_instructions=[],
            )
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("MAX ITERATIONS", output)
        self.assertNotIn("NEXT STEPS", output)
        tracker.display_summary.assert_called_once()


if __name__ == "__main__":
    unittest.main()
