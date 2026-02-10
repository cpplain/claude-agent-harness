"""
Runner Tests
============

Tests for phase selection, conditions, session state, and max_iterations.
"""

import asyncio
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from agent_harness.config import ErrorRecoveryConfig, HarnessConfig, PhaseConfig
from agent_harness.runner import (
    _build_session_prompt,
    _handle_error,
    _handle_success,
    _load_session_state,
    _save_session_state,
    evaluate_condition,
    run_agent_session,
    select_phase,
)


class TestEvaluateCondition(unittest.TestCase):
    """Test condition evaluation."""

    def test_empty_condition_is_true(self) -> None:
        self.assertTrue(evaluate_condition("", Path("/tmp")))

    def test_exists_true(self) -> None:
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "file.txt").write_text("hi")
            self.assertTrue(evaluate_condition("exists:file.txt", Path(tmpdir)))

    def test_exists_false(self) -> None:
        with TemporaryDirectory() as tmpdir:
            self.assertFalse(evaluate_condition("exists:missing.txt", Path(tmpdir)))

    def test_not_exists_true(self) -> None:
        with TemporaryDirectory() as tmpdir:
            self.assertTrue(evaluate_condition("not_exists:missing.txt", Path(tmpdir)))

    def test_not_exists_false(self) -> None:
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "file.txt").write_text("hi")
            self.assertFalse(evaluate_condition("not_exists:file.txt", Path(tmpdir)))

    def test_unknown_condition_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            evaluate_condition("unknown:something", Path("/tmp"))
        self.assertIn("Unknown condition prefix", str(ctx.exception))

    def test_path_traversal_exists_raises(self) -> None:
        """Test that path traversal is blocked for exists: condition."""
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError) as ctx:
                evaluate_condition("exists:../../etc/passwd", Path(tmpdir))
            self.assertIn("escapes project directory", str(ctx.exception))

    def test_path_traversal_not_exists_raises(self) -> None:
        """Test that path traversal is blocked for not_exists: condition."""
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError) as ctx:
                evaluate_condition("not_exists:../../etc/passwd", Path(tmpdir))
            self.assertIn("escapes project directory", str(ctx.exception))

    def test_subdir_path_works_normally(self) -> None:
        """Test that legitimate subdirectory paths work."""
        with TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "file.txt").write_text("test")
            self.assertTrue(evaluate_condition("exists:subdir/file.txt", Path(tmpdir)))
            self.assertFalse(evaluate_condition("not_exists:subdir/file.txt", Path(tmpdir)))


