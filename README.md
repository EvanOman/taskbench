# ClickUp Toolkit

[![Test](https://github.com/EvanOman/clickup-tools/actions/workflows/test.yml/badge.svg)](https://github.com/EvanOman/clickup-tools/actions/workflows/test.yml)
![coverage](assets/coverage.svg)

A CLI for ClickUp task management, built with Python.

## Agent Quickstart (uvx)

The fastest way for an AI agent to use this CLI -- no clone, no install:

```bash
uvx --from git+https://github.com/EvanOman/clickup-tools.git clickup --help
```

Three-command happy path:

```bash
# 1. Interactive setup -- stores your API token and picks defaults
uvx --from git+https://github.com/EvanOman/clickup-tools.git clickup setup

# 2. Verify everything works
uvx --from git+https://github.com/EvanOman/clickup-tools.git clickup status

# 3. List tasks in your default list
uvx --from git+https://github.com/EvanOman/clickup-tools.git clickup task list
```

For repeat use, install once and then call `clickup` directly:

```bash
uv tool install git+https://github.com/EvanOman/clickup-tools.git
clickup setup
clickup status
clickup task list
```

## Installation

Choose the method that fits your workflow:

| Method | Command | Best for |
|--------|---------|----------|
| **One-shot (no install)** | `uvx --from git+https://github.com/EvanOman/clickup-tools.git clickup ...` | Agents, CI, quick checks |
| **Persistent install** | `uv tool install git+https://github.com/EvanOman/clickup-tools.git` then `clickup ...` | Repeat use |
| **Local development** | `git clone <repo> && cd clickup-tools && uv sync && uv run clickup ...` | Contributing (always reflects latest source; no cache) |

## Wiring this up for an AI coding agent

This CLI was built to be driven by AI agents. Setting it up so any Claude Code / Cursor / Codex / Aider session on your machine can capture follow-up tasks for you takes about three minutes.

### 1. Install the CLI persistently

Pick one (any of the methods above works, but for agent use `uv tool install` is friendliest):

```bash
uv tool install git+https://github.com/EvanOman/clickup-tools.git
```

Both `clickup` and `cup` are now on your `PATH`.

### 2. Drop your API token in a cwd-independent location

Put the token at `~/.config/clickup-toolkit/.env` so it loads regardless of where the agent invokes the CLI:

```bash
mkdir -p ~/.config/clickup-toolkit
echo 'CLICKUP_API_KEY=pk_<your_token>' >> ~/.config/clickup-toolkit/.env
chmod 600 ~/.config/clickup-toolkit/.env
clickup status   # should print "Auth Status: Valid"
```

Get a personal token from **ClickUp → Settings → Apps → API Token**.

### 3. Configure aliases for your spaces and a default status

Agents shouldn't have to run discovery commands every time they create a task. Map your real list IDs to short aliases so the agent can route by name:

```bash
clickup setup run            # one-shot: picks default workspace/space/list interactively
# or set the alias map by hand:
clickup config set-default-list omegapoint <list-id>
clickup config set-default-list overhead <list-id>
clickup config set-default-list personal <list-id>
clickup config set default_status on-deck   # tasks land in your "ready" column by default
```

Find the IDs with `clickup discover hierarchy --depth 5`.

### 4. Add a shell alias (optional)

Short one-liner so the agent (and you) can type `cup` instead of the full binary name:

```bash
# zsh (~/.zshrc) or bash (~/.bashrc)
alias cup='clickup'
# or, if you want local-source-on-edit (developer mode):
# alias cup='uv run --project /path/to/clickup-tools clickup'
```

### 5. Teach your agent how to use it

Drop this snippet into your agent's global instructions file. For Claude Code that's `~/.claude/CLAUDE.md`; for Cursor it's `.cursorrules` (project-level) or the user-level rules file; for Codex CLI it's `~/.codex/AGENTS.md` (project-level `AGENTS.md` works too); for Aider it's `~/.aider.conf.yml`'s `read` setting.

```markdown
## Capturing Follow-up Tasks (use `cup`)

When you identify a real follow-up the user might lose track of, capture it
as a ClickUp task via `cup`. The CLI is at `~/.local/bin/clickup` (installed
via `uv tool install`); the alias `cup` is shorter.

Available spaces (route by content; do NOT run discovery commands):

| Alias | Use for |
|---|---|
| `omegapoint` | Default — active work, technical follow-ups, code reviews |
| `overhead` | Admin / process / non-coding chores |
| `personal` | Explicitly non-work |

Default status: `on-deck` (the user's "ready to pick up" column) — applied
automatically.

Invocation:
```
cup task create "Short imperative title" --list-id omegapoint --description "Context."
cup task create "Title" --list-id personal --priority 2 --status in-progress
```

When NOT to capture: anything you can resolve in the current turn, trivial
todos, or active subtasks (use the agent's own todo tool for those).

After creating, mention the task ID and URL so the user can find it.
```

Edit the alias table to match the spaces you set up in step 3. After this, any agent session can be told "add a todo for X" and it'll route to the right space automatically — no discovery, no asking.

### Verifying the agent path works

From a fresh shell, ask your agent: *"Add a todo to verify cup integration."* It should run a single `cup task create ...` and report the task ID and URL. If it asks discovery questions instead, your instructions snippet didn't load — check the file path your agent reads from.

## Features

- **CLI Interface**: Command-line tool for ClickUp task management
- **Workspace Discovery**: Navigate ClickUp hierarchy to find IDs
- **Auth Validation**: Verify API credentials and user info
- **Shared Core**: Common ClickUp API client and data models
- **Type Safety**: Full type hints and pydantic validation
- **Modern Python**: Built with Python 3.12+ and uv package manager

## Quick Start

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Option A: install globally via uv tool
uv tool install git+https://github.com/EvanOman/clickup-tools.git

# Option B: clone for local development
git clone <repo-url>
cd clickup-tools
uv sync

# Configure your ClickUp API credentials
export CLICKUP_API_KEY="your_api_key_here"

# Verify credentials
clickup status

# Discover your workspace structure
clickup discover ids

# Create a task (use list ID from discover command)
clickup task create "My new task" --list-id <discovered-id>
```

## Getting Started

### 1. Authentication

Set your ClickUp personal API token. The CLI checks these sources in order:

1. **`CLICKUP_API_KEY` environment variable** -- highest priority, checked first.
2. **`.env` file** in the current directory -- loaded automatically if present.
3. **`clickup config set-token <token>`** -- persists the token to `~/.config/clickup-toolkit/config.json`.

You can get a personal API token from **ClickUp Settings > Apps > API Token**.

Verify your credentials work:
```bash
clickup config validate
```

### 2. Finding Your Workspace Structure

ClickUp organizes content as: Workspace > Space > Folder > List > Task

To find the IDs you need:

```bash
# Start with your workspaces
clickup discover ids

# Explore a workspace's spaces
clickup discover ids --workspace-id <id>

# See folders and lists in a space
clickup discover ids --space-id <id>

# View complete hierarchy as a tree
clickup discover hierarchy

# Find the path to any list
clickup discover path <id>
```

### 3. Working with Tasks

```bash
# List tasks in a list
clickup task list --list-id <id>

# Create a task
clickup task create "New task" --list-id <id>

# Get task details
clickup task get task123

# Update a task
clickup task update task123 --name "Updated name"
```

### 4. Configuration

```bash
# View current status
clickup status

# Set default workspace/space/list
clickup config set default_list_id <id>

# Show all config
clickup config show
```

## Development

```bash
# Install dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Lint and format
uv run ruff check
uv run ruff format

# Type check
uv run ty check
```

## Available Commands

### Get started
- `clickup setup` - Interactive first-run setup (API token + defaults)
- `clickup status` - Show connection status and configuration
- `clickup whoami` - Show the authenticated user
- `clickup config` - Manage configuration and validate credentials

### Task workflow
- `clickup task list` - List tasks in a list
- `clickup task create` - Create new tasks
- `clickup task get` - Get task details
- `clickup task update` - Update existing tasks
- `clickup task delete` - Delete tasks

### Workspace navigation
- `clickup workspace list` - List workspaces/teams
- `clickup workspace spaces` - List spaces in a workspace
- `clickup workspace folders` - List folders in a space
- `clickup workspace members` - List team members
- `clickup list` - Manage lists
- `clickup discover` - Navigate workspace hierarchy and find IDs

### Other
- `clickup bulk` - Bulk operations and import/export
- `clickup template` - Template management
- `clickup version` - Show version information

## Architecture

The project uses a modular structure:

- **`clickup/core/`**: Shared ClickUp API client and data models
- **`clickup/cli/`**: Command-line interface built with Typer

See `AGENT.md` for development guidelines.

## License

MIT
