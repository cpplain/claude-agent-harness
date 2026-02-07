# Agent Harness

A generic, configurable harness for long-running autonomous coding agents. Built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk), it supports any project type (frontend, backend, CLI tools, data pipelines, etc.) when configured via a `.agent-harness/` directory.

## Overview

Agent Harness provides:

- **Configurable agent loop** with phase-based workflows (e.g., initializer + coding agent)
- **TOML-based configuration** — no code changes needed to customize behavior
- **Configurable security** — bash command allowlists, sandboxing, filesystem restrictions
- **Progress tracking** — JSON checklist, notes file, or none
- **MCP server support** — browser automation, databases, etc.
- **Session persistence** — auto-continue across sessions with state tracking
- **Setup verification** — check auth, tools, config before running

## Prerequisites

- Python 3.10+
- [Claude Code CLI](https://www.npmjs.com/package/@anthropic-ai/claude-code) (`npm install -g @anthropic-ai/claude-code`)
- Authentication: `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` environment variable

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd claude-agent-harness

# Install with uv (recommended)
uv sync
```

Or with pip:

```bash
pip install -e .
```

## Quick Start

```bash
# 1. Create a new project configuration
uv run python -m agent_harness init --project-dir ./my-project

# 2. Edit the configuration
#    -> ./my-project/.agent-harness/config.toml

# 3. Verify setup
uv run python -m agent_harness verify --project-dir ./my-project

# 4. Run the agent
uv run python -m agent_harness run --project-dir ./my-project
```

## CLI Reference

```
uv run python -m agent_harness <command> [options]
```

### Commands

| Command  | Description                                    |
| -------- | ---------------------------------------------- |
| `run`    | Run the agent loop                             |
| `verify` | Check setup (auth, config, tools)              |
| `init`   | Scaffold `.agent-harness/` with starter config |

### Global Flags

| Flag            | Description                         | Default                       |
| --------------- | ----------------------------------- | ----------------------------- |
| `--project-dir` | Agent's working directory           | `.`                           |
| `--harness-dir` | Path to `.agent-harness/` directory | `project-dir/.agent-harness/` |

### Run Flags

| Flag               | Description             | Default     |
| ------------------ | ----------------------- | ----------- |
| `--max-iterations` | Override max iterations | From config |
| `--model`          | Override model          | From config |

## Configuration

Configuration lives in `.agent-harness/config.toml`. See the [example config](examples/claude-ai-clone/.agent-harness/config.toml) for a complete reference.

### Directory Layout

```
project_dir/
  .agent-harness/
    config.toml            # Main configuration (required)
    session.json           # Session number, completed phases (auto-created)
    .claude_settings.json  # Generated security settings (auto-created, gitignored)
    prompts/               # Prompt files (referenced by config)
    logs/                  # Session logs (auto-created, gitignored)
```

### Key Configuration Sections

```toml
# Agent model and system prompt
model = "claude-sonnet-4-5-20250929"
system_prompt = "file:prompts/system.md"

# Session settings
max_turns = 1000
auto_continue_delay = 3

# Tools and MCP servers
[tools]
builtin = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]

[tools.mcp_servers.puppeteer]
command = "npx"
args = ["puppeteer-mcp-server"]

# Security
[security]
permission_mode = "acceptEdits"

[security.bash]
allowed_commands = ["ls", "cat", "npm", "node", "git"]

# Progress tracking
[tracking]
type = "json_checklist"
file = "feature_list.json"

# Multi-phase workflows
[[phases]]
name = "initializer"
prompt = "file:prompts/initializer.md"
run_once = true
condition = "not_exists:.agent-harness/feature_list.json"

[[phases]]
name = "coding"
prompt = "file:prompts/coding.md"
```

### Config Loading Precedence

CLI flags > config.toml values > defaults

### Defaults

| Setting                    | Default Value                           |
| -------------------------- | --------------------------------------- |
| `model`                    | `claude-sonnet-4-5-20250929`            |
| `max_turns`                | `1000`                                  |
| `auto_continue_delay`      | `3`                                     |
| `tools.builtin`            | `[Read, Write, Edit, Glob, Grep, Bash]` |
| `security.permission_mode` | `acceptEdits`                           |
| `security.sandbox.enabled` | `true`                                  |
| `tracking.type`            | `none`                                  |

## Project Structure

```
agent_harness/          # Python package
  __init__.py
  __main__.py           # Entry point
  cli.py                # Argument parsing, subcommands
  config.py             # Config loading, validation, HarnessConfig
  runner.py             # Generic agent loop
  client_factory.py     # Builds ClaudeSDKClient from config
  security.py           # Configurable bash security hooks
  tracking.py           # Progress tracking implementations
  prompts.py            # Prompt loading with file: resolution
  verify.py             # Setup verification checks
  display.py            # Console output formatting
tests/
  test_config.py
  test_security.py
  test_tracking.py
  test_prompts.py
  test_verify.py
  test_runner.py
  test_client_factory.py
examples/
  claude-ai-clone/      # Complete example configuration
```

## Examples

See [`examples/claude-ai-clone/`](examples/claude-ai-clone/) for a complete example that recreates the original autonomous coding demo using the generic harness configuration.

```bash
# Run the Claude.ai clone example
uv run python -m agent_harness run \
    --project-dir ./my-clone-output \
    --harness-dir examples/claude-ai-clone/.agent-harness
```

## Running Tests

```bash
uv run python -m unittest discover tests -v
```

## License

MIT License. See [LICENSE](LICENSE).
