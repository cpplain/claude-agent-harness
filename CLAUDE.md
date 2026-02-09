# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a generic harness for running long-running autonomous coding agents using the Claude Agent SDK. It implements Anthropic's two-agent pattern (initializer + coding agent) with configurable MCP tools and multi-layered security.

The harness is **project-agnostic** - all project-specific configuration (tech stack, tools, prompts) is declared in `.agent-harness/config.toml` files within projects.

## Key Architecture Concepts

### Configuration-Based Architecture

Unlike the original flat harness, this codebase uses:

- **Package structure**: `agent_harness/` module with proper imports
- **Protocol-based tracking**: `ProgressTracker` Protocol with pluggable implementations
- **Phase-driven execution**: Declarative phase definitions in config.toml
- **Dataclass configs**: Type-safe configuration using Python dataclasses

### Session Management (runner.py)

- Each session creates a **fresh context window** via `create_client()`
- Progress persists between sessions via:
  - Tracking file (e.g., `feature_list.json`) tracking feature completion
  - Session state file (`session.json`) tracking completed run_once phases
  - Git commits preserving code changes
- Sessions auto-continue after configured delay (default 3s)
- **Completion detection**: Harness stops when `tracker.is_complete()` returns True (all features passing)

### Error Recovery & Circuit Breaker (runner.py:199-292)

Prevents runaway API costs when sessions fail repeatedly:

- Tracks `consecutive_errors` across sessions
- Exponential backoff: 5s → 10s → 20s → 40s → 120s (capped)
- Circuit breaker trips after 5 consecutive errors (configurable)
- Successful session resets error counter
- Error context forwarded to next session to help recovery

Configuration in `config.toml`:

```toml
[error_recovery]
max_consecutive_errors = 5
initial_backoff_seconds = 5.0
max_backoff_seconds = 120.0
backoff_multiplier = 2.0
```

### Multi-Layered Security (client_factory.py + security.py)

Defense-in-depth approach:

1. **OS-level sandbox**: Bash commands run in isolated environment preventing filesystem escape
2. **Filesystem permissions**: File operations restricted to `allowed_paths` (default: `./**`)
3. **Command allowlist**: Bash commands validated against configured allowed commands
4. **Git validation**: Automatically blocks destructive operations when `git` is allowed:
   - Blocks: `git clean`, `git reset --hard`, `git checkout -- <path>`, `git push --force/-f`
   - Allows: All other git operations (status, add, commit, diff, log, etc.)
5. **MCP tool restrictions**: Optional regex-based patterns and action allowlists
6. **Special command validation**: Additional checks for destructive operations:
   - `pkill`: Only allows killing configured dev processes (node, npm, vite, next)
   - `chmod`: Only allows `+x` mode (making files executable)
   - `init.sh`: Only allows `./init.sh` execution

### OAuth Token Validation (client_factory.py:104-116)

The client validates OAuth tokens to catch common issues:

- Strips whitespace from token
- Checks for embedded spaces/newlines/carriage returns
- Raises helpful error with debugging info if malformed

This prevents cryptic authentication failures from clipboard/env var issues.

### Configuration System (config.py)

- Projects declare everything in `.agent-harness/config.toml`
- Configuration dataclasses: `HarnessConfig`, `ToolsConfig`, `SecurityConfig`, `BashSecurityConfig`, `McpSecurityConfig`, `TrackingConfig`, `ErrorRecoveryConfig`, `PhaseConfig`, `InitFileConfig`
- All prompt file paths support `file:` references resolved relative to harness dir
- Comprehensive validation with helpful error messages

### Progress Tracking (tracking.py)

- Configurable via `[tracking]` section in config.toml
- Protocol-based design allows pluggable implementations
- Three tracker types:
  - `JsonChecklistTracker`: Tracks completion by checking boolean field in JSON array
  - `NotesFileTracker`: Plain text notes file (no structured completion)
  - `NoneTracker`: No-op tracker when tracking is disabled
- `is_complete()` method returns True when all items passing (only for JsonChecklistTracker)

## Commands

