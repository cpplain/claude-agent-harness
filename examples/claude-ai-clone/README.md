# Claude.ai Clone Example

This example recreates the original autonomous coding agent demo using the generic agent harness configuration.

## What It Builds

An autonomous agent that builds a fully functional clone of claude.ai using:

- React + Vite frontend
- Node.js + Express backend
- Puppeteer for browser-based testing

## Usage

From the repository root:

```bash
# Verify setup
python -m agent_harness verify \
    --harness-dir examples/claude-ai-clone/.agent-harness

# Run with harness config from example, agent works in ./my-claude-clone
python -m agent_harness run \
    --project-dir ./my-claude-clone \
    --harness-dir examples/claude-ai-clone/.agent-harness

# Run with iteration limit
python -m agent_harness run \
    --project-dir ./my-claude-clone \
    --harness-dir examples/claude-ai-clone/.agent-harness \
    --max-iterations 5
```

## How It Works

The configuration uses two phases:

1. **Initializer** (runs once): Reads `app_spec.txt`, creates `feature_list.json` with 200+ test cases, sets up project structure, initializes git.

2. **Coding** (runs repeatedly): Picks up from the previous session, implements features one at a time, verifies through browser automation, marks tests as passing.

## Configuration

See `.agent-harness/config.toml` for the full configuration including:

- Puppeteer MCP server for browser testing
- Bash command allowlist for security
- JSON checklist tracking with `feature_list.json`
- Two-phase agent pattern (initializer + coding)
