# Taskbench

[![Test](https://github.com/EvanOman/clickup-tools/actions/workflows/test.yml/badge.svg)](https://github.com/EvanOman/clickup-tools/actions/workflows/test.yml)
![coverage](assets/coverage.svg)

A backend-pluggable task-management CLI, built for AI agents. ClickUp is the default backend; the JSON local adapter works with zero setup.

## Agent Quickstart (uvx)

The fastest way for an AI agent to use this CLI -- no clone, no install:

```bash
uvx --from git+https://github.com/EvanOman/clickup-tools.git taskbench --help
```

Four-command happy path:

```bash
# 1. Non-interactive setup -- with CLICKUP_API_KEY in the env or .env, this
#    auto-picks your workspace/space/list (agents: always prefer --auto;
#    humans can drop the flag for interactive prompts)
uvx --from git+https://github.com/EvanOman/clickup-tools.git taskbench setup run --auto

# 2. Verify everything works
uvx --from git+https://github.com/EvanOman/clickup-tools.git taskbench status

# 3. Discover list IDs in your workspace
uvx --from git+https://github.com/EvanOman/clickup-tools.git taskbench discover hierarchy

# 4. Orient: per-list task counts and last-updated times
uvx --from git+https://github.com/EvanOman/clickup-tools.git taskbench list stats

# 5. List tasks in your default list (--brief = compact projection, recommended for agents)
uvx --from git+https://github.com/EvanOman/clickup-tools.git taskbench task list --brief
```

For repeat use, install once and then call `taskbench` (or `tb`) directly:

```bash
uv tool install git+https://github.com/EvanOman/clickup-tools.git
taskbench setup
taskbench status
taskbench task list
```

## Installation

Choose the method that fits your workflow:

| Method | Command | Best for |
|--------|---------|----------|
| **One-shot (no install)** | `uvx --from git+https://github.com/EvanOman/clickup-tools.git taskbench ...` | Agents, CI, quick checks |
| **Persistent install** | `uv tool install git+https://github.com/EvanOman/clickup-tools.git` then `taskbench ...` | Repeat use |
| **Local development** | `git clone <repo> && cd clickup-tools && uv sync && uv run taskbench ...` | Contributing (always reflects latest source; no cache) |

## Wiring this up for an AI coding agent

This CLI was built to be driven by AI agents. Setting it up so any Claude Code / Cursor / Codex / Aider session on your machine can capture follow-up tasks for you takes about three minutes.

### 1. Install the CLI persistently

Pick one (any of the methods above works, but for agent use `uv tool install` is friendliest):

```bash
uv tool install git+https://github.com/EvanOman/clickup-tools.git
```

Both `taskbench` and `tb` are now on your `PATH`.

### 2. Drop your API token in a cwd-independent location

Put the token at `~/.config/taskbench/.env` so it loads regardless of where the agent invokes the CLI:

```bash
mkdir -p ~/.config/taskbench
echo 'CLICKUP_API_KEY=pk_<your_token>' >> ~/.config/taskbench/.env
chmod 600 ~/.config/taskbench/.env
taskbench status   # should print "Auth Status: Valid"
```

Get a personal token from **ClickUp → Settings → Apps → API Token**.

### 3. Discover your list IDs

Before configuring aliases, find the numeric list IDs for the lists you want agents to target:

```bash
taskbench discover hierarchy          # prints workspace > space > folder > list tree with IDs
```

Or skip discovery entirely: `taskbench setup run --auto` picks the only workspace/space automatically (and the largest list when several exist) — zero-to-working `taskbench task list` in one non-interactive command. Pass explicit `--team-id/--space-id/--list-id` to override any level, or use `--non-interactive` with all IDs for fully pinned setup.

### 4. Configure aliases for your spaces and a default status

Agents shouldn't have to run discovery commands every time they create a task. Map your real list IDs to short aliases so the agent can route by name:

```bash
taskbench setup run --auto     # one-shot non-interactive: auto-picks workspace/space/list
taskbench setup run            # same, but interactive prompts (for humans)
# or set the alias map by hand:
taskbench config alias omegapoint <list-id>
taskbench config alias overhead <list-id>
taskbench config alias personal <list-id>
taskbench config set default_status on-deck   # tasks land in your "ready" column by default
```

Find the IDs with `taskbench discover hierarchy --depth 5`. The `--list-id` flag accepts both numeric IDs and configured aliases (e.g. `--list-id omegapoint`).

### 5. Add a shell alias (optional)

Short one-liner so the agent (and you) can type `tb` instead of the full binary name:

```bash
# zsh (~/.zshrc) or bash (~/.bashrc)
alias tb='taskbench'
# or, if you want local-source-on-edit (developer mode):
# alias tb='uv run --project /path/to/clickup-tools taskbench'
```

### 6. Teach your agent how to use it

Drop this snippet into your agent's global instructions file. For Claude Code that's `~/.claude/CLAUDE.md`; for Cursor it's `.cursorrules` (project-level) or the user-level rules file; for Codex CLI it's `~/.codex/AGENTS.md` (project-level `AGENTS.md` works too); for Aider it's `~/.aider.conf.yml`'s `read` setting.

```markdown
## Capturing Follow-up Tasks (use `tb`)

When you identify a real follow-up the user might lose track of, capture it
as a ClickUp task via `tb`. The CLI is at `~/.local/bin/taskbench` (installed
via `uv tool install`); the alias `tb` is shorter.

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
tb task create "Short imperative title" --list-id omegapoint --description "Context."
tb task create "Title" --list-id personal --priority 2 --status in-progress
```

When NOT to capture: anything you can resolve in the current turn, trivial
todos, or active subtasks (use the agent's own todo tool for those).

After creating, mention the task ID and URL so the user can find it.
```

Edit the alias table to match the spaces you set up in step 3. After this, any agent session can be told "add a todo for X" and it'll route to the right space automatically — no discovery, no asking.

### Verifying the agent path works

From a fresh shell, ask your agent: *"Add a todo to verify tb integration."* It should run a single `tb task create ...` and report the task ID and URL. If it asks discovery questions instead, your instructions snippet didn't load — check the file path your agent reads from.

## Features

- **CLI Interface**: Command-line tool for task management (ClickUp default backend)
- **Workspace Discovery**: Navigate ClickUp hierarchy to find IDs
- **Auth Validation**: Verify API credentials and user info
- **Shared Core**: Common API client and data models
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
taskbench status

# Discover your workspace structure
taskbench discover ids

# Create a task (use list ID from discover command)
taskbench task create "My new task" --list-id <discovered-id>
```

## Getting Started

### 1. Authentication

Set your ClickUp personal API token. The CLI checks these sources in order:

1. **`CLICKUP_API_KEY` environment variable** -- highest priority, checked first.
2. **`.env` file** in the current directory -- loaded automatically if present.
3. **`taskbench config set-token <token>`** -- persists the token to `~/.config/taskbench/config.json`.

You can get a personal API token from **ClickUp Settings > Apps > API Token**.

Verify your credentials work:
```bash
taskbench config validate
```

### 2. Finding Your Workspace Structure

ClickUp organizes content as: Workspace > Space > Folder > List > Task

To find the IDs you need:

```bash
# Start with your workspaces
taskbench discover ids

# Explore a workspace's spaces
taskbench discover ids --workspace-id <id>

# See folders and lists in a space
taskbench discover ids --space-id <id>

# View complete hierarchy as a tree
taskbench discover hierarchy

# Find the path to any list
taskbench discover path <id>
```

### 3. Working with Tasks

```bash
# List tasks in a list
taskbench task list --list-id <id>

# Create a task
taskbench task create "New task" --list-id <id>

# Get task details
taskbench task get task123

# Update a task
taskbench task update task123 --name "Updated name"

# Search tasks across your workspace
taskbench task search --query "keyword"

# List tasks assigned to you
taskbench task mine

# View and add comments
taskbench task comments list <task-id>
taskbench task comments add <task-id> "Comment text"
```

### 4. Configuration

```bash
# View current status
taskbench status

# Set default workspace/space/list
taskbench config set default_list_id <id>

# Show all config
taskbench config show
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
- `taskbench setup` - Interactive first-run setup (API token + defaults)
- `taskbench status` - Show the authenticated user, connection status, and configuration
- `taskbench config` - Manage configuration and validate credentials

### Task workflow
- `taskbench task list` - List tasks in a list
- `taskbench task create` - Create new tasks
- `taskbench task get` - Get task details
- `taskbench task update` - Update existing tasks
- `taskbench task delete` - Delete tasks
- `taskbench task mine` - List tasks assigned to you across all configured lists
- `taskbench task search` - Search tasks by keyword across a workspace
- `taskbench task comments list` - List comments on a task
- `taskbench task comments add` - Add a comment to a task

### Workspace navigation
- `taskbench workspace list` - List workspaces/teams
- `taskbench workspace spaces` - List spaces in a workspace
- `taskbench workspace folders` - List folders in a space
- `taskbench workspace members` - List team members
- `taskbench list` - Manage lists (`taskbench list stats` for per-list task/open counts)
- `taskbench discover` - Navigate workspace hierarchy and find IDs

### Other
- `taskbench bulk` - Bulk operations and import/export
- `taskbench template` - Template management
- `taskbench version` - Show version information

## Architecture

The project uses a modular structure:

- **`taskbench/core/`**: Shared API client and data models
- **`taskbench/cli/`**: Command-line interface built with Typer

See `AGENT.md` for development guidelines.

## Backends

The CLI talks to any backend implementing the `TaskProvider` protocol (`taskbench/core/providers.py`). External adapters are discovered via `entry_points(group="taskbench.providers")`. Per-backend setup and spin-up instructions: [docs/backends.md](docs/backends.md). Implementing a backend in another language? Target the [OpenAPI contract](spec/openapi.yaml) ([design notes](spec/README.md)).

| Backend | Adapter | Deployment |
|---------|---------|------------|
| ClickUp | `taskbench/core/client.py` (default) | SaaS — nothing to deploy |
| Local JSON | `taskbench/core/json_provider.py` | None — file-backed, used for evals |

## License

MIT
