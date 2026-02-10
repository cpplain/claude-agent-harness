"""
Prompt Loading
==============

Loads prompt content from inline strings or file: references.
Handles init_files copying to harness_dir on first run.
"""

from __future__ import annotations

import logging
import shutil

from agent_harness.config import ConfigError, HarnessConfig

logger = logging.getLogger(__name__)


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
