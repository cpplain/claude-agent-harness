# Harness Setup Guide

A step-by-step guide for setting up a project to use with Agent Harness.

---

## Getting Started

### Step 1: Initialize the Project

```bash
agent-harness init --project-dir ./my-project
```

This creates:

```
my-project/
  .agent-harness/
    config.toml       # Harness configuration
    spec.md           # Your project specification
    prompts/
      init.md         # One-time setup prompt
      build.md        # Iterative build prompt
```

### Step 2: Write Your Project Specification

Edit `.agent-harness/spec.md` to describe what you're building:

```markdown
# My Web App

## Overview

A React dashboard that displays real-time metrics.

## Requirements

- User authentication with JWT
- Dashboard with 3 chart types (line, bar, pie)
- REST API backend with Express
- PostgreSQL database

## Technology Stack

- React 18, TypeScript
- Express.js
- PostgreSQL, Prisma ORM

## Success Criteria

- All tests pass
- User can log in and view dashboard
- Charts update in real-time
```

**Why this matters** (from Anthropic's research):

- **Be specific** - Vague requirements lead to the agent guessing or going off-track
- **List your tech stack** - The agent needs to know which tools/frameworks to use
- **Define "done"** - Clear success criteria prevent premature completion claims

### Step 3: Configure the Harness

Edit `.agent-harness/config.toml`:

**For simple projects** (like the calculator example):

```toml
max_iterations = 10  # Limit sessions for bounded projects

[tracking]
type = "json_checklist"
file = "feature_list.json"
```

**For projects needing npm/network access:**

```toml
[security.sandbox.network]
allowed_domains = ["registry.npmjs.org", "github.com"]
allow_local_binding = true  # For dev servers

[security.permissions]
allow = ["Bash(npm *)"]
```

**For projects needing browser testing (MCP):**

```toml
[tools.mcp_servers.puppeteer]
command = "npx"
args = ["puppeteer-mcp-server"]
```

**Why JSON checklist tracking** (from Anthropic's research):

> "We switched from a markdown checklist to a JSON format... JSON was far less susceptible to accidental modification or silent failure."

The harness watches `feature_list.json` and stops when all items have `"passes": true`.

### Step 4: Customize the Init Prompt

Edit `.agent-harness/prompts/init.md` to match your project.

The init phase runs **once** and establishes the foundation for all future sessions. It should:

1. Read your spec
2. Create a feature list (all items `"passes": false`)
3. Initialize git
4. Create skeleton files
5. Create `claude-progress.txt`

**Example for a web app:**

````markdown
## YOUR ROLE - INIT PHASE

You are setting up a new project. This runs once at the start.

### STEP 1: Read the Specification

Read `.agent-harness/spec.md` to understand what you're building.

### STEP 2: Create Feature List

Create `.agent-harness/feature_list.json` with testable requirements:

```json
[
  {
    "name": "Project setup",
    "description": "Initialize React + Express",
    "passes": false
  },
  {
    "name": "Database schema",
    "description": "Prisma schema for users and metrics",
    "passes": false
  },
  { "name": "User auth", "description": "JWT login/logout", "passes": false },
  {
    "name": "Dashboard layout",
    "description": "Main dashboard component",
    "passes": false
  },
  {
    "name": "Line chart",
    "description": "Real-time line chart",
    "passes": false
  },
  {
    "name": "Bar chart",
    "description": "Bar chart component",
    "passes": false
  },
  { "name": "Pie chart", "description": "Pie chart component", "passes": false }
]
```
````

IMPORTANT:

- Mark ALL features as `"passes": false` initially
- Do NOT remove or modify feature definitions later - only update the `passes` field

### STEP 3: Initialize Project

```bash
git init
npx create-react-app . --template typescript
npm init -y  # For backend
git add . && git commit -m "Initial project setup"
```

### STEP 4: Create Progress Notes

Create `claude-progress.txt` summarizing what you set up.
This file helps future sessions understand the current state.

````

**Why this structure** (from Anthropic's research):
> "We use two complementary agents: an initializer agent for first-run setup, and a coding agent for subsequent sessions."

The init phase creates the "handoff artifacts" that future sessions need to orient themselves.

### Step 5: Customize the Build Prompt

Edit `.agent-harness/prompts/build.md`.

The build phase runs **repeatedly** and should follow this pattern:
1. **Orient** - Check pwd, git log, progress file (agent has no memory between sessions)
2. **Review** - Read feature list, understand current state
3. **Select ONE feature** - Pick the highest priority incomplete item
4. **Implement & test** - Build it and verify it works
5. **Update & commit** - Mark complete, update progress notes, commit

**Example:**
```markdown
## YOUR ROLE - BUILD PHASE

You are continuing work on a project. Each session starts fresh with no memory.

### STEP 1: Get Your Bearings
Run these commands to understand the current state:

```bash
pwd && ls -la
cat .agent-harness/spec.md
cat .agent-harness/feature_list.json
cat claude-progress.txt
git log --oneline -10
````

### STEP 2: Choose ONE Feature

Find a feature with `"passes": false` in feature_list.json.
Pick the most logical next one based on dependencies.

IMPORTANT: Only work on ONE feature per session. This prevents:

- Attempting too much at once
- Leaving code in a broken state
- Unclear progress tracking

### STEP 3: Implement & Test

- Write the code
- Write tests
- Run tests: `npm test`
- Test as an end-user would, not just at code level

### STEP 4: Update Progress

Only after verifying the feature works:

1. Update `feature_list.json` - set `"passes": true` for THIS feature only
2. Update `claude-progress.txt` with what you implemented
3. Commit your changes:

```bash
git add . && git commit -m "Implement [feature name]"
```

### Critical Rules

- ONLY mark a feature complete after thorough testing
- Leave code in production-ready condition (no broken builds)
- If you can't complete a feature, document the blocker in claude-progress.txt
- Do NOT modify feature definitions - only update the `passes` field

````

**Why this matters** (from Anthropic's research):

On orientation:
> "Each session should begin by the agent confirming current working directory, reading recent git logs, reviewing progress documentation."

On single-feature focus:
> "We added a system prompt instruction to only complete a single feature per session... This prevented the agent from attempting too much."

On testing:
> "Perform end-to-end verification... Test as a human user would, not just at code level."

On leaving code ready:
> "Leave code in production-ready condition between sessions. Eliminate bugs and incomplete implementations before session end."

### Step 6: Verify Configuration

```bash
agent-harness verify --project-dir ./my-project
````

This checks:

- Python version (3.10+)
- Claude Agent SDK installed
- Authentication configured
- Config file valid
- All `file:` references resolve
- MCP server commands available
- Directory is writable

Fix any issues before running.

### Step 7: Run the Harness

```bash
agent-harness run --project-dir ./my-project
```

The agent will:

1. Run init phase (once, skipped if feature_list.json exists)
2. Run build phase repeatedly
3. Auto-continue between sessions (3 second delay)
4. Stop when all features pass (or hit max_iterations)

---

## Quick Reference

| File                  | Purpose                                      |
| --------------------- | -------------------------------------------- |
| `config.toml`         | Harness settings (model, security, tracking) |
| `spec.md`             | What you're building (read by agent)         |
| `prompts/init.md`     | One-time setup instructions                  |
| `prompts/build.md`    | Iterative build instructions                 |
| `feature_list.json`   | Progress tracking (created by init phase)    |
| `claude-progress.txt` | Session handoff notes (created by agent)     |

---

## Common Configurations

### Read-only analysis (no edits)

```toml
[tools]
builtin = ["Read", "Glob", "Grep"]

[security]
permission_mode = "bypassPermissions"
```

### Full autonomy with sandbox (recommended for most projects)

```toml
[security]
permission_mode = "acceptEdits"

[security.sandbox]
enabled = true
auto_allow_bash_if_sandboxed = true
```

### Web development (Node.js/npm)

```toml
[security.sandbox.network]
allowed_domains = ["registry.npmjs.org", "github.com", "cdn.jsdelivr.net"]
allow_local_binding = true

[security.permissions]
allow = ["Bash(npm *)", "Bash(node *)", "Bash(npx *)", "Bash(git *)"]
deny = ["Bash(curl *)", "Bash(wget *)"]
```

### Python development

```toml
[security.sandbox.network]
allowed_domains = ["pypi.org", "files.pythonhosted.org", "github.com"]

[security.permissions]
allow = ["Bash(python *)", "Bash(pip *)", "Bash(uv *)", "Bash(git *)"]
```

---

## Troubleshooting

**Agent can't install packages**
→ Add the package registry domain to `allowed_domains`
→ Add the package manager command to `allow` list

**Agent keeps working on the same feature**
→ Check if tests are actually passing
→ Make sure the feature definition is clear and testable

**Agent marks features complete without testing**
→ Strengthen testing requirements in build prompt
→ Add explicit "run tests and verify output" steps

**Session errors / circuit breaker triggered**
→ Run `agent-harness verify` to check configuration
→ Check error_recovery settings in config.toml

**Agent goes off-track**
→ Make spec.md more specific
→ Add constraints to prompts ("Do NOT do X")

---

## Anthropic's Key Recommendations Applied

This harness follows Anthropic's guidance from "Effective Harnesses for Long-Running Agents":

| Recommendation                    | How It's Applied                                       |
| --------------------------------- | ------------------------------------------------------ |
| Two-agent pattern (init + build)  | Separate phase prompts with different responsibilities |
| JSON feature tracking             | `json_checklist` tracker with `passes` field           |
| Session orientation               | Build prompt starts with pwd, git log, progress review |
| Single feature per session        | Explicit instruction in build prompt                   |
| End-to-end testing                | Testing requirements in build prompt                   |
| Production-ready between sessions | "Leave code working" instruction                       |
| Clear handoff artifacts           | `claude-progress.txt` + git commits                    |

---

## Next Steps

Once you're comfortable with the basic setup, explore:

- **[Configuration Reference](../agent_harness/templates/config.toml)** - All available options with detailed comments
- **[Examples](../examples/)** - Real-world project setups
  - [Simple Calculator](../examples/simple-calculator/) - Python, completes in ~5 minutes
  - [Claude.ai Clone](../examples/claude-ai-clone/) - Next.js with MCP browser automation
- **[Main README](../README.md)** - Technical details on how the harness works
