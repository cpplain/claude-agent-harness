"""
Prompt Loading
==============

Loads prompt content from inline strings or file: references.
Handles init_files copying to harness_dir on first run.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from agent_harness.config import HarnessConfig, resolve_file_reference


def load_prompt(value: str, harness_dir: Path) -> str:
    """Load a prompt from an inline string or file: reference.

    Args:
        value: Inline prompt text or "file:path/to/prompt.md"
        harness_dir: Base directory for resolving file: references

    Returns:
        The prompt text
    """
    return resolve_file_reference(value, harness_dir)


def copy_init_files(config: HarnessConfig) -> None:
    """Copy init_files to harness_dir if they don't already exist.

    Args:
        config: Harness configuration with init_files and paths
    """
    for init_file in config.init_files:
        source = config.harness_dir / init_file.source
        dest = config.harness_dir / init_file.dest

        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, dest)
            print(f"Copied {init_file.source} to {dest}")
