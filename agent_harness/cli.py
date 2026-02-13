"""
CLI Interface
=============

Argument parsing and subcommand dispatch for the agent harness.
Run with: python -m agent_harness <command> [options]
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

from agent_harness.config import CONFIG_DIR_NAME, ConfigError, load_config
from agent_harness.runner import run_agent
from agent_harness.verify import run_verify


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add --project-dir to a parser."""
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path("."),
        help="Agent's working directory (default: current directory)",
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

    try:
        config = load_config(project_dir, {
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

    results = run_verify(project_dir)

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
    harness_dir = project_dir / CONFIG_DIR_NAME

    config_file = harness_dir / "config.toml"
    if config_file.exists():
        print(f"Config already exists: {config_file}")
        print("Remove it first if you want to reinitialize.")
        sys.exit(1)

    harness_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir = harness_dir / "prompts"
    prompts_dir.mkdir(exist_ok=True)

    # Copy templates from package
    templates_dir = Path(__file__).parent / "templates"
    shutil.copy(templates_dir / "config.toml", config_file)
    shutil.copy(templates_dir / "spec.md", harness_dir / "spec.md")
    shutil.copy(templates_dir / "init.md", prompts_dir / "init.md")
    shutil.copy(templates_dir / "build.md", prompts_dir / "build.md")

    print(f"Created {harness_dir}/")
    print(f"  - config.toml (edit this to configure your project)")
    print(f"  - spec.md (describe what you're building)")
    print(f"  - prompts/init.md (initialization phase prompt)")
    print(f"  - prompts/build.md (building phase prompt)")
    print()
    print("Next steps:")
    print(f"  1. Edit {harness_dir / 'spec.md'} with your project specification")
    print(f"  2. Edit {config_file} to configure phases and tracking")
    print(f"  3. Run: python -m agent_harness verify --project-dir {project_dir}")
    print(f"  4. Run: python -m agent_harness run --project-dir {project_dir}")


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    {"run": cmd_run, "verify": cmd_verify, "init": cmd_init}[args.command](args)
