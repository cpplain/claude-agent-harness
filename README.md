# Autonomous Coding Agent Demo

A minimal harness demonstrating long-running autonomous coding with the Claude Agent SDK. This demo implements a two-agent pattern (initializer + coding agent) that can build complete applications over multiple sessions.

## Prerequisites

### System Requirements

Verify you have the required versions:

```bash
# Python 3.10 or higher (required by claude-agent-sdk)
python3 --version

# Node.js and npm (required for Puppeteer MCP server)
node --version
npm --version
```

If you need to install these:

- **Python:** Download from [python.org](https://www.python.org/downloads/) (3.10+)
- **Node.js:** Download from [nodejs.org](https://nodejs.org/) (includes npm)

### Installation

**Step 1:** Install Claude Code CLI (latest version required)

```bash
npm install -g @anthropic-ai/claude-code
```

Verify installation:

```bash
claude --version  # Should be latest version
```

**Step 2:** Install Python dependencies using one of these methods:

#### Method 1: Using uv (Recommended - Fast and Modern)

```bash
# Install uv if you don't have it
pip install uv

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Verify installation:

```bash
pip show claude-agent-sdk  # Check SDK is installed
```

#### Method 2: Using venv (Standard Python Virtual Environment)

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Verify installation:

```bash
pip show claude-agent-sdk  # Check SDK is installed
```

#### Method 3: Using pip (Simple but Not Recommended)

```bash
# Install directly (not recommended - use virtual environment instead)
pip install -r requirements.txt
```

**Warning:** Installing without a virtual environment can cause dependency conflicts. Use Method 1 or 2 instead.

### API Key Configuration

Set up authentication using **one** of these methods:

**Option 1: API Key** (from [console.anthropic.com](https://console.anthropic.com))

```bash
export ANTHROPIC_API_KEY='sk-ant-api03-...'
```

**Option 2: OAuth Token** (from Claude Code CLI)

```bash
claude setup-token
export CLAUDE_CODE_OAUTH_TOKEN='your-oauth-token'
```

**Option 3: Environment File with 1Password** (most secure)

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your credentials (supports 1Password references)
# Then load it:
source .env
```

For automated loading, consider using [direnv](https://direnv.net/).

## Quick Start

```bash
python autonomous_agent_demo.py --project-dir ./my_project
```

For testing with limited iterations:

```bash
python autonomous_agent_demo.py --project-dir ./my_project --max-iterations 3
```

## Important Timing Expectations

> **Warning: This demo takes a long time to run!**

- **First session (initialization):** The agent generates a `feature_list.json` with 200 test cases. This takes several minutes and may appear to hang - this is normal. The agent is writing out all the features.

- **Subsequent sessions:** Each coding iteration can take **5-15 minutes** depending on complexity.

- **Full app:** Building all 200 features typically requires **many hours** of total runtime across multiple sessions.

**Tip:** The 200 features parameter in the prompts is designed for comprehensive coverage. If you want faster demos, you can modify `prompts/initializer_prompt.md` to reduce the feature count (e.g., 20-50 features for a quicker demo).

## How It Works

### Two-Agent Pattern

1. **Initializer Agent (Session 1):** Reads `app_spec.txt`, creates `feature_list.json` with 200 test cases, sets up project structure, and initializes git.

2. **Coding Agent (Sessions 2+):** Picks up where the previous session left off, implements features one by one, and marks them as passing in `feature_list.json`.

### Session Management

- Each session runs with a fresh context window
- Progress is persisted via `feature_list.json` and git commits
- The agent auto-continues between sessions (3 second delay)
- Press `Ctrl+C` to pause; run the same command to resume

## Security Model

This demo uses a defense-in-depth security approach (see `security.py` and `client.py`):

1. **OS-level Sandbox:** Bash commands run in an isolated environment
2. **Filesystem Restrictions:** File operations restricted to the project directory only
3. **Bash Allowlist:** Only specific commands are permitted:
   - File inspection: `ls`, `cat`, `head`, `tail`, `wc`, `grep`
   - Node.js: `npm`, `node`
   - Version control: `git`
   - Process management: `ps`, `lsof`, `sleep`, `pkill` (dev processes only)

Commands not in the allowlist are blocked by the security hook.

## Project Structure

```
autonomous-coding/
├── autonomous_agent_demo.py  # Main entry point
├── agent.py                  # Agent session logic
├── client.py                 # Claude SDK client configuration
├── security.py               # Bash command allowlist and validation
├── progress.py               # Progress tracking utilities
├── prompts.py                # Prompt loading utilities
├── prompts/
│   ├── app_spec.txt          # Application specification
│   ├── initializer_prompt.md # First session prompt
│   └── coding_prompt.md      # Continuation session prompt
└── requirements.txt          # Python dependencies
```

## Generated Project Structure

After running, your project directory will contain:

```
my_project/
├── feature_list.json         # Test cases (source of truth)
├── app_spec.txt              # Copied specification
├── init.sh                   # Environment setup script
├── claude-progress.txt       # Session progress notes
├── .claude_settings.json     # Security settings
└── [application files]       # Generated application code
```

## Running the Generated Application

After the agent completes (or pauses), you can run the generated application:

```bash
cd generations/my_project

# Run the setup script created by the agent
./init.sh

# Or manually (typical for Node.js apps):
npm install
npm run dev
```

The application will typically be available at `http://localhost:3000` or similar (check the agent's output or `init.sh` for the exact URL).

## Command Line Options

| Option             | Description               | Default                      |
| ------------------ | ------------------------- | ---------------------------- |
| `--project-dir`    | Directory for the project | `./autonomous_demo_project`  |
| `--max-iterations` | Max agent iterations      | Unlimited                    |
| `--model`          | Claude model to use       | `claude-sonnet-4-5-20250929` |

## Customization

### Changing the Application

Edit `prompts/app_spec.txt` to specify a different application to build.

### Adjusting Feature Count

Edit `prompts/initializer_prompt.md` and change the "200 features" requirement to a smaller number for faster demos.

### Modifying Allowed Commands

Edit `security.py` to add or remove commands from `ALLOWED_COMMANDS`.

## Troubleshooting

**"Appears to hang on first run"**
This is normal. The initializer agent is generating 200 detailed test cases, which takes significant time. Watch for `[Tool: ...]` output to confirm the agent is working.

**"Command blocked by security hook"**
The agent tried to run a command not in the allowlist. This is the security system working as intended. If needed, add the command to `ALLOWED_COMMANDS` in `security.py`.

**"API key not set"**
Ensure `ANTHROPIC_API_KEY` is exported in your shell environment.

**"Python version too old"**
The claude-agent-sdk requires Python 3.10 or higher. Check your version with `python3 --version`. If needed, install a newer Python version from [python.org](https://www.python.org/downloads/).

**"ModuleNotFoundError: No module named 'claude_agent_sdk'"**
This usually means you forgot to activate your virtual environment or install dependencies. Run:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

**"Node.js or npm not found"**
The Puppeteer MCP server requires Node.js and npm. Install from [nodejs.org](https://nodejs.org/) and verify with `node --version` and `npm --version`.

## License

Internal Anthropic use.
