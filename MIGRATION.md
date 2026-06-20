# Migration Guide: clickup-toolkit to taskbench (v1.0.0)

## What changed

The project has been renamed from `clickup-toolkit` to `taskbench` and the
version bumped to 1.0.0. The rename reflects the CLI's evolution into a
backend-pluggable tool (ClickUp, JSON local, external plugins) rather than a
ClickUp-only utility.

## Binary names

| Old | New |
|---|---|
| `clickup` | `taskbench` |
| `cup` | `tb` |

## Environment variables

| Old | New | Status |
|---|---|---|
| `CLICKUP_PROVIDER` | `TASKBENCH_PROVIDER` | Old name works with a one-time deprecation warning to stderr |
| `CLICKUP_CONFIG_PATH` | `TASKBENCH_CONFIG_PATH` | Old name works with a one-time deprecation warning to stderr |
| `CLICKUP_API_KEY` | `CLICKUP_API_KEY` | **Unchanged** (refers to the ClickUp service, not the CLI) |
| `CLICKUP_API_TOKEN` | `CLICKUP_API_TOKEN` | **Unchanged** |
| `CLICKUP_JSON_STORE` | `CLICKUP_JSON_STORE` | **Unchanged** (JSON provider config) |

## Config directory

| Old | New |
|---|---|
| `~/.config/clickup-toolkit/` | `~/.config/taskbench/` |

On first run, if `~/.config/taskbench/` does not exist but
`~/.config/clickup-toolkit/` does, the CLI automatically copies
`config.json` and `.env` to the new location. The old directory is never
deleted. Run `taskbench config clean` when you are ready to remove it.

## Python package

| Old | New |
|---|---|
| `from clickup.core import ...` | `from taskbench.core import ...` |
| `from clickup.cli import ...` | `from taskbench.cli import ...` |

The `ClickUpConfig` class is still available as a backward-compat alias for
`TaskbenchConfig` (same object). `ClickUpClient`, `ClickUpError`, and all
ClickUp-service-specific names are unchanged.

## External adapter plugins

Adapters are now discovered via `entry_points(group="taskbench.providers")`.
Register your adapter in your package's `pyproject.toml`:

```toml
[project.entry-points."taskbench.providers"]
myadapter = "my_package:MyAdapterFactory"
```

The factory receives `(config: Config, console: Console | None)` and must
return an object satisfying the `TaskProvider` protocol.

## Shell alias update

If you had a shell alias for the old binary:

```bash
# Old
alias cup='clickup'
# or
alias cup='uv run --project /path/to/clickup-tools clickup'

# New
alias tb='taskbench'
# or
alias tb='uv run --project /path/to/clickup-tools taskbench'
```

## Agent instruction update

If your agent instructions reference `clickup` or `cup`, update them to
`taskbench` or `tb`. The CLI will not respond to the old binary names.
