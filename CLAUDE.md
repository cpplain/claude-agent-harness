# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agent Harness is a configurable harness for long-running autonomous coding agents built on the Claude Agent SDK. It enables multi-phase agent execution with security hooks, error recovery, progress tracking, and MCP server integration. Configuration is driven entirely by `.agent-harness/config.toml`.

## Commands

This project uses `uv` for dependency management. All `python` commands should be run via `uv run`.

```bash
# Install dependencies
uv sync

# Run all tests
uv run python -m unittest discover tests -v

# Run a single test module
uv run python -m unittest tests.test_security -v

# Run a single test
uv run python -m unittest tests.test_security.TestSecurity.test_extract_commands -v

# Run the agent
uv run python -m agent_harness run --project-dir ./my-project
uv run python -m agent_harness verify --project-dir ./my-project
uv run python -m agent_harness init --project-dir ./my-project
```

No linter or formatter is configured. Tests use `unittest` from the standard library (no pytest).

## Architecture

The system runs an async loop that executes **phases** sequentially. Each phase creates a fresh Claude SDK session (no context carryover) with a configured prompt. Phases can be `run_once` (skipped after first completion) and have path-based conditions (`exists:`, `not_exists:`). Session state (completed phases, error context) persists in `.agent-harness/session.json`.

### Module Dependency Flow

```
cli.py → config.py → runner.py → client_factory.py → Claude SDK
                         ↓               ↓
                    tracking.py     security.py
                    prompts.py
                    display.py
```

**cli.py** — Argument parsing for 3 subcommands: `run`, `verify`, `init`. Entry point via `python -m agent_harness`.

**config.py** — Loads `.agent-harness/config.toml` into dataclasses. Resolves `file:prompts/foo.md` references to file contents. Validates permission modes, tracking types, phase names, and file paths.

**runner.py** — Main async agent loop. Manages phase selection, session state persistence, error tracking with exponential backoff, and auto-continue between sessions. Calls `create_client()` for each session.

**client_factory.py** — Creates `ClaudeSDKClient` with permission rules, settings files, pre-tool-use security hooks, and MCP server configuration. Handles API key vs OAuth token auth.

**security.py** — Bash command validation via pre-tool-use hooks. Parses shell command strings (`extract_commands`, `split_command_segments`, `strip_balanced_parens`), validates against allowlists, and has special validators for `pkill`, `chmod`, `init.sh`, and `git` (blocks destructive operations like `push --force`, `reset --hard`).

**tracking.py** — Progress monitoring with 3 implementations: `JsonChecklistTracker` (JSON array with boolean `passes` field), `NotesFileTracker` (plain text), `NoneTracker`. Created via `create_tracker()` factory.

**verify.py** — Runs 11 setup checks (Python version, SDK installed, CLI available, auth, API connectivity, config validity, MCP commands, directory permissions).

## Key Patterns

- **Dataclass-based config** — All configuration is modeled as nested dataclasses with defaults and validation functions in `config.py`.
- **Factory functions** — `create_tracker()`, `create_client()`, `create_bash_security_hook()` encapsulate complex construction.
- **Hook system** — Security validation runs as pre-tool-use hooks registered with the Claude SDK client. `create_bash_security_hook()` returns an async hook function that intercepts Bash tool calls.
- **`file:` resolution** — Prompt strings starting with `file:` are resolved relative to the `.agent-harness/` directory and replaced with file contents during config loading.
- **MCP environment variables** — MCP server `env` values support `${VAR}` syntax for environment variable expansion.

## Dependencies

Single runtime dependency: `claude-agent-sdk>=0.1.0` (plus `tomli` backport for Python <3.11). The SDK provides `ClaudeSDKClient`, message/block types, hook matchers, and built-in tools.