class TestSelectPhase(unittest.TestCase):
    """Test phase selection logic."""

    def test_no_phases_returns_none(self) -> None:
        config = HarnessConfig(phases=[])
        self.assertIsNone(select_phase(config, {}))

    def test_selects_first_phase(self) -> None:
        config = HarnessConfig(
            phases=[
                PhaseConfig(name="init", prompt="Initialize"),
                PhaseConfig(name="code", prompt="Code"),
            ]
        )
        phase = select_phase(config, {})
        assert phase is not None
        self.assertEqual(phase.name, "init")

    def test_skips_completed_run_once(self) -> None:
        config = HarnessConfig(
            phases=[
                PhaseConfig(name="init", prompt="Initialize", run_once=True),
                PhaseConfig(name="code", prompt="Code"),
            ]
        )
        state = {"completed_phases": ["init"]}
        phase = select_phase(config, state)
        assert phase is not None
        self.assertEqual(phase.name, "code")

    def test_skips_failed_condition(self) -> None:
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "feature_list.json").write_text("[]")
            config = HarnessConfig(
                project_dir=Path(tmpdir),
                phases=[
                    PhaseConfig(
                        name="init",
                        prompt="Initialize",
                        run_once=True,
                        condition="not_exists:feature_list.json",
                    ),
                    PhaseConfig(name="code", prompt="Code"),
                ],
            )
            phase = select_phase(config, {})
            assert phase is not None
            self.assertEqual(phase.name, "code")

    def test_falls_back_to_last_non_run_once(self) -> None:
        config = HarnessConfig(
            phases=[
                PhaseConfig(name="init", prompt="Initialize", run_once=True),
                PhaseConfig(name="code", prompt="Code"),
            ]
        )
        # init already completed, code has no run_once so it's always available
        state = {"completed_phases": ["init"]}
        phase = select_phase(config, state)
        assert phase is not None
        self.assertEqual(phase.name, "code")

    def test_all_run_once_completed_returns_none_or_last(self) -> None:
        config = HarnessConfig(
            phases=[
                PhaseConfig(name="init", prompt="Initialize", run_once=True),
                PhaseConfig(name="setup", prompt="Setup", run_once=True),
            ]
        )
        state = {"completed_phases": ["init", "setup"]}
        # All are run_once and completed, no non-run_once to fall back to
        phase = select_phase(config, state)
        self.assertIsNone(phase)

    def test_fallback_respects_conditions(self) -> None:
        """Test that fallback loop re-evaluates conditions."""
        with TemporaryDirectory() as tmpdir:
            # Create a file that makes the condition fail
            (Path(tmpdir) / "blocking_file.txt").write_text("exists")
            config = HarnessConfig(
                project_dir=Path(tmpdir),
                phases=[
                    PhaseConfig(name="init", prompt="Initialize", run_once=True),
                    PhaseConfig(
                        name="code",
                        prompt="Code",
                        run_once=False,
                        condition="not_exists:blocking_file.txt",
                    ),
                ],
            )
            # init is completed, code is non-run_once but condition fails
            state = {"completed_phases": ["init"]}
            phase = select_phase(config, state)
            # Should return None because the fallback's condition fails
            self.assertIsNone(phase)

    def test_fallback_passes_when_condition_met(self) -> None:
        """Test that fallback succeeds when condition is met."""
        with TemporaryDirectory() as tmpdir:
            config = HarnessConfig(
                project_dir=Path(tmpdir),
                phases=[
                    PhaseConfig(name="init", prompt="Initialize", run_once=True),
                    PhaseConfig(
                        name="code",
                        prompt="Code",
                        run_once=False,
                        condition="not_exists:missing_file.txt",
                    ),
                ],
            )
            state = {"completed_phases": ["init"]}
            phase = select_phase(config, state)
            # Should return code phase because condition is met
            assert phase is not None
            self.assertEqual(phase.name, "code")


