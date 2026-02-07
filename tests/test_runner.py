"""
Runner Tests
============

Tests for phase selection, conditions, session state, and max_iterations.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness.config import HarnessConfig, PhaseConfig
from agent_harness.runner import (
    evaluate_condition,
    select_phase,
    _load_session_state,
    _save_session_state,
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

    def test_unknown_condition_is_true(self) -> None:
        self.assertTrue(evaluate_condition("unknown:something", Path("/tmp")))


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


if __name__ == "__main__":
    unittest.main()
