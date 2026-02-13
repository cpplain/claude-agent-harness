# Simple Calculator Example

A minimal example demonstrating the agent harness with a straightforward Python project that completes in ~5 minutes.

## What It Builds

An autonomous agent that builds a Python calculator module (`calculator.py`) with comprehensive unit tests (`test_calculator.py`).

Features:

- 6 basic math functions (add, subtract, multiply, divide, power, modulo)
- Edge case handling (division by zero, negative numbers)
- Full test coverage with unittest

## Usage

From the repository root:

```bash
# Copy the harness config to your project directory
mkdir -p ./my-calculator
cp -r examples/simple-calculator/.agent-harness ./my-calculator/

# Verify setup
uv run python -m agent_harness verify --project-dir ./my-calculator

# Run the agent (limited to 10 iterations)
uv run python -m agent_harness run --project-dir ./my-calculator
```

## How It Works

The configuration uses two phases:

1. **Init** (runs once): Reads `spec.md`, creates `feature_list.json` with 7 features, initializes git and skeleton files.

2. **Build** (runs repeatedly): Implements one function at a time, writes comprehensive tests, verifies all tests pass, marks feature complete.

## Why This Example?

Perfect for:

- Learning the agent harness basics
- Quick demos (completes in ~5 minutes)
- Testing your harness setup
- Understanding multi-phase workflows

## Configuration

See `.agent-harness/config.toml` for:

- Minimal tool set (no MCP servers)
- No network access (sandbox with empty allowed_domains)
- JSON checklist tracking
- 10-iteration limit to prevent runaway costs
- Two-phase workflow (init + build)
