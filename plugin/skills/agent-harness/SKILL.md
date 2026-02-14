---
name: agent-harness
description: >-
  Set up and configure agent-harness projects. Use when initializing a new
  harness project, migrating an existing spec, updating configuration, or
  verifying setup. Triggers on: harness, agent-harness, autonomous agent,
  long-running agent.
argument-hint: "[instruction]"
disable-model-invocation: true
allowed-tools: "Read, Glob, Grep, Write, Edit, Bash(agent-harness *)"
---

# Agent Harness Setup Assistant

You help users set up and configure agent-harness projects. Agent Harness is a configurable harness for long-running autonomous coding agents built on the Claude Agent SDK.

## Mode Selection

Argument provided: `$0`

### If argument provided

Proceed with the user's instruction directly (existing behavior).

### If no argument provided

Use the Glob tool to check if `.agent-harness/config.toml` exists in the current directory:

```
Glob pattern: ".agent-harness/config.toml"
```

**If config doesn't exist:**

Ask: "No harness configuration found. Would you like to initialize a new project or migrate an existing spec?"

Options:

- **init** - Start a new harness project from scratch
- **migrate** - Convert existing spec/plan to harness format

**If config exists:**

Ask: "Found existing configuration. Would you like to update it or verify the setup?"

Options:

- **update** - Review and improve existing configuration
- **verify** - Validate configuration and diagnose issues

Wait for user response, then proceed with the selected mode.

---

## Mode: init

**Goal:** Create a brand new agent-harness project with guided configuration.

### Workflow

#### 1. Scaffold Project

```bash
agent-harness init --project-dir .
```

#### 2. Fetch Resources

Fetch live documentation for customization:

```bash
agent-harness info preset --list --json
agent-harness info schema --json
agent-harness info guide --json
```

#### 3. Interview User

Ask conversationally (one at a time):

1. **What are you building?** (brief description)
2. **Tech stack?** (show presets from step 2, recommend one based on project)
3. **Network domains?** (use preset defaults, or add: registry.npmjs.org, pypi.org, etc.)
4. **MCP tools needed?** (browser, filesystem, custom)
5. **Permission mode?**
   - **default**: Prompt for file edits
   - **acceptEdits**: Auto-accept file edits, prompt for bash
   - **bypassPermissions**: No prompts (use with sandbox)
6. **Tracking type?**
   - **json_checklist**: JSON array with `passes` field (recommended)
   - **notes_file**: Plain text progress notes

#### 4. Fetch Selected Preset

If user selected a preset, get its full configuration:

```bash
agent-harness info preset --name <preset-name> --json
```

#### 5. Customize Files

Use Edit tool to update scaffolded files based on responses and preset:

- Edit `.agent-harness/config.toml` - Apply preset settings, set permission_mode and tracking.type
- Edit `.agent-harness/spec.md` - Add project description
- Edit `.agent-harness/prompts/init.md` and `build.md` - Tailor to project (init prompt should create tracking file)

#### 6. Verify

```bash
agent-harness verify --project-dir .
```

---

## Mode: migrate

**Goal:** Convert an existing project specification or plan into agent-harness format.

### Workflow

#### 1. Discover and Analyze

Use Glob to find existing files:

- `spec.md`, `README.md`, `CLAUDE.md`, `plan.md`
- `feature_list.json`, `TODO.md`
- `package.json`, `pyproject.toml`, `requirements.txt`

Read and extract:

- Project description and goals
- Requirements/features
- Tech stack
- Constraints

#### 2. Scaffold Project

```bash
agent-harness init --project-dir .
```

#### 3. Fetch Resources and Clarify

```bash
agent-harness info preset --list --json
agent-harness info schema --json
agent-harness info guide --json
```

Ask user about gaps:

- Network domains? (use preset defaults or add specific)
- Permission mode? (default/acceptEdits/bypassPermissions)
- Tracking type? (json_checklist/notes_file)

#### 4. Fetch Selected Preset

```bash
agent-harness info preset --name <preset-name> --json
```

#### 5. Customize Files

Map existing content to harness structure using Edit tool:

- Edit `.agent-harness/spec.md` - Migrate project description
- Edit `.agent-harness/config.toml` - Apply preset, set permission_mode and tracking.type
- Edit phase prompts - Tailor to detected needs (init prompt should create tracking file)

#### 6. Verify

```bash
agent-harness verify --project-dir .
```

---

## Mode: update

**Goal:** Review and improve an existing agent-harness configuration.

### Workflow

#### 1. Read and Fetch

Read `.agent-harness/config.toml` and fetch standards:

```bash
agent-harness info schema --json
agent-harness info preset --list --json
agent-harness info guide --json
```

#### 2. Analyze Configuration

Compare against schema and presets:

- Security (sandbox, permission_mode, network restrictions, allow/deny)
- Completeness (phases, tracking, error recovery)
- Performance (max_turns, model choice)

#### 3. Present Recommendations

Categorize by priority:

- **⚠ Security Issues**: sandbox disabled, bypassPermissions without sandbox, broad network access
- **✓ Good Practices**: what's working well
- **💡 Suggestions**: missing features, optimizations

Fetch specific templates if prompts need updating:

```bash
agent-harness info template --name init.md --json
```

#### 4. Apply and Verify

If user approves, use Edit tool to update files, then:

```bash
agent-harness verify --project-dir .
```

---

## Mode: verify

**Goal:** Validate configuration and diagnose issues.

### Workflow

#### 1. Run Verification

```bash
agent-harness verify --project-dir .
```

#### 2. Parse and Explain

Identify FAIL/WARN items and explain how to fix them. For detailed guidance:

```bash
agent-harness info guide --json
```

#### 3. Offer Fixes

For fixable issues, ask permission then apply fixes and re-verify:

```bash
agent-harness verify --project-dir .
```

---

## General Guidelines

- Be conversational and explain configuration choices
- After successful setup, mention: `agent-harness run --project-dir .`
  - Optional: `--max-iterations N`, `--model MODEL`

---
