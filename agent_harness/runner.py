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
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_harness.config import HarnessConfig, PhaseConfig
from agent_harness.client_factory import create_client
from agent_harness.display import print_banner, print_progress, print_final_summary, print_session_header
from agent_harness.prompts import copy_init_files
from agent_harness.tracking import create_tracker, ProgressTracker


# Session state file
SESSION_STATE_FILE = "session.json"

# Display length constants
MAX_TOOL_INPUT_DISPLAY_LEN = 200
MAX_ERROR_DISPLAY_LEN = 500


def _load_session_state(config: HarnessConfig) -> dict:
    """Load session state from .agent-harness/session.json.

    Prunes completed_phases entries that don't match any configured phase name,
    handling renames or removals gracefully.
    """
    state_file = config.harness_dir / SESSION_STATE_FILE
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
    state_file = config.harness_dir / SESSION_STATE_FILE
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
        path = project_dir / condition[7:]
        # Protect against path traversal
        resolved = path.resolve()
        if not resolved.is_relative_to(project_dir.resolve()):
            raise ValueError(
                f"Path {condition[7:]!r} escapes project directory"
            )
        return path.exists()
    elif condition.startswith("not_exists:"):
        path = project_dir / condition[11:]
        # Protect against path traversal
        resolved = path.resolve()
        if not resolved.is_relative_to(project_dir.resolve()):
            raise ValueError(
                f"Path {condition[11:]!r} escapes project directory"
            )
        return not path.exists()

    raise ValueError(
        f"Unknown condition prefix in {condition!r} — "
        f"only 'exists:' and 'not_exists:' are supported"
    )


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

        response_text = ""
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
                        print(block.text, end="", flush=True)
                    elif isinstance(block, ToolUseBlock):
                        print(f"\n[Tool: {block.name}]", flush=True)
                        input_str = str(block.input)
                        if len(input_str) > MAX_TOOL_INPUT_DISPLAY_LEN:
                            print(f"   Input: {input_str[:MAX_TOOL_INPUT_DISPLAY_LEN]}...", flush=True)
                        else:
                            print(f"   Input: {input_str}", flush=True)

            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, ToolResultBlock):
                        result_content = block.content or ""
                        is_error = block.is_error or False

                        if is_error:
                            error_str = str(result_content)[:MAX_ERROR_DISPLAY_LEN]
                            if "blocked" in error_str.lower():
                                print(f"   [BLOCKED] {result_content}", flush=True)
                            else:
                                print(f"   [Error] {error_str}", flush=True)
                        else:
                            print("   [Done]", flush=True)

        print("\n" + "-" * 70 + "\n")
        return "continue", response_text

    except (OSError, IOError, ConnectionError, TimeoutError, RuntimeError) as e:
        logger.exception("Error during agent session")
        print(f"Error during agent session: {e}")
        return "error", str(e)


def _build_session_prompt(phase_prompt: str, last_error_message: str) -> str:
    """Build the session prompt, prepending error context if needed.

    Args:
        phase_prompt: The phase's prompt text
        last_error_message: Error message from the previous session, or ""

    Returns:
        The prompt to send to the agent
    """
    if last_error_message:
        truncated = last_error_message[:MAX_ERROR_DISPLAY_LEN]
        error_context = (
            f"Note: The previous session encountered an error: {truncated}\n"
            "Please continue with your work.\n\n"
        )
        return error_context + phase_prompt
    return phase_prompt


def _handle_error(
    config: HarnessConfig,
    consecutive_errors: int,
    response: str,
) -> tuple[int, str, float, bool]:
    """Handle an error status from a session.

    Args:
        config: Harness configuration
        consecutive_errors: Current consecutive error count
        response: Error response text

    Returns:
        (consecutive_errors, last_error_message, backoff_delay, should_break)
    """
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

    should_break = consecutive_errors >= config.error_recovery.max_consecutive_errors
    if should_break:
        print(
            f"\nReached maximum consecutive errors "
            f"({config.error_recovery.max_consecutive_errors})"
        )

    return consecutive_errors, last_error_message, backoff_delay, should_break


def _handle_success(
    config: HarnessConfig,
    state: dict,
    phase: Optional[PhaseConfig],
    tracker: ProgressTracker,
) -> tuple[bool, str]:
    """Handle a successful session.

    Marks run_once phases as completed, prints progress,
    and checks for completion.

    Args:
        config: Harness configuration
        state: Session state dict (mutated in place)
        phase: The phase that was run, or None
        tracker: Progress tracker

    Returns:
        (is_complete, exit_reason) — is_complete=True means agent should stop
    """
    # Mark run_once phase as completed
    if phase is not None and phase.run_once:
        completed = state.get("completed_phases", [])
        if phase.name not in completed:
            completed.append(phase.name)
            state["completed_phases"] = completed

    print(f"\nAgent will auto-continue in {config.auto_continue_delay}s...")
    print_progress(tracker)

    if tracker.is_complete():
        print("\n✓ All items passing! Agent work is complete.")
        return True, "ALL COMPLETE"

    return False, ""


async def run_agent(config: HarnessConfig) -> None:
    """Run the autonomous agent loop.

    Args:
        config: Harness configuration
    """
    # Create tracker
    tracker = create_tracker(config.tracking, config.harness_dir)

    # Load session state
    state = _load_session_state(config)

    # Print banner
    summary = {
        "Project directory": str(config.project_dir),
        "Harness directory": str(config.harness_dir),
        "Model": config.model,
    }
    if config.max_iterations:
        summary["Max iterations"] = str(config.max_iterations)
    else:
        summary["Max iterations"] = "Unlimited"

    print_banner("AGENT HARNESS", summary)

    # Ensure project directory exists
    config.project_dir.mkdir(parents=True, exist_ok=True)

    # Copy init files on first run
    copy_init_files(config)

    # Show initial progress
    if tracker.is_initialized():
        print_progress(tracker)

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
            exit_reason = "MAX ITERATIONS"
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
        prompt = _build_session_prompt(prompt, last_error_message)

        # Print session header
        print_session_header(state["session_number"], phase_name)

        # Create client (fresh context each session)
        client = create_client(config)

        # Run session
        status = "error"
        response = ""
        async with client:
            status, response = await run_agent_session(client, prompt)

        # Handle status
        if status == "continue":
            consecutive_errors = 0
            last_error_message = ""
            is_complete, exit_reason = _handle_success(config, state, phase, tracker)
            _save_session_state(config, state)
            if is_complete:
                break
            await asyncio.sleep(config.auto_continue_delay)
        elif status == "error":
            _save_session_state(config, state)
            consecutive_errors, last_error_message, backoff_delay, should_break = (
                _handle_error(config, consecutive_errors, response)
            )
            if should_break:
                exit_reason = "TOO MANY ERRORS"
                break

            print(f"Will retry with a fresh session in {backoff_delay:.1f}s...")
            await asyncio.sleep(backoff_delay)

    # Final summary
    print_final_summary(
        exit_reason=exit_reason,
        output_dir=str(config.project_dir),
        tracker=tracker,
        post_run_instructions=config.post_run_instructions,
    )
    print("\nDone!")
