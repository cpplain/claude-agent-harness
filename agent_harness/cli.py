"""
CLI Interface
=============

Argument parsing and subcommand dispatch for the agent harness.
Run with: agent-harness <command> [options]
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from importlib.metadata import version as get_version
from pathlib import Path

from agent_harness.config import CONFIG_DIR_NAME, ConfigError, load_config
from agent_harness.info import (
    cmd_info_guide,
    cmd_info_preset,
    cmd_info_schema,
    cmd_info_template,
)
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
        prog="agent-harness",
        description="Generic harness for long-running autonomous coding agents",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {get_version('agent-harness')}",
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

    # info subcommand
    info_parser = subparsers.add_parser("info", help="Get templates, schema, and documentation")
    info_subparsers = info_parser.add_subparsers(dest="info_command", help="Info topics")

    # info template
    template_parser = info_subparsers.add_parser("template", help="Get template files")
    template_parser.add_argument("--name", help="Template name (e.g. config.toml)")
    template_parser.add_argument("--list", action="store_true", help="List all templates")
    template_parser.add_argument("--all", action="store_true", help="Get all templates with content")
    template_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # info schema
    schema_parser = info_subparsers.add_parser("schema", help="Get configuration schema")
    schema_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # info preset
    preset_parser = info_subparsers.add_parser("preset", help="Get preset configurations")
    preset_parser.add_argument("--name", help="Preset name (e.g. python)")
    preset_parser.add_argument("--list", action="store_true", help="List all presets")
    preset_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # info guide
    guide_parser = info_subparsers.add_parser("guide", help="Get setup guide")
    guide_parser.add_argument("--json", action="store_true", help="Output as JSON")

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
    print(f"  3. Run: agent-harness verify --project-dir {project_dir}")
    print(f"  4. Run: agent-harness run --project-dir {project_dir}")


def cmd_info(args: argparse.Namespace) -> None:
    """Execute the info subcommand."""
    if not args.info_command:
        print("Error: info subcommand required")
        print("Usage: agent-harness info {template|schema|preset|guide} [options]")
        sys.exit(1)

    if args.info_command == "template":
        cmd_info_template(
            name=getattr(args, "name", None),
            list_templates_flag=getattr(args, "list", False),
            all_templates_flag=getattr(args, "all", False),
            json_output=getattr(args, "json", False),
        )
    elif args.info_command == "schema":
        cmd_info_schema(json_output=getattr(args, "json", False))
    elif args.info_command == "preset":
        cmd_info_preset(
            name=getattr(args, "name", None),
            list_presets_flag=getattr(args, "list", False),
            json_output=getattr(args, "json", False),
        )
    elif args.info_command == "guide":
        cmd_info_guide(json_output=getattr(args, "json", False))


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    {"run": cmd_run, "verify": cmd_verify, "init": cmd_init, "info": cmd_info}[args.command](args)
