"""
Console Output Formatting
==========================

Functions for formatted console output: headers, summaries, etc.
"""

from __future__ import annotations

from agent_harness.tracking import ProgressTracker


def print_session_header(session_num: int, phase_name: str) -> None:
    """Print a formatted header for a session."""
    print("\n" + "=" * 70)
    print(f"  SESSION {session_num}: {phase_name.upper()}")
    print("=" * 70)
    print()


def print_banner(title: str, config_summary: dict[str, str]) -> None:
    """Print the startup banner with configuration summary.

    Args:
        title: Banner title
        config_summary: Key-value pairs to display
    """
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)
    for key, value in config_summary.items():
        print(f"\n{key}: {value}")
    print()


def print_progress(tracker: ProgressTracker) -> None:
    """Print progress from a tracker."""
    tracker.display_summary()


def print_session_complete(project_dir: str) -> None:
    """Print session completion message."""
    print("\n" + "=" * 70)
    print("  SESSION COMPLETE")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")


def print_final_summary(
    exit_reason: str,
    output_dir: str,
    tracker: ProgressTracker,
    post_run_instructions: list[str],
) -> None:
    """Print final summary with exit reason, output directory, progress, and post-run instructions.

    Args:
        exit_reason: Reason for exiting (e.g., "ALL COMPLETE", "MAX ITERATIONS", "TOO MANY ERRORS")
        output_dir: Path to the output directory
        tracker: Progress tracker to display summary
        post_run_instructions: List of instructions to show the user
    """
    print("\n" + "=" * 70)
    print(f"  {exit_reason}")
    print("=" * 70)
    print(f"\nOutput directory: {output_dir}")
    print_progress(tracker)

    if post_run_instructions:
        print("\n" + "-" * 70)
        print("  NEXT STEPS:")
        print("-" * 70)
        for instruction in post_run_instructions:
            print(f"  {instruction}")
        print("-" * 70)
