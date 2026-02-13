# Agent Harness

A generic, configurable harness for long-running autonomous coding agents. Built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk), it implements [Anthropic's guide for effective agent harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), featuring phase-driven execution, configurable MCP tools, and SDK-native sandbox isolation.

## Features

Agent Harness provides:

- **Phase-based workflows** — declarative phase definitions with conditions and run-once semantics
- **TOML-based configuration** — no code changes needed to customize behavior
- **SDK-native security** — OS sandbox with network isolation, declarative permission rules (allow/deny), secure defaults
- **Progress tracking** — JSON checklist, notes file, or none with automatic completion detection
- **Error recovery** — exponential backoff and circuit breaker to prevent runaway costs
- **MCP server support** — browser automation, databases, etc.
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
<summary>Alternative using pip</summary>

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
uv run python -m agent_harness run --project-dir <path> [options]

# Verify setup (auth, dependencies, config)
uv run python -m agent_harness verify [--project-dir <path>]

# Scaffold new project configuration
uv run python -m agent_harness init --project-dir <path>

# Global flags (all commands)
--project-dir PATH      # Agent's working directory (default: .)
--harness-dir PATH      # Path to .agent-harness/ (default: project-dir/.agent-harness/)

# Run command options
--max-iterations N      # Override max iterations (default: from config)
--model MODEL           # Override model (default: from config)
```

## How It Works

The harness executes agents in configurable **phases** with conditions and run-once semantics. Each phase gets a fresh Claude SDK session (no context carryover) with a configured prompt.

**Phase execution:**

- Phases run sequentially based on conditions (`exists:`, `not_exists:` path checks)
- `run_once: true` phases skip after first successful completion
- State persists in `.agent-harness/session.json`

**Session management:**

- Fresh context per session prevents context pollution
- Progress preserved via tracking file (e.g., `feature_list.json`), session state, and git commits
- Auto-continue after configured delay (default 3s)
- Completion detection: Harness stops when `tracker.is_complete()` returns `true` (only `json_checklist` supports this; `notes_file` and `none` require manual stop via Ctrl+C)
- Press Ctrl+C to pause; run same command to resume

**Error recovery:**

Prevents runaway API costs when sessions fail repeatedly:

- Tracks consecutive errors across sessions
- **Exponential backoff**: 5s → 10s → 20s → 40s → 80s (circuit breaker trips; max cap 120s)
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

This harness follows [Anthropic's secure deployment recommendations](https://platform.claude.com/docs/en/agent-sdk/secure-deployment) by relying on the SDK's built-in sandbox and permission system as the primary defense, rather than custom application-layer validation.

### SDK-Native Sandbox

The Claude SDK provides process-level isolation with:

- **Process isolation** — Bash commands run in a sandboxed subprocess
- **Network restrictions** — Configurable domain allowlist and Unix socket access
- **Filesystem boundaries** — Commands are restricted to the project directory

```toml
[security.sandbox]
enabled = true
auto_allow_bash_if_sandboxed = true
allow_unsandboxed_commands = false  # secure default

[security.sandbox.network]
# Example allowed domains (configure for your project needs)
allowed_domains = ["registry.npmjs.org", "github.com"]
allow_local_binding = false
allow_unix_sockets = []
```

### Declarative Permission Rules

Security is enforced through SDK permission rules, not runtime command parsing:

```toml
[security.permissions]
allow = [
    "Bash(npm *)", "Bash(node *)", "Bash(git *)",
    "Bash(ls *)", "Bash(cat *)", "Bash(grep *)",
    "Read(./**)", "Write(./**)", "Edit(./**)",
]
deny = [
    "Bash(curl *)", "Bash(wget *)",
    "Read(./.env)", "Read(./.env.*)",
]
```

Permission rules are evaluated by the SDK before tool execution. The agent cannot bypass these rules through prompt injection or indirect command execution.

### Secure Defaults

- `allow_unsandboxed_commands` defaults to `false`
- When sandbox is enabled, `auto_allow_bash_if_sandboxed=true` auto-allows Bash commands
- When sandbox is disabled, explicit `permissions.allow` rules are required
- Network access is denied by default

### Git Protection Recommendations

For production deployments, protect critical branches using **server-side git hooks or branch protection rules** on your git hosting platform (GitHub, GitLab, Bitbucket), not client-side validation. This prevents destructive operations like `git push --force` at the source.

## Configuration

Configuration lives in `.agent-harness/config.toml`.

### Directory Layout

```
project_dir/
├── .agent-harness/
│   ├── logs/                  # Session logs (auto-created, gitignored)
│   ├── prompts/               # Prompt files (referenced by config)
│   │   ├── app_spec.txt
│   │   ├── coding.md
│   │   └── initializer.md
│   ├── config.toml            # Main configuration (required)
│   └── session.json           # Session number, completed phases (auto-created)
└── (generated code lives here)
```

### Configuration Reference

For a complete, annotated configuration reference with detailed comments on all available options, see:

- **[`agent_harness/templates/config.toml`](agent_harness/templates/config.toml)** - Template with full documentation
- **[`examples/claude-ai-clone/.agent-harness/config.toml`](examples/claude-ai-clone/.agent-harness/config.toml)** - Real-world example

The `init` command creates a new config using the template:

```bash
uv run python -m agent_harness init --project-dir ./my-project
```

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
│   ├── runner.py           # Generic agent loop
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
│   ├── test_cli.py
│   ├── test_client_factory.py
│   ├── test_config.py
│   ├── test_prompts.py
│   ├── test_runner.py
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
uv run python -m agent_harness run \
    --project-dir ./my-clone-output \
    --harness-dir examples/claude-ai-clone/.agent-harness
```

## Troubleshooting

### "Configuration file not found"

The harness expects a `.agent-harness/config.toml` file in your project directory. If you see this error:

1. Check that you're running from the correct directory
2. Use `uv run python -m agent_harness init --project-dir ./my-project` to scaffold a new configuration
3. If using `--harness-dir`, verify the path points to a directory containing `config.toml`

### "Prompt file not found"

Check that all `file:` references in your config.toml point to files relative to the `.agent-harness/` directory:

```toml
[[phases]]
prompt = "file:prompts/coding_prompt.md"  # Must exist at .agent-harness/prompts/coding_prompt.md
```

### "Neither ANTHROPIC_API_KEY nor CLAUDE_CODE_OAUTH_TOKEN is set"

You need authentication credentials to use the Claude API:

- **API Key**: Get one from [console.anthropic.com](https://console.anthropic.com/) and set `export ANTHROPIC_API_KEY="your-key"`
- **OAuth Token**: Run `claude setup-token` and the harness will use `CLAUDE_CODE_OAUTH_TOKEN` automatically
- See [`.env.example`](.env.example) for setting these via environment file

### Agent is hanging on the first session

The first session can take 10-20+ minutes for complex projects as it reads the spec, plans features, creates project structure, and sets up git. This is expected behavior. Subsequent sessions are typically faster.

If a session truly hangs:

1. Check `.agent-harness/session.json` for error messages
2. Look for permission prompts or security blocks in the output
3. Verify your progress file format matches the configuration (e.g., `feature_list.json` with `"passes": false` fields)

## Running Tests

```bash
# Run all tests
uv run python -m unittest discover tests -v

# Run specific test modules
uv run python -m unittest tests.test_config -v         # Configuration loading
uv run python -m unittest tests.test_tracking -v       # Progress tracking
uv run python -m unittest tests.test_runner -v         # Session loop logic
uv run python -m unittest tests.test_client_factory -v # Client creation
```

Test coverage includes:

- **Security configuration**: Sandbox settings, permission rules, network isolation
- **Configuration loading**: TOML parsing, defaults, validation, error cases
- **Progress tracking**: Completion detection, JSON parsing, print formatting
- **Prompt loading**: File reading, `file:` resolution, error handling

## License

MIT License. See [LICENSE](LICENSE).