### Run the harness

```bash
# Basic usage
python -m agent_harness run --project-dir examples/claude-ai-clone

# With max iterations (for testing)
python -m agent_harness run --project-dir examples/claude-ai-clone --max-iterations 3

# Custom model
python -m agent_harness run --project-dir examples/claude-ai-clone --model claude-opus-4-6
```

### Verify setup

```bash
# Verify Python/CLI/auth/dependencies
python -m agent_harness verify

# Verify project configuration
python -m agent_harness verify --project-dir examples/claude-ai-clone
```

### Run tests

```bash
# All tests
python -m unittest discover tests -v

# Specific test modules
python -m unittest tests.test_security -v
python -m unittest tests.test_config -v
python -m unittest tests.test_tracking -v
python -m unittest tests.test_runner -v
python -m unittest tests.test_client_factory -v
```

### Authentication

Set one of these environment variables:

- `ANTHROPIC_API_KEY` - Direct API key
- `CLAUDE_CODE_OAUTH_TOKEN` - OAuth token from `claude setup-token`

## Development Notes

### Adding New Security Rules

To add command validation (security.py):

1. Add command to project's `security.bash.allowed_commands` in config.toml
2. If command needs validation beyond allowlist, add validator:
   - Add to `security.bash.extra_validators.{command_name}` in config.toml
   - Create `validate_{command}_command()` function returning `(bool, str)` tuple
   - Add validation case in `bash_security_hook()` (check `commands_needing_extra`)
3. **Git validation is automatic** - no extra config needed when git is in allowed_commands

### Creating New Example Projects

1. Create directory with `.agent-harness/config.toml`
2. Define prompts in `.agent-harness/prompts/`
3. Configure phases, tracking, security, and MCP servers in config.toml
4. Run `python -m agent_harness verify --project-dir your-project` to validate

### Testing Security Changes

The test suite in `tests/test_security.py` covers:

- Command extraction from complex shell syntax (pipes, &&, ||, subshells)
- Parenthesis handling to prevent bypass attempts
- Git destructive operation blocking (26 test cases)
- pkill/chmod/init.sh validation
- MCP tool restriction enforcement
- Balanced paren stripping

Always add test cases when modifying security validation logic.

### Client Creation Flow

1. `create_client()` builds `ClaudeSDKClient` with:
   - Security settings written to `.agent-harness/.claude_settings.json` in project dir
   - Working directory set to project_dir
   - Auth credentials passed via `env` parameter
   - Allowed tools list (builtin + MCP wildcards)
   - Pre-tool-use hooks for Bash and MCP tools
2. SDK spawns subprocess with:
   - `cwd=project_dir` (all file operations relative to this)
   - `settings=.claude_settings.json` path (contains sandbox/permissions config)
   - `env=auth_env` (OAuth token or API key)

### Exit Reasons

The harness tracks why agent execution stops:

- `"ALL COMPLETE"`: All items in progress tracker passing (via `tracker.is_complete()`)
- `"MAX ITERATIONS"`: Reached configured `max_iterations`
- `"TOO MANY ERRORS"`: Circuit breaker tripped after consecutive errors

### Post-Run Instructions

Configure `post_run_instructions` in config.toml to show next steps:

```toml
post_run_instructions = [
    "npm install",
    "npm run dev",
    "Open http://localhost:3000",
]
```

These are displayed in the final summary banner.

## Recent Changes

This codebase recently incorporated safety features from the original flat harness:

1. **Error recovery & circuit breaker**: Exponential backoff and max consecutive error limit
2. **Completion detection**: Automatic stop when `tracker.is_complete()` returns True
3. **Error context forwarding**: Previous session errors prepended to next session prompt
4. **Git destructive operation blocking**: Automatic validation when git is in allowed commands
5. **OAuth token validation**: Checks for malformed tokens before use
6. **Shell parsing hardening**: `strip_balanced_parens()` prevents security bypass attempts
7. **MCP tool restrictions**: Regex patterns and action allowlists for MCP tools
8. **Post-run instructions**: Configurable next steps shown in final summary
