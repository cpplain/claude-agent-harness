"""
Generic Agent Runner
====================

Main agent loop with phase selection, session state, and conditions.
Replaces the hardcoded agent.py with a fully configurable runner.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    ClaudeSDKClient,
    ClaudeSDKError,
    ProcessError,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_harness.config import ConfigError, ErrorRecoveryConfig, HarnessConfig, PhaseConfig
from agent_harness.client_factory import create_client
from agent_harness.tracking import (
    JsonChecklistTracker,
    NoneTracker,
    NotesFileTracker,
    ProgressTracker,
)

BANNER_WIDTH = 70


def _load_session_state(config: HarnessConfig) -> dict:
    """Load session state from .agent-harness/session.json.

    Prunes completed_phases entries that don't match any configured phase name,
    handling renames or removals gracefully.
    """
    state_file = config.harness_dir / "session.json"
    state = {"session_number": 0, "completed_phases": []}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            if not isinstance(state, dict):
                logger.warning("Corrupt session state (non-dict JSON), starting fresh")
                return {"session_number": 0, "completed_phases": []}
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Corrupt session state (%s), starting fresh", e)
            return {"session_number": 0, "completed_phases": []}

    # Prune completed phases that no longer exist in config
    if config.phases:
        valid_names = {p.name for p in config.phases}
        state["completed_phases"] = [
            name for name in state.get("completed_phases", [])
            if name in valid_names
        ]

    return state


def _save_session_state(config: HarnessConfig, state: dict) -> None:
    """Save session state to .agent-harness/session.json.

    Uses atomic write (temp file + rename) to prevent corruption.
    Logs OSError as warning instead of crashing.
    """
    state_file = config.harness_dir / "session.json"
    try:
        # Create temp file in same directory for atomic rename
        fd, temp_path = tempfile.mkstemp(
            dir=config.harness_dir,
            prefix=".session.",
            suffix=".tmp"
        )
        try:
            # Write to temp file
            with os.fdopen(fd, 'w') as f:
                f.write(json.dumps(state, indent=2))

            # Atomic rename
            os.rename(temp_path, state_file)
        except:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
    except OSError as e:
        logger.warning("Failed to save session state: %s", e)


def evaluate_condition(condition: str, project_dir: Path) -> bool:
    """Evaluate a phase condition.

    Supported conditions:
        - "exists:<path>" — True if file exists relative to project_dir
        - "not_exists:<path>" — True if file does not exist
        - "" — Always True (no condition)

    Raises:
        ValueError: If path escapes project_dir (path traversal attack)

    Returns:
        True if the condition is met
    """
    if not condition:
        return True

    if condition.startswith("exists:"):
        prefix, negate = "exists:", False
    elif condition.startswith("not_exists:"):
        prefix, negate = "not_exists:", True
    else:
        raise ValueError(
            f"Unknown condition prefix in {condition!r} — "
            f"only 'exists:' and 'not_exists:' are supported"
        )

    path = project_dir / condition[len(prefix):]
    # Protect against path traversal
    resolved = path.resolve()
    if not resolved.is_relative_to(project_dir.resolve()):
        raise ValueError(
            f"Path {condition[len(prefix):]!r} escapes project directory"
        )
    return not path.exists() if negate else path.exists()


def select_phase(
    config: HarnessConfig,
    state: dict,
) -> Optional[PhaseConfig]:
    """Select the next phase to run.

    Skips run_once phases already completed.
    Evaluates path-based conditions.

    Returns:
        The next phase to run, or None if no phases are configured
    """
    if not config.phases:
        return None

    completed = set(state.get("completed_phases", []))

    for phase in config.phases:
        # Skip run_once phases already completed
        if phase.run_once and phase.name in completed:
            continue

        # Evaluate condition
        if not evaluate_condition(phase.condition, config.project_dir):
            continue

        return phase

    # If all phases are exhausted (all run_once and completed), use the last non-run_once phase
    for phase in reversed(config.phases):
        if not phase.run_once:
            # Re-evaluate condition in fallback
            if evaluate_condition(phase.condition, config.project_dir):
                return phase

    return None


async def run_agent_session(
    client: ClaudeSDKClient,
    message: str,
) -> tuple[str, str]:
    """Run a single agent session using Claude Agent SDK.

    Args:
        client: Claude SDK client
        message: The prompt to send

    Returns:
        (status, response_text) where status is "continue" or "error"
    """
    print("Sending prompt to Claude Agent SDK...\n")

    try:
        await client.query(message)

        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(block.text, end="", flush=True)
                    elif isinstance(block, ToolUseBlock):
                        print(f"\n[Tool: {block.name}]", flush=True)
                        input_str = str(block.input)
                        print(f"   Input: {input_str[:200]}{'...' if len(input_str) > 200 else ''}", flush=True)

            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, ToolResultBlock):
                        result_content = block.content or ""

                        if block.is_error:
                            error_str = str(result_content)[:500]
                            if "blocked" in error_str.lower():
                                print(f"   [BLOCKED] {result_content}", flush=True)
                            else:
                                print(f"   [Error] {error_str}", flush=True)
                        else:
                            print("   [Done]", flush=True)

        print("\n" + "-" * 70 + "\n")
        return "continue", ""

    except (OSError, IOError, ConnectionError, TimeoutError, RuntimeError, ClaudeSDKError, CLIConnectionError, ProcessError) as e:
        logger.exception("Error during agent session")
        print(f"Error during agent session: {e}")
        return "error", str(e)


def copy_init_files(config: HarnessConfig) -> None:
    """Copy init_files to harness_dir if they don't already exist.

    Args:
        config: Harness configuration with init_files and paths

    Raises:
        ConfigError: If source or dest paths escape harness directory
    """
    harness_dir_resolved = config.harness_dir.resolve()

    for init_file in config.init_files:
        source = (config.harness_dir / init_file.source).resolve()
        dest = (config.harness_dir / init_file.dest).resolve()

        # Path traversal protection
        if not source.is_relative_to(harness_dir_resolved):
            raise ConfigError(
                f"init_files source escapes harness directory: {init_file.source}"
            )
        if not dest.is_relative_to(harness_dir_resolved):
            raise ConfigError(
                f"init_files dest escapes harness directory: {init_file.dest}"
            )

        if not dest.exists():
            if not source.exists():
                logger.warning("init file source not found: %s", source)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, dest)
            print(f"Copied {init_file.source} to {dest}")


async def run_agent(config: HarnessConfig) -> None:
    """Run the autonomous agent loop.

    Args:
        config: Harness configuration
    """
    # Create tracker
    if config.tracking.type == "json_checklist":
        tracker: ProgressTracker = JsonChecklistTracker(
            file_path=config.harness_dir / config.tracking.file,
            passing_field=config.tracking.passing_field,
        )
    elif config.tracking.type == "notes_file":
        tracker = NotesFileTracker(file_path=config.harness_dir / config.tracking.file)
    else:
        tracker = NoneTracker()

    # Load session state
    state = _load_session_state(config)

    # Print startup banner
    print("\n" + "=" * BANNER_WIDTH)
    print("  AGENT HARNESS")
    print("=" * BANNER_WIDTH)
    print(f"\nProject directory: {config.project_dir}")
    print(f"\nHarness directory: {config.harness_dir}")
    print(f"\nModel: {config.model}")
    print(f"\nMax iterations: {config.max_iterations or 'Unlimited'}")
    print()

    # Ensure project directory exists
    config.project_dir.mkdir(parents=True, exist_ok=True)

    # Copy init files on first run
    copy_init_files(config)

    # Show initial progress
    if tracker.is_initialized():
        tracker.display_summary()

    # Main loop
    iteration = 0
    consecutive_errors = 0
    last_error_message = ""
    exit_reason = "MAX ITERATIONS"

    while True:
        iteration += 1
        state["session_number"] = state.get("session_number", 0) + 1

        # Check max iterations
        if config.max_iterations and iteration > config.max_iterations:
            print(f"\nReached max iterations ({config.max_iterations})")
            break

        # Select phase
        phase = select_phase(config, state)

        if phase is not None:
            phase_name = phase.name
            prompt = phase.prompt
        elif config.phases:
            # All phases are run_once and completed
            print("\nAll phases completed.")
            exit_reason = "ALL COMPLETE"
            break
        else:
            # No phases configured — use a generic continuation prompt
            phase_name = "agent"
            prompt = "Begin working."

        # Build prompt with error context if needed
        if last_error_message:
            prompt = (
                f"Note: The previous session encountered an error: {last_error_message[:500]}\n"
                "Please continue with your work.\n\n"
            ) + prompt

        # Print session header
        print("\n" + "=" * BANNER_WIDTH)
        print(f"  SESSION {state['session_number']}: {phase_name.upper()}")
        print("=" * BANNER_WIDTH)
        print()

        # Create client (fresh context each session)
        client = create_client(config)

        # Run session
        async with client:
            status, response = await run_agent_session(client, prompt)

        # Handle status
        if status == "continue":
            consecutive_errors = 0
            last_error_message = ""

            # Mark run_once phase as completed
            if phase is not None and phase.run_once and phase.name not in state["completed_phases"]:
                state["completed_phases"].append(phase.name)

            print(f"\nAgent will auto-continue in {config.auto_continue_delay}s...")
            tracker.display_summary()

            if tracker.is_complete():
                print("\n✓ All items passing! Agent work is complete.")
                exit_reason = "ALL COMPLETE"
                _save_session_state(config, state)
                break

            _save_session_state(config, state)
            await asyncio.sleep(config.auto_continue_delay)
        elif status == "error":
            _save_session_state(config, state)

            consecutive_errors += 1
            last_error_message = response

            backoff_delay = min(
                config.error_recovery.initial_backoff_seconds
                * (config.error_recovery.backoff_multiplier ** (consecutive_errors - 1)),
                config.error_recovery.max_backoff_seconds,
            )

            print(
                f"\nSession encountered an error "
                f"(attempt {consecutive_errors}/{config.error_recovery.max_consecutive_errors})"
            )

            if consecutive_errors >= config.error_recovery.max_consecutive_errors:
                print(
                    f"\nReached maximum consecutive errors "
                    f"({config.error_recovery.max_consecutive_errors})"
                )
                exit_reason = "TOO MANY ERRORS"
                break

            print(f"Will retry with a fresh session in {backoff_delay:.1f}s...")
            await asyncio.sleep(backoff_delay)

    # Final summary
    print("\n" + "=" * BANNER_WIDTH)
    print(f"  {exit_reason}")
    print("=" * BANNER_WIDTH)
    print(f"\nOutput directory: {config.project_dir}")
    tracker.display_summary()

    if config.post_run_instructions:
        print("\n" + "-" * BANNER_WIDTH)
        print("  NEXT STEPS:")
        print("-" * BANNER_WIDTH)
        for instruction in config.post_run_instructions:
            print(f"  {instruction}")
        print("-" * BANNER_WIDTH)

    print("\nDone!")
