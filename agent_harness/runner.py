"""
Generic Agent Runner
====================

Main agent loop with phase selection, session state, and conditions.
Replaces the hardcoded agent.py with a fully configurable runner.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

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
from agent_harness.tracking import create_tracker


# Session state file
SESSION_STATE_FILE = "session.json"


def _load_session_state(config: HarnessConfig) -> dict:
    """Load session state from .agent-harness/session.json."""
    state_file = config.harness_dir / SESSION_STATE_FILE
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {"session_number": 0, "completed_phases": []}


def _save_session_state(config: HarnessConfig, state: dict) -> None:
    """Save session state to .agent-harness/session.json."""
    state_file = config.harness_dir / SESSION_STATE_FILE
    state_file.write_text(json.dumps(state, indent=2))


def evaluate_condition(condition: str, project_dir: Path) -> bool:
    """Evaluate a phase condition.

    Supported conditions:
        - "exists:<path>" — True if file exists relative to project_dir
        - "not_exists:<path>" — True if file does not exist
        - "" — Always True (no condition)

    Returns:
        True if the condition is met
    """
    if not condition:
        return True

    if condition.startswith("exists:"):
        path = project_dir / condition[7:]
        return path.exists()
    elif condition.startswith("not_exists:"):
        path = project_dir / condition[11:]
        return not path.exists()

    return True


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
                        if len(input_str) > 200:
                            print(f"   Input: {input_str[:200]}...", flush=True)
                        else:
                            print(f"   Input: {input_str}", flush=True)

            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, ToolResultBlock):
                        result_content = block.content or ""
                        is_error = block.is_error or False

                        if "blocked" in str(result_content).lower():
                            print(f"   [BLOCKED] {result_content}", flush=True)
                        elif is_error:
                            error_str = str(result_content)[:500]
                            print(f"   [Error] {error_str}", flush=True)
                        else:
                            print("   [Done]", flush=True)

        print("\n" + "-" * 70 + "\n")
        return "continue", response_text

    except Exception as e:
        print(f"Error during agent session: {e}")
        return "error", str(e)


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
        else:
            # No phases — use system prompt directly, prompt is empty
            phase_name = "agent"
            prompt = config.system_prompt

        # Prepend error context if there was an error in the previous session
        if last_error_message:
            error_context = f"Note: The previous session encountered an error: {last_error_message}\nPlease continue with your work.\n\n"
            prompt = error_context + prompt

        # Print session header
        print_session_header(state["session_number"], phase_name)

        # Create client (fresh context each session)
        client = create_client(config)

        # Run session
        status = "error"
        async with client:
            status, response = await run_agent_session(client, prompt)

        # Mark run_once phase as completed
        if phase is not None and phase.run_once and status == "continue":
            completed = state.get("completed_phases", [])
            if phase.name not in completed:
                completed.append(phase.name)
                state["completed_phases"] = completed

        # Save session state
        _save_session_state(config, state)

        # Handle status
        if status == "continue":
            # Reset error tracking on success
            consecutive_errors = 0
            last_error_message = ""

            print(f"\nAgent will auto-continue in {config.auto_continue_delay}s...")
            print_progress(tracker)

            # Check for completion
            if tracker.is_complete():
                print("\n✓ All items passing! Agent work is complete.")
                exit_reason = "ALL COMPLETE"
                break

            await asyncio.sleep(config.auto_continue_delay)
        elif status == "error":
            # Track error for recovery
            consecutive_errors += 1
            last_error_message = response

            # Calculate backoff delay
            backoff_delay = min(
                config.error_recovery.initial_backoff_seconds *
                (config.error_recovery.backoff_multiplier ** (consecutive_errors - 1)),
                config.error_recovery.max_backoff_seconds
            )

            print(f"\nSession encountered an error (attempt {consecutive_errors}/{config.error_recovery.max_consecutive_errors})")

            # Check circuit breaker
            if consecutive_errors >= config.error_recovery.max_consecutive_errors:
                print(f"\nReached maximum consecutive errors ({config.error_recovery.max_consecutive_errors})")
                exit_reason = "TOO MANY ERRORS"
                break

            print(f"Will retry with a fresh session in {backoff_delay:.1f}s...")
            await asyncio.sleep(backoff_delay)

        # Small delay between sessions
        if config.max_iterations is None or iteration < config.max_iterations:
            print("\nPreparing next session...\n")
            await asyncio.sleep(1)

    # Final summary
    print_final_summary(
        exit_reason=exit_reason,
        output_dir=str(config.project_dir),
        tracker=tracker,
        post_run_instructions=config.post_run_instructions,
    )
    print("\nDone!")
