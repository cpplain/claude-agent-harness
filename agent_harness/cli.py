"""
CLI Interface
=============

Argument parsing and subcommand dispatch for the agent harness.
Run with: uv run python -m agent_harness <command> [options]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from agent_harness.config import CONFIG_DIR_NAME, ConfigError, load_config
from agent_harness.runner import run_agent
from agent_harness.verify import print_verify_results, run_verify


DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

INIT_CONFIG_TEMPLATE = """\
# Agent Harness Configuration
# See README.md for full reference

# --- Agent ---
model = "claude-sonnet-4-5-20250929"
system_prompt = "You are a helpful coding assistant."
# Or reference a file:
# system_prompt = "file:prompts/system.md"

# --- Session ---
max_turns = 1000
# max_iterations = 10
auto_continue_delay = 3
# max_budget_usd = 5.0

# --- Tools ---
[tools]
builtin = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]

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

    cli_overrides = {
        "model": args.model,
        "max_iterations": args.max_iterations,
    }

    try:
        config = load_config(project_dir, harness_dir, cli_overrides)
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
    success = print_verify_results(results)

    if not success:
        sys.exit(1)


def cmd_init(args: argparse.Namespace) -> None:
    """Execute the init subcommand."""
    project_dir = args.project_dir.resolve()
    harness_dir = args.harness_dir.resolve() if args.harness_dir else project_dir / CONFIG_DIR_NAME

    if harness_dir.exists():
        config_file = harness_dir / "config.toml"
        if config_file.exists():
            print(f"Config already exists: {config_file}")
            print("Remove it first if you want to reinitialize.")
            sys.exit(1)

    harness_dir.mkdir(parents=True, exist_ok=True)
    (harness_dir / "prompts").mkdir(exist_ok=True)

    config_file = harness_dir / "config.toml"
    config_file.write_text(INIT_CONFIG_TEMPLATE)

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

    if args.command == "run":
        cmd_run(args)
    elif args.command == "verify":
        cmd_verify(args)
    elif args.command == "init":
        cmd_init(args)
