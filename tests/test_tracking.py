"""
Tracking Tests
==============

Tests for progress tracker implementations.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness.config import TrackingConfig
from agent_harness.tracking import (
    JsonChecklistTracker,
    NoneTracker,
    NotesFileTracker,
    create_tracker,
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


class TestNoneTracker(unittest.TestCase):
    """Tests for no-op tracker."""

    def test_get_summary(self) -> None:
        tracker = NoneTracker()
        self.assertEqual(tracker.get_summary(), (0, 0))

    def test_is_initialized_always_true(self) -> None:
        tracker = NoneTracker()
        self.assertTrue(tracker.is_initialized())


class TestCreateTracker(unittest.TestCase):
    """Tests for the tracker factory function."""

    def test_create_json_checklist(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config = TrackingConfig(
                type="json_checklist", file="features.json", passing_field="passes"
            )
            tracker = create_tracker(config, Path(tmpdir))
            self.assertIsInstance(tracker, JsonChecklistTracker)

    def test_create_notes_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config = TrackingConfig(type="notes_file", file="notes.txt")
            tracker = create_tracker(config, Path(tmpdir))
            self.assertIsInstance(tracker, NotesFileTracker)

    def test_create_none(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config = TrackingConfig(type="none")
            tracker = create_tracker(config, Path(tmpdir))
            self.assertIsInstance(tracker, NoneTracker)


if __name__ == "__main__":
    unittest.main()
