"""
CLI Interface
=============

Argument parsing and subcommand dispatch for the agent harness.
Run with: python -m agent_harness <command> [options]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from agent_harness.config import CONFIG_DIR_NAME, DEFAULT_BUILTIN_TOOLS, DEFAULT_MODEL, ConfigError, load_config
from agent_harness.runner import run_agent
from agent_harness.verify import run_verify


INIT_CONFIG_TEMPLATE = """\
# Agent Harness Configuration
# See README.md for full reference

# --- Agent ---
model = "{DEFAULT_MODEL}"
system_prompt = "You are a helpful coding assistant."
# Or reference a file:
# system_prompt = "file:prompts/system.md"

# --- Session ---
max_turns = 1000
# max_iterations = 10
auto_continue_delay = 3
# --- Tools ---
[tools]
builtin = {DEFAULT_BUILTIN_TOOLS}

# [tools.mcp_servers.puppeteer]
# command = "npx"
# args = ["puppeteer-mcp-server"]

# --- Security ---
[security]
permission_mode = "acceptEdits"
allowed_paths = ["./**"]

[security.sandbox]
enabled = true
auto_allow_bash_if_sandboxed = true

# Omit [security.bash] for no bash security hook (sandbox handles it)
# [security.bash]
# allowed_commands = ["ls", "cat", "npm", "node", "git"]
#
# [security.bash.extra_validators.pkill]
# allowed_targets = ["node", "npm"]

# --- Progress Tracking ---
[tracking]
type = "none"
# type = "json_checklist"
# file = "feature_list.json"
# passing_field = "passes"

# --- Phases (optional) ---
# [[phases]]
# name = "initializer"
# prompt = "file:prompts/initializer.md"
# run_once = true
# condition = "not_exists:.agent-harness/feature_list.json"
#
# [[phases]]
# name = "coding"
# prompt = "file:prompts/coding.md"

# --- Init Files (copied to harness dir on first run) ---
# [[init_files]]
# source = "prompts/app_spec.txt"
# dest = "app_spec.txt"
"""


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add --project-dir and --harness-dir to a parser."""
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path("."),
        help="Agent's working directory (default: current directory)",
    )
    parser.add_argument(
        "--harness-dir",
        type=Path,
        default=None,
        help="Path to .agent-harness/ directory (default: project-dir/.agent-harness/)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="agent_harness",
        description="Generic harness for long-running autonomous coding agents",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Run the agent loop")
    _add_common_args(run_parser)
    run_parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Override max iterations from config",
    )
    run_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override model from config",
    )

    # verify subcommand
    verify_parser = subparsers.add_parser("verify", help="Check setup and configuration")
    _add_common_args(verify_parser)

    # init subcommand
    init_parser = subparsers.add_parser("init", help="Scaffold .agent-harness/ with starter config")
    _add_common_args(init_parser)

    return parser


def cmd_run(args: argparse.Namespace) -> None:
    """Execute the run subcommand."""
    project_dir = args.project_dir.resolve()
    harness_dir = args.harness_dir.resolve() if args.harness_dir else None

    try:
        config = load_config(project_dir, harness_dir, {
            "model": args.model,
            "max_iterations": args.max_iterations,
        })
    except ConfigError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    try:
        asyncio.run(run_agent(config))
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        print("To resume, run the same command again")
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise


def cmd_verify(args: argparse.Namespace) -> None:
    """Execute the verify subcommand."""
    project_dir = args.project_dir.resolve()
    harness_dir = args.harness_dir.resolve() if args.harness_dir else None

    results = run_verify(project_dir, harness_dir)

    print("\nVerification Results:")
    print("-" * 50)

    for result in results:
        print(result)

    print("-" * 50)

    fails = sum(1 for r in results if r.status == "FAIL")
    warns = sum(1 for r in results if r.status == "WARN")
    passes = sum(1 for r in results if r.status == "PASS")

    print(f"\n  {passes} passed, {warns} warnings, {fails} failed")

    if fails > 0:
        print("\n  Fix the FAIL items above before running the agent.")
        sys.exit(1)

    if warns > 0:
        print("\n  Warnings are non-blocking but may cause issues.")


def cmd_init(args: argparse.Namespace) -> None:
    """Execute the init subcommand."""
    project_dir = args.project_dir.resolve()
    harness_dir = args.harness_dir.resolve() if args.harness_dir else project_dir / CONFIG_DIR_NAME

    config_file = harness_dir / "config.toml"
    if config_file.exists():
        print(f"Config already exists: {config_file}")
        print("Remove it first if you want to reinitialize.")
        sys.exit(1)

    harness_dir.mkdir(parents=True, exist_ok=True)
    (harness_dir / "prompts").mkdir(exist_ok=True)
    config_file.write_text(
        INIT_CONFIG_TEMPLATE.replace("{DEFAULT_MODEL}", DEFAULT_MODEL)
        .replace("{DEFAULT_BUILTIN_TOOLS}", json.dumps(DEFAULT_BUILTIN_TOOLS))
    )

    print(f"Created {harness_dir}/")
    print(f"  - config.toml (edit this to configure your project)")
    print(f"  - prompts/ (put prompt files here)")
    print()
    print("Next steps:")
    print(f"  1. Edit {config_file}")
    print(f"  2. Run: python -m agent_harness verify --project-dir {project_dir}")
    print(f"  3. Run: python -m agent_harness run --project-dir {project_dir}")


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    {"run": cmd_run, "verify": cmd_verify, "init": cmd_init}[args.command](args)
