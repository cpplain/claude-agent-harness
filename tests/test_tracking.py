"""
Tracking Tests
==============

Tests for progress tracker implementations.
"""

import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness.tracking import (
    JsonChecklistTracker,
    NoneTracker,
    NotesFileTracker,
)


class TestJsonChecklistTracker(unittest.TestCase):
    """Tests for JSON checklist tracking."""

    def test_get_summary_all_failing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            path.write_text(json.dumps([
                {"description": "A", "passes": False},
                {"description": "B", "passes": False},
            ]))
            tracker = JsonChecklistTracker(path)
            self.assertEqual(tracker.get_summary(), (0, 2))

    def test_get_summary_some_passing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            path.write_text(json.dumps([
                {"description": "A", "passes": True},
                {"description": "B", "passes": False},
                {"description": "C", "passes": True},
            ]))
            tracker = JsonChecklistTracker(path)
            self.assertEqual(tracker.get_summary(), (2, 3))

    def test_get_summary_custom_field(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            path.write_text(json.dumps([
                {"name": "A", "done": True},
                {"name": "B", "done": False},
            ]))
            tracker = JsonChecklistTracker(path, passing_field="done")
            self.assertEqual(tracker.get_summary(), (1, 2))

    def test_get_summary_missing_file(self) -> None:
        tracker = JsonChecklistTracker(Path("/nonexistent/file.json"))
        self.assertEqual(tracker.get_summary(), (0, 0))

    def test_get_summary_malformed_json(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            path.write_text("not json")
            tracker = JsonChecklistTracker(path)
            self.assertEqual(tracker.get_summary(), (0, 0))

    def test_get_summary_non_list_json(self) -> None:
        """Test that non-list JSON (object, string, number) returns (0, 0)."""
        with TemporaryDirectory() as tmpdir:
            # Test with JSON object
            path = Path(tmpdir) / "features.json"
            path.write_text(json.dumps({"passes": True}))
            tracker = JsonChecklistTracker(path)
            self.assertEqual(tracker.get_summary(), (0, 0))

            # Test with JSON string
            path.write_text(json.dumps("hello"))
            tracker = JsonChecklistTracker(path)
            self.assertEqual(tracker.get_summary(), (0, 0))

            # Test with JSON number
            path.write_text(json.dumps(42))
            tracker = JsonChecklistTracker(path)
            self.assertEqual(tracker.get_summary(), (0, 0))

    def test_get_summary_mixed_array(self) -> None:
        """Test that mixed arrays with non-dict items don't crash."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            # Array with dict, string, and number
            path.write_text(json.dumps([
                {"description": "A", "passes": True},
                "string item",
                42,
                {"description": "B", "passes": False},
            ]))
            tracker = JsonChecklistTracker(path)
            # Only the first dict item has passes=True
            # Total is 4 (all items), passing is 1 (only dicts with passes=True)
            self.assertEqual(tracker.get_summary(), (1, 4))

    def test_is_initialized_true(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            path.write_text(json.dumps([{"passes": False}]))
            tracker = JsonChecklistTracker(path)
            self.assertTrue(tracker.is_initialized())

    def test_is_initialized_empty_list(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            path.write_text(json.dumps([]))
            tracker = JsonChecklistTracker(path)
            self.assertFalse(tracker.is_initialized())

    def test_is_initialized_missing_file(self) -> None:
        tracker = JsonChecklistTracker(Path("/nonexistent/file.json"))
        self.assertFalse(tracker.is_initialized())

    def test_is_complete_all_passing(self) -> None:
        """Test is_complete when all items pass."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            path.write_text('[{"name": "f1", "passes": true}, {"name": "f2", "passes": true}]')
            tracker = JsonChecklistTracker(path)
            self.assertTrue(tracker.is_complete())

    def test_is_complete_some_failing(self) -> None:
        """Test is_complete when some items fail."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            path.write_text('[{"name": "f1", "passes": true}, {"name": "f2", "passes": false}]')
            tracker = JsonChecklistTracker(path)
            self.assertFalse(tracker.is_complete())

    def test_is_complete_empty_list(self) -> None:
        """Test is_complete with empty list (should be False)."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            path.write_text('[]')
            tracker = JsonChecklistTracker(path)
            self.assertFalse(tracker.is_complete())

    def test_is_complete_missing_file(self) -> None:
        """Test is_complete when file doesn't exist."""
        tracker = JsonChecklistTracker(Path("/nonexistent"))
        self.assertFalse(tracker.is_complete())

    def test_display_summary_with_progress(self) -> None:
        """Test display_summary shows progress data."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            path.write_text(json.dumps([
                {"description": "A", "passes": True},
                {"description": "B", "passes": False},
                {"description": "C", "passes": True},
            ]))
            tracker = JsonChecklistTracker(path)
            captured = io.StringIO()
            sys.stdout = captured
            try:
                tracker.display_summary()
            finally:
                sys.stdout = sys.__stdout__
            output = captured.getvalue()
            self.assertIn("Progress:", output)
            self.assertIn("2/3", output)
            self.assertIn("66.7%", output)

    def test_display_summary_missing_file(self) -> None:
        """Test display_summary when file doesn't exist."""
        tracker = JsonChecklistTracker(Path("/nonexistent/features.json"))
        captured = io.StringIO()
        sys.stdout = captured
        try:
            tracker.display_summary()
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("Progress:", output)
        self.assertIn("features.json not yet created", output)


class TestNotesFileTracker(unittest.TestCase):
    """Tests for notes file tracking."""

    def test_get_summary_always_zero(self) -> None:
        tracker = NotesFileTracker(Path("/nonexistent"))
        self.assertEqual(tracker.get_summary(), (0, 0))

    def test_is_initialized_when_file_exists(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "notes.txt"
            path.write_text("Some notes")
            tracker = NotesFileTracker(path)
            self.assertTrue(tracker.is_initialized())

    def test_is_initialized_when_file_missing(self) -> None:
        tracker = NotesFileTracker(Path("/nonexistent"))
        self.assertFalse(tracker.is_initialized())

    def test_is_complete_always_false(self) -> None:
        """Test that NotesFileTracker.is_complete() always returns False."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "notes.txt"
            path.write_text("Some notes")
            tracker = NotesFileTracker(path)
            self.assertFalse(tracker.is_complete())

    def test_display_summary_multi_line_content(self) -> None:
        """Test display_summary shows preview and line count for multi-line notes."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "notes.txt"
            # Create content with more than 5 lines
            lines = [f"Line {i}" for i in range(1, 11)]  # 10 lines
            path.write_text("\n".join(lines))
            tracker = NotesFileTracker(path)
            captured = io.StringIO()
            sys.stdout = captured
            try:
                tracker.display_summary()
            finally:
                sys.stdout = sys.__stdout__
            output = captured.getvalue()
            self.assertIn("Progress notes:", output)
            # Should show first 5 lines
            self.assertIn("Line 1", output)
            self.assertIn("Line 5", output)
            # Should NOT show line 6 or beyond
            self.assertNotIn("Line 6", output)
            # Should show total line count
            self.assertIn("(10 lines total)", output)

    def test_display_summary_missing_file(self) -> None:
        """Test display_summary when notes file doesn't exist."""
        tracker = NotesFileTracker(Path("/nonexistent/notes.txt"))
        captured = io.StringIO()
        sys.stdout = captured
        try:
            tracker.display_summary()
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("Progress:", output)
        self.assertIn("notes.txt not yet created", output)


class TestNoneTracker(unittest.TestCase):
    """Tests for no-op tracker."""

    def test_get_summary(self) -> None:
        tracker = NoneTracker()
        self.assertEqual(tracker.get_summary(), (0, 0))

    def test_is_initialized_always_true(self) -> None:
        tracker = NoneTracker()
        self.assertTrue(tracker.is_initialized())

    def test_is_complete_always_false(self) -> None:
        """Test that NoneTracker.is_complete() always returns False."""
        tracker = NoneTracker()
        self.assertFalse(tracker.is_complete())

    def test_display_summary_produces_no_output(self) -> None:
        """Test that NoneTracker.display_summary() produces no output."""
        tracker = NoneTracker()
        captured = io.StringIO()
        sys.stdout = captured
        try:
            tracker.display_summary()
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        # Should produce no output at all
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
