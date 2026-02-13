# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agent Harness is a configurable harness for long-running autonomous coding agents built on the Claude Agent SDK. It enables multi-phase agent execution with SDK-native sandbox isolation, error recovery, progress tracking, and MCP server integration. Configuration is driven entirely by `.agent-harness/config.toml`.

## Commands

```bash
# Install globally
uv tool install .

# Run commands
agent-harness init --project-dir ./my-project
agent-harness verify --project-dir ./my-project
agent-harness run --project-dir ./my-project
```

For development without installing:

```bash
uv run python -m agent_harness <command> --project-dir ./my-project
```

For testing, this project uses `uv` for dependency management:

```bash
# Install dependencies
uv sync

# Run all tests
uv run python -m unittest discover tests -v

# Run a single test module
uv run python -m unittest tests.test_config -v

# Run a single test
uv run python -m unittest tests.test_config.TestConfigDefaults.test_default_model -v
```

No linter or formatter is configured. Tests use `unittest` from the standard library (no pytest).

## Architecture

The system runs an async loop that executes **phases** sequentially. Each phase creates a fresh Claude SDK session (no context carryover) with a configured prompt. Phases can be `run_once` (skipped after first completion) and have path-based conditions (`exists:`, `not_exists:`). Session state (completed phases) persists in `.agent-harness/session.json`.

### Module Dependency Flow

**cli.py** orchestrates three main modules:

- **config.py** — loads and validates configuration (foundational, no internal imports)
- **runner.py** — executes the agent loop (uses config.py, client_factory.py, tracking.py)
- **verify.py** — runs setup checks (uses config.py)

**client_factory.py** builds SDK clients using config.py settings and passes them to the Claude SDK.

**tracking.py** is standalone with no internal imports.

**cli.py** — Argument parsing for 3 subcommands: `run`, `verify`, `init`. Entry point via `agent-harness` CLI.

**config.py** — Loads `.agent-harness/config.toml` into dataclasses. Resolves `file:prompts/foo.md` references to file contents. Validates permission modes, tracking types, phase names, and file paths.

**runner.py** — Main async agent loop. Manages phase selection, session state persistence, error tracking with exponential backoff, and auto-continue between sessions. Calls `create_client()` for each session.

**client_factory.py** — Creates `ClaudeSDKClient` by passing sandbox settings and permission mode directly to the SDK. Generates minimal settings file with permission rules (allow/deny lists). Handles API key vs OAuth token auth.

**tracking.py** — Progress monitoring with 3 implementations: `JsonChecklistTracker` (JSON array with boolean `passes` field), `NotesFileTracker` (plain text), `NoneTracker`.

**verify.py** — Runs up to 10 setup checks (Python version, SDK installed, CLI available, auth, API connectivity, config exists, config valid, file references, MCP commands, directory permissions).

## Key Patterns

- **Dataclass-based config** — All configuration is modeled as nested dataclasses with defaults and validation functions in `config.py`.
- **Factory functions** — `create_client()` encapsulates SDK client construction with sandbox and permission configuration.
- **SDK-native security** — Security is enforced through the Claude SDK's built-in sandbox (process isolation, network restrictions) and declarative permission rules (allow/deny lists), not application-layer hooks.
- **`file:` resolution** — Prompt strings starting with `file:` are resolved relative to the `.agent-harness/` directory and replaced with file contents during config loading.
- **MCP environment variables** — MCP server `env` values support `${VAR}` syntax for environment variable expansion.

## Design Principles

**Understand Anthropic's Guidance First**: Before designing any feature, read and understand Anthropic's documentation. They have already solved most agent problems and documented both WHAT to do and WHY. Do not design solutions without first understanding their recommended approach.

Required reading:

- [Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Claude Code Sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)
- [Effective Harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)

## Dependencies

Single runtime dependency: `claude-agent-sdk>=0.1.0` (plus `tomli` backport for Python <3.11). The SDK provides `ClaudeSDKClient`, message/block types, and built-in tools.
