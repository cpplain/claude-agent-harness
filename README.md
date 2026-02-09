# Agent Harness

A generic, configurable harness for long-running autonomous coding agents. Built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk), it supports any project type (frontend, backend, CLI tools, data pipelines, etc.) when configured via a `.agent-harness/` directory.

## Overview

Agent Harness provides:

- **Configurable agent loop** with phase-based workflows (e.g., initializer + coding agent)
- **TOML-based configuration** — no code changes needed to customize behavior
- **Configurable security** — bash command allowlists, sandboxing, filesystem restrictions, automatic git validation
- **Progress tracking** — JSON checklist, notes file, or none with automatic completion detection
- **Error recovery** — exponential backoff and circuit breaker to prevent runaway costs
- **MCP server support** — browser automation, databases, etc. with optional tool restrictions
- **Session persistence** — auto-continue across sessions with state tracking
- **Setup verification** — check auth, tools, config before running

## Prerequisites

- Python 3.10+
- [Claude Code CLI](https://www.npmjs.com/package/@anthropic-ai/claude-code) (`npm install -g @anthropic-ai/claude-code`)
- Authentication — one of:
  - `ANTHROPIC_API_KEY` ([console.anthropic.com](https://console.anthropic.com/))
  - `CLAUDE_CODE_OAUTH_TOKEN` (via `claude setup-token`)

See [`.env.example`](.env.example) for all options.

### Using 1Password CLI

If you manage secrets with [1Password CLI](https://developer.1password.com/docs/cli), create a `.env` file with an `op://` reference:

```
ANTHROPIC_API_KEY="op://Vault/Item/api_key"
```

Then wrap any command with `op run`:

```bash
op run --env-file .env -- python -m agent_harness run --project-dir ./my-project
```

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd claude-agent-harness
```

**Using uv (recommended):**

```bash
uv sync
source .venv/bin/activate
```

**Using venv + pip:**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

**Using pip (existing environment):**

```bash
pip install -e .
```

## Quick Start

```bash
# 1. Create a new project configuration
python -m agent_harness init --project-dir ./my-project

# 2. Edit the configuration
#    -> ./my-project/.agent-harness/config.toml

# 3. Verify setup
python -m agent_harness verify --project-dir ./my-project

# 4. Run the agent
python -m agent_harness run --project-dir ./my-project
```

## CLI Reference

```
python -m agent_harness <command> [options]
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

## Safety Features

The harness includes multiple layers of safety for autonomous agent operation:

### Error Recovery & Circuit Breaker

- **Exponential backoff**: Automatically increases delay between retries (5s → 10s → 20s → 40s → 120s)
- **Circuit breaker**: Stops after 5 consecutive errors (configurable) to prevent runaway API costs
- **Error context forwarding**: Previous session errors are included in the next session's prompt to help recovery

```toml
[error_recovery]
max_consecutive_errors = 5
initial_backoff_seconds = 5.0
max_backoff_seconds = 120.0
backoff_multiplier = 2.0
```

### Completion Detection

The harness automatically stops when all work is complete:

- For `json_checklist` tracking: stops when all items have `passing_field` set to `true`
- Exit reason shown in final summary: `"ALL COMPLETE"`, `"MAX ITERATIONS"`, or `"TOO MANY ERRORS"`

### Git Safety

When `git` is in the allowed commands list, destructive operations are automatically blocked:

- ❌ Blocked: `git clean`, `git reset --hard`, `git checkout -- <path>`, `git push --force/-f`
- ✅ Allowed: `git status`, `git add`, `git commit`, `git diff`, `git log`, `git push`, etc.

No additional configuration needed — git validation happens automatically.

### OAuth Token Validation

The harness validates OAuth tokens before use, checking for:

- Embedded whitespace (spaces, newlines, carriage returns)
- Copy/paste corruption from clipboard
- Provides helpful error messages with debugging info

### MCP Tool Restrictions

Optional security restrictions for MCP tools:

```toml
[security.mcp]
tool_restrictions.puppeteer.blocked_patterns = [r"rm -rf", r"--force"]
tool_restrictions.puppeteer.allowed_args = ["status", "list"]
```

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

# Post-run instructions (shown in final summary)
post_run_instructions = [
    "npm install",
    "npm run dev",
]
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
python -m agent_harness run \
    --project-dir ./my-clone-output \
    --harness-dir examples/claude-ai-clone/.agent-harness
```

## Troubleshooting

### "Configuration file not found"

The harness expects a `.agent-harness/config.toml` file in your project directory. If you see this error:

1. Check that you're running from the correct directory
2. Use `python -m agent_harness init --project-dir ./my-project` to scaffold a new configuration
3. If using `--harness-dir`, verify the path points to a directory containing `config.toml`

### "Prompt file not found"

Check that all `file:` references in your config.toml point to files relative to the `.agent-harness/` directory. For example:

```toml
[[phases]]
system_prompt = "file:prompts/coding_prompt.md"  # Must exist at .agent-harness/prompts/coding_prompt.md
```

### "Command 'X' is not in the allowed commands list"

The agent tried to run a bash command that's not in your `security.bash.allowed_commands` list. To fix:

1. Add the command to your config.toml:
   ```toml
   [security.bash]
   allowed_commands = ["ls", "cat", "npm", "node", "your-command"]
   ```
2. If the command needs extra validation (like `chmod` or `git`), check that validators are configured correctly
3. For destructive operations, the harness blocks certain git commands by default (clean, reset --hard, etc.)

### "Neither ANTHROPIC_API_KEY nor CLAUDE_CODE_OAUTH_TOKEN is set"

You need authentication credentials to use the Claude API:

- **API Key**: Get one from [console.anthropic.com](https://console.anthropic.com/) and set `export ANTHROPIC_API_KEY="your-key"`
- **OAuth Token**: Run `claude setup-token` and the harness will use `CLAUDE_CODE_OAUTH_TOKEN` automatically
- See [`.env.example`](.env.example) for setting these via environment file

### Agent is hanging on the first session

The first session (initializer phase) can take 10-20+ minutes for complex projects because it:

- Reads the entire spec
- Plans the feature breakdown
- Creates initial project structure
- Sets up git repository
- May run initial installs (npm, pip, etc.)

This is expected behavior. Subsequent sessions (coding phase) are typically faster as they focus on individual features.

If a session truly hangs:

1. Check the `.agent-harness/session.json` file for error messages
2. Look for permission prompts or security blocks in the output
3. Verify your progress file format matches the configuration (e.g., `feature_list.json` with `"passes": false` fields)

## Running Tests

```bash
python -m unittest discover tests -v
```

## License

MIT License. See [LICENSE](LICENSE).
