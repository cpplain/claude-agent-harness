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
# Copy the harness config to your project directory
mkdir -p ./my-claude-clone
cp -r examples/claude-ai-clone/.agent-harness ./my-claude-clone/

# Verify setup
uv run python -m agent_harness verify --project-dir ./my-claude-clone

# Run the agent
uv run python -m agent_harness run --project-dir ./my-claude-clone

# Run with iteration limit
uv run python -m agent_harness run --project-dir ./my-claude-clone --max-iterations 5
```

## How It Works

The configuration uses two phases:

1. **Initializer** (runs once): Reads `app_spec.txt`, creates `feature_list.json` with 200+ test cases, sets up project structure, initializes git.

2. **Coding** (runs repeatedly): Picks up from the previous session, implements features one at a time, verifies through browser automation, marks tests as passing.

## Configuration

See `.agent-harness/config.toml` for the full configuration including:

- Puppeteer MCP server for browser testing
- Sandbox with network isolation and permission rules
- JSON checklist tracking with `feature_list.json`
- Two-phase agent pattern (initializer + coding)