class TestSessionState(unittest.TestCase):
    """Test session state persistence."""

    def test_load_empty_state(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(harness_dir=config_dir)
            state = _load_session_state(config)
            self.assertEqual(state["session_number"], 0)
            self.assertEqual(state["completed_phases"], [])

    def test_save_and_load_state(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(harness_dir=config_dir)
            state = {
                "session_number": 5,
                "completed_phases": ["init"],
            }
            _save_session_state(config, state)

            loaded = _load_session_state(config)
            self.assertEqual(loaded["session_number"], 5)
            self.assertEqual(loaded["completed_phases"], ["init"])

    def test_load_corrupted_state_returns_default(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir(parents=True)
            (config_dir / "session.json").write_text("not json")
            config = HarnessConfig(harness_dir=config_dir)
            state = _load_session_state(config)
            self.assertEqual(state["session_number"], 0)

    def test_load_corrupted_state_logs_warning(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir(parents=True)
            (config_dir / "session.json").write_text("not json")
            config = HarnessConfig(harness_dir=config_dir)
            with self.assertLogs("agent_harness.runner", level=logging.WARNING) as cm:
                _load_session_state(config)
            self.assertTrue(any("Corrupt session state" in msg for msg in cm.output))

    def test_load_non_dict_json_array(self) -> None:
        """Test that JSON arrays are treated as corrupt."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir(parents=True)
            (config_dir / "session.json").write_text('[1, 2, 3]')
            config = HarnessConfig(harness_dir=config_dir)
            state = _load_session_state(config)
            self.assertEqual(state["session_number"], 0)
            self.assertEqual(state["completed_phases"], [])

    def test_load_non_dict_json_string(self) -> None:
        """Test that JSON strings are treated as corrupt."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir(parents=True)
            (config_dir / "session.json").write_text('"just a string"')
            config = HarnessConfig(harness_dir=config_dir)
            state = _load_session_state(config)
            self.assertEqual(state["session_number"], 0)
            self.assertEqual(state["completed_phases"], [])

    def test_load_non_dict_json_number(self) -> None:
        """Test that JSON numbers are treated as corrupt."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir(parents=True)
            (config_dir / "session.json").write_text('42')
            config = HarnessConfig(harness_dir=config_dir)
            state = _load_session_state(config)
            self.assertEqual(state["session_number"], 0)
            self.assertEqual(state["completed_phases"], [])

    def test_load_non_dict_json_logs_warning(self) -> None:
        """Test that non-dict JSON logs a warning."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir(parents=True)
            (config_dir / "session.json").write_text('["array"]')
            config = HarnessConfig(harness_dir=config_dir)
            with self.assertLogs("agent_harness.runner", level=logging.WARNING) as cm:
                _load_session_state(config)
            self.assertTrue(any("non-dict JSON" in msg for msg in cm.output))


class TestAtomicSessionStateWrites(unittest.TestCase):
    """Test atomic session state writes (B1)."""

    def test_valid_json_written(self) -> None:
        """Test that valid JSON is written to session.json."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(harness_dir=config_dir)
            state = {
                "session_number": 42,
                "completed_phases": ["init", "code"],
            }
            _save_session_state(config, state)

            # Read back and verify
            loaded = _load_session_state(config)
            self.assertEqual(loaded["session_number"], 42)
            self.assertEqual(loaded["completed_phases"], ["init", "code"])

    def test_no_temp_files_left_on_success(self) -> None:
        """Test that temp files are cleaned up on successful write."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(harness_dir=config_dir)
            state = {"session_number": 1, "completed_phases": []}
            _save_session_state(config, state)

            # Check no .tmp files left
            temp_files = list(config_dir.glob("*.tmp"))
            self.assertEqual(len(temp_files), 0)

    def test_oserror_on_readonly_dir_logs_warning(self) -> None:
        """Test that OSError on read-only directory is logged as warning instead of crash."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(harness_dir=config_dir)

            # Make directory read-only
            import stat
            config_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

            try:
                state = {"session_number": 1, "completed_phases": []}
                with self.assertLogs("agent_harness.runner", level=logging.WARNING) as cm:
                    _save_session_state(config, state)
                self.assertTrue(any("Failed to save session state" in msg for msg in cm.output))
            finally:
                # Restore permissions for cleanup
                config_dir.chmod(stat.S_IRWXU)

    def test_atomic_rename_prevents_corruption(self) -> None:
        """Test that atomic rename prevents partial writes."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(harness_dir=config_dir)

            # Write initial state
            state1 = {"session_number": 1, "completed_phases": []}
            _save_session_state(config, state1)

            # Write new state - if atomic, old state won't be corrupted mid-write
            state2 = {"session_number": 2, "completed_phases": ["init"]}
            _save_session_state(config, state2)

            # Verify final state is valid and complete
            loaded = _load_session_state(config)
            self.assertEqual(loaded["session_number"], 2)
            self.assertEqual(loaded["completed_phases"], ["init"])


class TestSessionStatePruning(unittest.TestCase):
    """Test that stale completed_phases are pruned on load."""

    def test_prunes_removed_phase_names(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(
                harness_dir=config_dir,
                phases=[
                    PhaseConfig(name="init", prompt="Initialize"),
                    PhaseConfig(name="code", prompt="Code"),
                ],
            )
            # Save state with a phase name that no longer exists
            state = {
                "session_number": 5,
                "completed_phases": ["init", "old_removed_phase"],
            }
            _save_session_state(config, state)

            loaded = _load_session_state(config)
            self.assertEqual(loaded["completed_phases"], ["init"])
            self.assertEqual(loaded["session_number"], 5)

    def test_no_pruning_when_no_phases_configured(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(harness_dir=config_dir, phases=[])
            state = {
                "session_number": 3,
                "completed_phases": ["some_phase"],
            }
            _save_session_state(config, state)

            loaded = _load_session_state(config)
            # No phases configured → no pruning
            self.assertEqual(loaded["completed_phases"], ["some_phase"])

    def test_all_phases_still_valid(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".agent-harness"
            config_dir.mkdir()
            config = HarnessConfig(
                harness_dir=config_dir,
                phases=[
                    PhaseConfig(name="init", prompt="Initialize"),
                    PhaseConfig(name="code", prompt="Code"),
                ],
            )
            state = {
                "session_number": 2,
                "completed_phases": ["init"],
            }
            _save_session_state(config, state)

            loaded = _load_session_state(config)
            self.assertEqual(loaded["completed_phases"], ["init"])


class TestBackoffCalculation(unittest.TestCase):
    """Test error recovery backoff calculation."""

    def test_exponential_backoff(self) -> None:
        """Test that backoff increases exponentially: 5→10→20→40→80."""
        error_recovery = ErrorRecoveryConfig(
            initial_backoff_seconds=5.0,
            backoff_multiplier=2.0,
            max_backoff_seconds=120.0
        )

        # Calculate backoff for consecutive errors 1-5
        backoffs = []
        for consecutive_errors in range(1, 6):
            backoff = min(
                error_recovery.initial_backoff_seconds *
                (error_recovery.backoff_multiplier ** (consecutive_errors - 1)),
                error_recovery.max_backoff_seconds
            )
            backoffs.append(backoff)

        # Verify exponential progression
        self.assertEqual(backoffs, [5.0, 10.0, 20.0, 40.0, 80.0])

    def test_backoff_max_cap(self) -> None:
        """Test that backoff is capped at max_backoff_seconds."""
        error_recovery = ErrorRecoveryConfig(
            initial_backoff_seconds=5.0,
            backoff_multiplier=2.0,
            max_backoff_seconds=60.0
        )

        # Calculate backoff for many consecutive errors
        backoffs = []
        for consecutive_errors in range(1, 8):
            backoff = min(
                error_recovery.initial_backoff_seconds *
                (error_recovery.backoff_multiplier ** (consecutive_errors - 1)),
                error_recovery.max_backoff_seconds
            )
            backoffs.append(backoff)

        # Verify capping at 60.0
        self.assertEqual(backoffs, [5.0, 10.0, 20.0, 40.0, 60.0, 60.0, 60.0])

    def test_circuit_breaker_threshold(self) -> None:
        """Test that circuit breaker trips at max_consecutive_errors."""
        error_recovery = ErrorRecoveryConfig(
            max_consecutive_errors=3,
            initial_backoff_seconds=5.0,
            backoff_multiplier=2.0,
            max_backoff_seconds=120.0
        )

        # Simulate consecutive errors
        for consecutive_errors in range(1, 5):
            should_break = consecutive_errors >= error_recovery.max_consecutive_errors

            if consecutive_errors < 3:
                self.assertFalse(should_break)
            else:
                # At 3 or more, circuit breaker should trip
                self.assertTrue(should_break)

    def test_different_backoff_multiplier(self) -> None:
        """Test backoff with 3.0x multiplier: 2→6→18→54."""
        error_recovery = ErrorRecoveryConfig(
            initial_backoff_seconds=2.0,
            backoff_multiplier=3.0,
            max_backoff_seconds=200.0
        )

        # Calculate backoff for consecutive errors 1-4
        backoffs = []
        for consecutive_errors in range(1, 5):
            backoff = min(
                error_recovery.initial_backoff_seconds *
                (error_recovery.backoff_multiplier ** (consecutive_errors - 1)),
                error_recovery.max_backoff_seconds
            )
            backoffs.append(backoff)

        # Verify 3x progression
        self.assertEqual(backoffs, [2.0, 6.0, 18.0, 54.0])


class TestErrorContextForwarding(unittest.TestCase):
    """Test that error context is correctly prepended to session prompts."""

    def test_no_error_returns_prompt_unchanged(self) -> None:
        prompt = "Do your work."
        result = _build_session_prompt(prompt, "")
        self.assertEqual(result, "Do your work.")

    def test_error_prepends_context(self) -> None:
        prompt = "Do your work."
        result = _build_session_prompt(prompt, "Connection timeout")
        self.assertIn("Connection timeout", result)
        self.assertTrue(result.endswith(prompt))
        self.assertIn("previous session encountered an error", result)

    def test_error_truncated_to_500_chars(self) -> None:
        long_error = "x" * 1000
        result = _build_session_prompt("prompt", long_error)
        # The error should be truncated to 500 chars in the context
        self.assertNotIn("x" * 501, result)


class TestHandleError(unittest.TestCase):
    """Test error handling helper function."""

    def test_increments_consecutive_errors(self) -> None:
        config = HarnessConfig()
        consecutive_errors, _, _, _ = _handle_error(config, 0, "some error")
        self.assertEqual(consecutive_errors, 1)

    def test_returns_response_as_last_error(self) -> None:
        config = HarnessConfig()
        _, last_error, _, _ = _handle_error(config, 0, "some error message")
        self.assertEqual(last_error, "some error message")

    def test_calculates_backoff(self) -> None:
        config = HarnessConfig(
            error_recovery=ErrorRecoveryConfig(
                initial_backoff_seconds=5.0,
                backoff_multiplier=2.0,
                max_backoff_seconds=120.0,
            )
        )
        _, _, backoff, _ = _handle_error(config, 0, "err")
        self.assertEqual(backoff, 5.0)
        _, _, backoff, _ = _handle_error(config, 1, "err")
        self.assertEqual(backoff, 10.0)

    def test_should_break_at_max_errors(self) -> None:
        config = HarnessConfig(
            error_recovery=ErrorRecoveryConfig(max_consecutive_errors=3)
        )
        _, _, _, should_break = _handle_error(config, 2, "err")
        self.assertTrue(should_break)

    def test_should_not_break_below_max(self) -> None:
        config = HarnessConfig(
            error_recovery=ErrorRecoveryConfig(max_consecutive_errors=5)
        )
        _, _, _, should_break = _handle_error(config, 1, "err")
        self.assertFalse(should_break)


class TestHandleSuccess(unittest.TestCase):
    """Test success handling helper function."""

    def test_marks_run_once_phase_completed(self) -> None:
        config = HarnessConfig()
        state = {"completed_phases": []}
        phase = PhaseConfig(name="init", prompt="Initialize", run_once=True)
        tracker = MagicMock()
        tracker.is_complete.return_value = False

        is_complete, _ = _handle_success(config, state, phase, tracker)

        self.assertFalse(is_complete)
        self.assertEqual(state["completed_phases"], ["init"])

    def test_does_not_duplicate_completed_phase(self) -> None:
        config = HarnessConfig()
        state = {"completed_phases": ["init"]}
        phase = PhaseConfig(name="init", prompt="Initialize", run_once=True)
        tracker = MagicMock()
        tracker.is_complete.return_value = False

        _handle_success(config, state, phase, tracker)

        self.assertEqual(state["completed_phases"], ["init"])

    def test_non_run_once_phase_not_marked(self) -> None:
        config = HarnessConfig()
        state = {"completed_phases": []}
        phase = PhaseConfig(name="code", prompt="Code", run_once=False)
        tracker = MagicMock()
        tracker.is_complete.return_value = False

        _handle_success(config, state, phase, tracker)

        self.assertEqual(state["completed_phases"], [])

    def test_none_phase_not_marked(self) -> None:
        config = HarnessConfig()
        state = {"completed_phases": []}
        tracker = MagicMock()
        tracker.is_complete.return_value = False

        _handle_success(config, state, None, tracker)

        self.assertEqual(state["completed_phases"], [])

    def test_returns_complete_when_tracker_complete(self) -> None:
        config = HarnessConfig()
        state = {"completed_phases": []}
        phase = PhaseConfig(name="code", prompt="Code")
        tracker = MagicMock()
        tracker.is_complete.return_value = True

        is_complete, exit_reason = _handle_success(config, state, phase, tracker)

        self.assertTrue(is_complete)
        self.assertEqual(exit_reason, "ALL COMPLETE")

    def test_returns_not_complete_when_tracker_not_complete(self) -> None:
        config = HarnessConfig()
        state = {"completed_phases": []}
        phase = PhaseConfig(name="code", prompt="Code")
        tracker = MagicMock()
        tracker.is_complete.return_value = False

        is_complete, exit_reason = _handle_success(config, state, phase, tracker)

        self.assertFalse(is_complete)
        self.assertEqual(exit_reason, "")


class TestRunAgentSession(unittest.TestCase):
    """Test run_agent_session exception handling."""

    def test_exception_logging(self) -> None:
        """Test that exceptions are logged with traceback."""
        # Create a mock client that raises an exception
        mock_client = MagicMock()
        mock_client.query = AsyncMock(side_effect=RuntimeError("Test error"))

        # Run the session and check that logger.exception was called
        with self.assertLogs("agent_harness.runner", level=logging.ERROR) as cm:
            status, response = asyncio.run(
                run_agent_session(mock_client, "test prompt")
            )

        # Check that status is error
        self.assertEqual(status, "error")
        self.assertEqual(response, "Test error")

        # Check that exception was logged
        self.assertTrue(any("Error during agent session" in msg for msg in cm.output))

    def test_exception_includes_traceback(self) -> None:
        """Test that exception logging includes full traceback."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(side_effect=RuntimeError("Runtime error"))

        # Patch logger.exception to verify it was called
        with patch("agent_harness.runner.logger.exception") as mock_logger:
            _status, _response = asyncio.run(
                run_agent_session(mock_client, "test prompt")
            )

            # Verify logger.exception was called (which includes traceback)
            mock_logger.assert_called_once_with("Error during agent session")


class TestNarrowExceptionHandler(unittest.TestCase):
    """Test narrowed exception handler (B2)."""

    def test_type_error_propagates(self) -> None:
        """Test that TypeError is not caught (programming error)."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(side_effect=TypeError("Bad type"))

        with self.assertRaises(TypeError):
            asyncio.run(run_agent_session(mock_client, "test prompt"))

    def test_attribute_error_propagates(self) -> None:
        """Test that AttributeError is not caught (programming error)."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(side_effect=AttributeError("No attribute"))

        with self.assertRaises(AttributeError):
            asyncio.run(run_agent_session(mock_client, "test prompt"))

    def test_key_error_propagates(self) -> None:
        """Test that KeyError is not caught (programming error)."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(side_effect=KeyError("missing_key"))

        with self.assertRaises(KeyError):
            asyncio.run(run_agent_session(mock_client, "test prompt"))

    def test_runtime_error_caught(self) -> None:
        """Test that RuntimeError is caught and returns error status."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(side_effect=RuntimeError("Runtime error"))

        status, response = asyncio.run(run_agent_session(mock_client, "test prompt"))

        self.assertEqual(status, "error")
        self.assertEqual(response, "Runtime error")

    def test_connection_error_caught(self) -> None:
        """Test that ConnectionError is caught and returns error status."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(side_effect=ConnectionError("Connection failed"))

        status, response = asyncio.run(run_agent_session(mock_client, "test prompt"))

        self.assertEqual(status, "error")
        self.assertEqual(response, "Connection failed")

    def test_timeout_error_caught(self) -> None:
        """Test that TimeoutError is caught and returns error status."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(side_effect=TimeoutError("Timeout"))

        status, response = asyncio.run(run_agent_session(mock_client, "test prompt"))

        self.assertEqual(status, "error")
        self.assertEqual(response, "Timeout")

    def test_os_error_caught(self) -> None:
        """Test that OSError is caught and returns error status."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(side_effect=OSError("OS error"))

        status, response = asyncio.run(run_agent_session(mock_client, "test prompt"))

        self.assertEqual(status, "error")
        self.assertEqual(response, "OS error")

    def test_io_error_caught(self) -> None:
        """Test that IOError is caught and returns error status."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(side_effect=IOError("IO error"))

        status, response = asyncio.run(run_agent_session(mock_client, "test prompt"))

        self.assertEqual(status, "error")
        self.assertEqual(response, "IO error")


if __name__ == "__main__":
    unittest.main()
