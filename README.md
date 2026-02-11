# Agent Harness

A generic, configurable harness for long-running autonomous coding agents. Built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk), it implements [Anthropic's guide for effective agent harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), featuring phase-driven execution, configurable MCP tools, and multi-layered security.

This project originated from the [autonomous-coding example](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding) in the claude-quickstarts repository and extends it into a fully configurable, project-agnostic harness.

## What This Is

This is a **project-agnostic harness** that can drive any kind of autonomous coding task:

- **Web applications** (Next.js, React, Vue, etc.)
- **Backend services** (Node, Python, Ruby, Go, etc.)
- **Test refactoring** (RSpec, Jest, Pytest, etc.)
- **Data pipelines** and ETL workflows
- **CLI tools** and automation scripts
- **Any other coding task** requiring multiple iterations

The harness is **completely generic** — all project-specific configuration (tech stack, tools, prompts) is declared in a `.agent-harness/config.toml` file. No hardcoded assumptions about your stack.

## Overview

Agent Harness provides:

- **Phase-based workflows** — declarative phase definitions with conditions and run-once semantics
- **TOML-based configuration** — no code changes needed to customize behavior
- **Multi-layered security** — OS sandbox, filesystem restrictions, command allowlists, automatic git validation
- **Progress tracking** — JSON checklist, notes file, or none with automatic completion detection
- **Error recovery** — exponential backoff and circuit breaker to prevent runaway costs
- **MCP server support** — browser automation, databases, etc. with optional tool restrictions
- **Session persistence** — auto-continue across sessions with state tracking
- **Setup verification** — check auth, tools, config before running

## Getting Started

### 1. Clone and install

```bash
git clone <repo-url>
cd claude-agent-harness
uv sync
```

<details>
<summary>Alternative: using pip</summary>

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

If using pip, replace `uv run` with `python` in all commands below.

</details>

### 2. Set up authentication

Export one of these environment variables:

- `ANTHROPIC_API_KEY` — get one from [console.anthropic.com](https://console.anthropic.com/)
- `CLAUDE_CODE_OAUTH_TOKEN` — via `claude setup-token`

See [`.env.example`](.env.example) for all options.

<details>
<summary>Using 1Password CLI</summary>

If you manage secrets with [1Password CLI](https://developer.1password.com/docs/cli), create a `.env` file with an `op://` reference:

```
ANTHROPIC_API_KEY="op://Vault/Item/api_key"
```

Then wrap any command with `op run`:

```bash
op run --env-file "./.env" -- uv run python -m agent_harness run --project-dir ./my-project
```

</details>

### 3. Run

```bash
# Scaffold a new project configuration
uv run python -m agent_harness init --project-dir ./my-project

# Edit the configuration
#    -> ./my-project/.agent-harness/config.toml

# Verify setup
uv run python -m agent_harness verify --project-dir ./my-project

# Run the agent
uv run python -m agent_harness run --project-dir ./my-project
```

## CLI Reference

```bash
# Run the agent
python -m agent_harness run --project-dir <path> [options]

# Verify setup (auth, dependencies, config)
python -m agent_harness verify [--project-dir <path>]

# Scaffold new project configuration
python -m agent_harness init --project-dir <path>

# Global flags (all commands)
--project-dir PATH      # Agent's working directory (default: .)
--harness-dir PATH      # Path to .agent-harness/ (default: project-dir/.agent-harness/)

# Run command options
--max-iterations N      # Override max iterations (default: from config)
--model MODEL           # Override model (default: from config)
```

## How It Works

### Phase-Driven Execution

The harness executes agents in configurable phases with conditions and run-once semantics:

1. **Initializer Phase** (run_once: true):
   - Reads the specification
   - Creates a feature list with test cases
   - Sets up project structure
   - Initializes git repository

2. **Coding Phase** (repeating):
   - Picks up where previous session left off
   - Implements features one by one
   - Marks features as complete in progress file
   - Creates git commits for changes

### Session Management

- **Fresh context per session**: Each session creates a new context window to prevent context pollution
- **Progress persistence**: State preserved between sessions via:
  - Tracking file (e.g., `feature_list.json`) tracking feature completion
  - Session state file (`session.json`) tracking completed phases
  - Git commits preserving code changes
- **Auto-continue**: Sessions auto-resume after configured delay (default 3s)
- **Completion detection**: Harness stops automatically when `tracker.is_complete()` returns `true` (all features passing)
- Press `Ctrl+C` to pause; run same command to resume

### Error Recovery & Circuit Breaker

Prevents runaway API costs when sessions fail repeatedly:

- Tracks consecutive errors across sessions
- **Exponential backoff**: 5s → 10s → 20s → 40s → 120s (capped)
- **Circuit breaker**: Trips after 5 consecutive errors (configurable)
- Successful session resets error counter
- Error context forwarded to next session to help recovery

```toml
[error_recovery]
max_consecutive_errors = 5
initial_backoff_seconds = 5.0
max_backoff_seconds = 120.0
backoff_multiplier = 2.0
```

## Security Model

This harness uses a defense-in-depth security approach with multiple layers:

### 1. OS-Level Sandbox

Bash commands run in an isolated environment that prevents filesystem escape.

### 2. Filesystem Restrictions

File operations are restricted to `allowed_paths` (default: `./**` — the project directory only).

### 3. Command Allowlist

Bash commands are validated against an allowlist before execution. The harness provides base commands for common operations, and projects add their own:

```toml
[security.bash]
allowed_commands = ["npm", "node", "ruby", "bundle", "init.sh"]
```

### 4. Git Safety (Automatic)

When `git` is in the allowed commands list, destructive operations are automatically blocked:

- **Blocked**: `git clean`, `git reset --hard`, `git checkout -- <path>`, `git restore`, `git push --force/-f`
- **Allowed**: `git status`, `git add`, `git commit`, `git diff`, `git log`, `git push`, etc.

No additional configuration needed — git validation happens automatically.

### 5. Special Command Validation

Certain commands have additional validation logic:

- **`pkill`**: Only allows killing configured dev processes (node, npm, vite, next)
- **`chmod`**: Only allows `+x` mode (making files executable)
- **`init.sh`**: Only allows `./init.sh` execution

### 6. MCP Tool Restrictions

Optional regex-based patterns and action allowlists for MCP tools:

```toml
[security.mcp]
tool_restrictions.puppeteer.blocked_patterns = [r"rm -rf", r"--force"]
tool_restrictions.puppeteer.allowed_args = ["navigate", "screenshot"]
```

### OAuth Token Validation

The harness validates OAuth tokens before use, checking for:

- Embedded whitespace (spaces, newlines, carriage returns)
- Copy/paste corruption from clipboard
- Provides helpful error messages with debugging info

## Configuration

Configuration lives in `.agent-harness/config.toml`. See the [example config](examples/claude-ai-clone/.agent-harness/config.toml) for a complete reference.

### Directory Layout

```
project_dir/
├── .agent-harness/
│   ├── logs/                  # Session logs (auto-created, gitignored)
│   ├── prompts/               # Prompt files (referenced by config)
│   │   ├── app_spec.txt
│   │   ├── coding.md
│   │   └── initializer.md
│   ├── .claude_settings.json  # Generated security settings (auto-created, gitignored)
│   ├── config.toml            # Main configuration (required)
│   └── session.json           # Session number, completed phases (auto-created)
└── (generated code lives here)
```

### Full Configuration Reference

Complete annotated example showing all available configuration options:

```toml
# --- Agent Settings ---
# Model to use for agent execution
model = "claude-sonnet-4-5-20250929"

# System prompt (can use "file:prompts/system.md" to load from file)
system_prompt = "You are an expert full-stack developer..."

# --- Session Settings ---
# Maximum API turns per session before auto-continuing
max_turns = 1000

# Maximum total sessions before stopping (default: unlimited)
max_iterations = 10

# Delay in seconds before auto-continuing to next session
auto_continue_delay = 3

# --- Tools ---
[tools]
# Built-in Claude SDK tools to enable
builtin = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]

# MCP servers to connect
[tools.mcp_servers.puppeteer]
command = "npx"
args = ["puppeteer-mcp-server"]
env = { NODE_ENV = "production" }

# --- Security ---
[security]
# Permission mode: "acceptEdits", "bypassPermissions", "plan"
permission_mode = "acceptEdits"

# Filesystem paths the agent can access (globs supported)
allowed_paths = ["./**"]

# OS-level sandbox configuration
[security.sandbox]
enabled = true
auto_allow_bash_if_sandboxed = true

# Bash command security
[security.bash]
allowed_commands = ["ls", "cat", "npm", "node", "git", "pkill", "chmod"]

# Extra validators for specific commands
[security.bash.extra_validators.pkill]
allowed_targets = ["node", "npm", "vite", "next"]

[security.bash.extra_validators.chmod]
allowed_modes = ["+x", "u+x", "a+x"]

# MCP tool restrictions (optional)
[security.mcp]
[security.mcp.tool_restrictions.puppeteer_navigate]
blocked_patterns = [".*admin.*", ".*internal.*"]
allowed_args = ["url"]

# --- Progress Tracking ---
[tracking]
# Tracker type: "json_checklist", "notes_file", "none"
type = "json_checklist"

# Tracking file path (relative to harness_dir)
file = "feature_list.json"

# Field name indicating completion (for json_checklist)
passing_field = "passes"

# --- Error Recovery ---
[error_recovery]
# Circuit breaker: max consecutive session errors before stopping
max_consecutive_errors = 5

# Initial backoff delay after first error
initial_backoff_seconds = 5.0

# Maximum backoff delay (capped exponential backoff)
max_backoff_seconds = 120.0

# Multiplier for exponential backoff
backoff_multiplier = 2.0

# --- Phases ---
# Multi-phase workflow definitions
[[phases]]
name = "initializer"
prompt = "file:prompts/initializer.md"
run_once = true
condition = "not_exists:.agent-harness/feature_list.json"

[[phases]]
name = "coding"
prompt = "file:prompts/coding.md"

# --- Init Files ---
# Files to copy on first run
[[init_files]]
source = "prompts/app_spec.txt"
dest = "app_spec.txt"

# --- Post-Run Instructions ---
# Commands to display after agent completes
post_run_instructions = [
    "npm install",
    "npm run dev",
    "Open http://localhost:3000",
]
```

### Configuration Fields

#### Top-Level Settings

| Field                   | Type     | Default                                 | Description                                                   |
| ----------------------- | -------- | --------------------------------------- | ------------------------------------------------------------- |
| `model`                 | string   | `"claude-sonnet-4-5-20250929"`          | Claude model to use for agent execution                       |
| `system_prompt`         | string   | `"You are a helpful coding assistant."` | System prompt (supports `file:` references)                   |
| `max_turns`             | int      | `1000`                                  | Maximum API turns per session before auto-continuing          |
| `max_iterations`        | int?     | `null`                                  | Maximum total sessions before stopping (unlimited if not set) |
| `auto_continue_delay`   | int      | `3`                                     | Delay in seconds before auto-continuing to next session       |
| `post_run_instructions` | string[] | `[]`                                    | Commands to display in final summary banner                   |

#### `[tools]` Section

| Field     | Type     | Default                                             | Description                         |
| --------- | -------- | --------------------------------------------------- | ----------------------------------- |
| `builtin` | string[] | `["Read", "Write", "Edit", "Glob", "Grep", "Bash"]` | Built-in Claude SDK tools to enable |

**MCP Servers** (`[tools.mcp_servers.<name>]`):

| Field     | Type     | Default | Description                                         |
| --------- | -------- | ------- | --------------------------------------------------- |
| `command` | string   | `""`    | Command to execute MCP server                       |
| `args`    | string[] | `[]`    | Command-line arguments                              |
| `env`     | map      | `{}`    | Environment variables (supports `${VAR}` expansion) |

#### `[security]` Section

| Field             | Type     | Default         | Description                                                          |
| ----------------- | -------- | --------------- | -------------------------------------------------------------------- |
| `permission_mode` | string   | `"acceptEdits"` | Permission mode: `"acceptEdits"`, `"bypassPermissions"`, or `"plan"` |
| `allowed_paths`   | string[] | `["./**"]`      | Filesystem paths the agent can access (glob patterns supported)      |

**Sandbox** (`[security.sandbox]`):

| Field                          | Type | Default | Description                                          |
| ------------------------------ | ---- | ------- | ---------------------------------------------------- |
| `enabled`                      | bool | `true`  | Enable OS-level sandbox for Bash commands            |
| `auto_allow_bash_if_sandboxed` | bool | `true`  | Auto-allow all Bash commands when sandbox is enabled |

**Bash Security** (`[security.bash]`):

| Field              | Type     | Default | Description                                                    |
| ------------------ | -------- | ------- | -------------------------------------------------------------- |
| `allowed_commands` | string[] | `[]`    | Bash commands the agent can execute (when sandbox is disabled) |

**Bash Extra Validators** (`[security.bash.extra_validators.<command>]`):

| Field             | Type     | Default | Description                               |
| ----------------- | -------- | ------- | ----------------------------------------- |
| `allowed_targets` | string[] | `[]`    | Allowed targets for commands like `pkill` |
| `allowed_modes`   | string[] | `[]`    | Allowed modes for commands like `chmod`   |

**MCP Security** (`[security.mcp]`):

Defined as `[security.mcp.tool_restrictions.<tool_name>]`:

| Field              | Type     | Default | Description                                   |
| ------------------ | -------- | ------- | --------------------------------------------- |
| `blocked_patterns` | string[] | `[]`    | Regex patterns to block in tool arguments     |
| `allowed_args`     | string[] | `[]`    | Allowed argument names (all allowed if empty) |

#### `[tracking]` Section

| Field           | Type   | Default    | Description                                                                          |
| --------------- | ------ | ---------- | ------------------------------------------------------------------------------------ |
| `type`          | string | `"none"`   | Tracker type: `"json_checklist"`, `"notes_file"`, or `"none"`                        |
| `file`          | string | `""`       | Tracking file path (relative to harness_dir, required for json_checklist/notes_file) |
| `passing_field` | string | `"passes"` | JSON field indicating completion (for json_checklist)                                |

#### `[error_recovery]` Section

| Field                     | Type  | Default | Description                                                     |
| ------------------------- | ----- | ------- | --------------------------------------------------------------- |
| `max_consecutive_errors`  | int   | `5`     | Circuit breaker: max consecutive session errors before stopping |
| `initial_backoff_seconds` | float | `5.0`   | Initial backoff delay after first error                         |
| `max_backoff_seconds`     | float | `120.0` | Maximum backoff delay (capped exponential backoff)              |
| `backoff_multiplier`      | float | `2.0`   | Multiplier for exponential backoff                              |

#### `[[phases]]` Section

Multiple phases can be defined using `[[phases]]` array syntax:

| Field       | Type   | Default    | Description                                                 |
| ----------- | ------ | ---------- | ----------------------------------------------------------- |
| `name`      | string | _required_ | Phase name (for logging/debugging)                          |
| `prompt`    | string | _required_ | Phase prompt (supports `file:` references)                  |
| `run_once`  | bool   | `false`    | Only execute this phase once across all sessions            |
| `condition` | string | `""`       | Condition for running phase (e.g., `"not_exists:file.txt"`) |

#### `[[init_files]]` Section

Multiple init files can be defined using `[[init_files]]` array syntax:

| Field    | Type   | Default    | Description                                     |
| -------- | ------ | ---------- | ----------------------------------------------- |
| `source` | string | _required_ | Source file path (relative to harness_dir)      |
| `dest`   | string | _required_ | Destination file path (relative to harness_dir) |

### Config Loading Precedence

CLI flags > config.toml values > defaults

## Project Structure

```
claude-agent-harness/
├── agent_harness/          # Python package
│   ├── __init__.py
│   ├── __main__.py         # Entry point
│   ├── cli.py              # Argument parsing, subcommands
│   ├── client_factory.py   # Builds ClaudeSDKClient from config
│   ├── config.py           # Config loading, validation, HarnessConfig
│   ├── display.py          # Console output formatting
│   ├── prompts.py          # Prompt loading with file: resolution
│   ├── runner.py           # Generic agent loop
│   ├── security.py         # Configurable bash security hooks
│   ├── tracking.py         # Progress tracking implementations
│   └── verify.py           # Setup verification checks
├── examples/
│   └── claude-ai-clone/
│       ├── .agent-harness/
│       │   ├── prompts/
│       │   │   ├── app_spec.txt
│       │   │   ├── coding.md
│       │   │   └── initializer.md
│       │   └── config.toml
│       └── README.md
├── tests/
│   ├── test_client_factory.py
│   ├── test_config.py
│   ├── test_prompts.py
│   ├── test_runner.py
│   ├── test_security.py
│   ├── test_tracking.py
│   └── test_verify.py
├── .env.example
└── pyproject.toml
```

## Examples

### Claude.ai Clone (Next.js)

See [`examples/claude-ai-clone/`](examples/claude-ai-clone/) for a complete example that:

- Uses Next.js/React stack (npm, node commands)
- Integrates Puppeteer MCP server for browser testing
- Generates a production-quality chat interface
- Tracks progress via feature_list.json

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
prompt = "file:prompts/coding_prompt.md"  # Must exist at .agent-harness/prompts/coding_prompt.md
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

## Design Principles

1. **Zero assumptions about tech stack**: The harness has no hardcoded knowledge of npm, Ruby, Python, or any other stack. Projects declare exactly what they need.

2. **Zero wasted context**: Only tools and servers declared in the config are available to the agent. No unused MCP servers polluting the context.

3. **Defense in depth**: Multiple security layers (sandbox, permissions, allowlists, validation) protect against unintended actions.

4. **Session persistence**: Progress is saved between sessions via the progress file and git commits, enabling long-running tasks that span hours or days.

5. **Fresh context per session**: Each session starts with a clean context window, preventing context pollution and allowing unlimited total work.

6. **SDK-first**: Delegate to the Claude Agent SDK for security enforcement, sandboxing, permission evaluation, and tool management. Only add custom code for domain-specific validation and orchestration.

## Running Tests

```bash
# Run all tests
python -m unittest discover tests -v

# Run specific test modules
python -m unittest tests.test_security -v       # Security validation
python -m unittest tests.test_config -v         # Configuration loading
python -m unittest tests.test_tracking -v       # Progress tracking
python -m unittest tests.test_runner -v         # Session loop logic
python -m unittest tests.test_client_factory -v # Client creation
```

Test coverage includes:

- **Security validation**: Command allowlist, chmod/pkill/init.sh validation, git destructive operation blocking (26 test cases), parenthesis handling
- **Configuration loading**: TOML parsing, defaults, validation, error cases
- **Progress tracking**: Completion detection, JSON parsing, print formatting
- **Prompt loading**: File reading, `file:` resolution, error handling

## License

MIT License. See [LICENSE](LICENSE).

This harness is based on the patterns described in Anthropic's [guide for long-running agent harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents). The project originated from the [autonomous-coding example](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding) in the claude-quickstarts repository and is built using the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk).
