"""
Generic Progress Tracking
=========================

Tracker implementations for monitoring agent progress.
Supports json_checklist, notes_file, and none tracking types.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from agent_harness.config import TrackingConfig


class ProgressTracker(Protocol):
    """Protocol for progress trackers."""

    def get_summary(self) -> tuple[int, int]:
        """Return (passing_count, total_count)."""
        ...

    def is_initialized(self) -> bool:
        """Return True if the tracking file exists and is valid."""
        ...

    def is_complete(self) -> bool:
        """Return True when all items are passing and there is at least one item."""
        ...

    def display_summary(self) -> None:
        """Print a progress summary to stdout."""
        ...


class JsonChecklistTracker:
    """Tracks progress via a JSON array with a boolean passing field."""

    def __init__(self, file_path: Path, passing_field: str = "passes") -> None:
        self.file_path = file_path
        self.passing_field = passing_field

    def get_summary(self) -> tuple[int, int]:
        if not self.file_path.exists():
            return 0, 0

        try:
            with open(self.file_path, "r") as f:
                items = json.load(f)
            if not isinstance(items, list):
                return 0, 0
            total = len(items)
            passing = sum(
                1 for item in items if isinstance(item, dict) and item.get(self.passing_field, False)
            )
            return passing, total
        except (json.JSONDecodeError, IOError):
            return 0, 0

    def is_initialized(self) -> bool:
        if not self.file_path.exists():
            return False
        try:
            with open(self.file_path, "r") as f:
                items = json.load(f)
            return isinstance(items, list) and len(items) > 0
        except (json.JSONDecodeError, IOError):
            return False

    def is_complete(self) -> bool:
        passing, total = self.get_summary()
        return passing == total and total > 0

    def display_summary(self) -> None:
        passing, total = self.get_summary()
        if total > 0:
            percentage = (passing / total) * 100
            print(f"\nProgress: {passing}/{total} tests passing ({percentage:.1f}%)")
        else:
            print(f"\nProgress: {self.file_path.name} not yet created")


class NotesFileTracker:
    """Tracks progress via a plain text notes file."""

    PREVIEW_LINES = 5

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path

    def get_summary(self) -> tuple[int, int]:
        return 0, 0

    def is_initialized(self) -> bool:
        return self.file_path.exists()

    def is_complete(self) -> bool:
        return False

    def display_summary(self) -> None:
        if self.file_path.exists():
            content = self.file_path.read_text().strip()
            # Show first few lines as summary
            lines = content.split("\n")
            preview = "\n".join(lines[:self.PREVIEW_LINES])
            if len(lines) > self.PREVIEW_LINES:
                preview += f"\n  ... ({len(lines)} lines total)"
            print(f"\nProgress notes:\n{preview}")
        else:
            print(f"\nProgress: {self.file_path.name} not yet created")


class NoneTracker:
    """No-op tracker when tracking is disabled."""

    def get_summary(self) -> tuple[int, int]:
        return 0, 0

    def is_initialized(self) -> bool:
        return True

    def is_complete(self) -> bool:
        return False

    def display_summary(self) -> None:
        pass


def create_tracker(config: TrackingConfig, harness_dir: Path) -> ProgressTracker:
    """Create the appropriate tracker from config.

    Args:
        config: Tracking configuration
        harness_dir: Base directory for resolving relative file paths

    Returns:
        A ProgressTracker implementation
    """
    if config.type == "json_checklist":
        return JsonChecklistTracker(
            file_path=harness_dir / config.file,
            passing_field=config.passing_field,
        )
    elif config.type == "notes_file":
        return NotesFileTracker(file_path=harness_dir / config.file)
    else:
        return NoneTracker()
