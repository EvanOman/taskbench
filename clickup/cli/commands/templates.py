"""Template management commands."""

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from ...core import ClickUpClient, ClickUpError, Config
from ..output import render_error
from ..utils import Progress, SpinnerColumn, TextColumn, run_async

app = typer.Typer(help="Template management")
console = Console()


async def get_client() -> ClickUpClient:
    """Get configured ClickUp client."""
    config = Config()
    if not config.has_credentials():
        console.print(
            "[red]Error: No ClickUp API token configured. Set CLICKUP_API_KEY in your "
            "environment (or .env), or run 'clickup config set-token <token>'.[/red]"
        )
        raise typer.Exit(1)
    return ClickUpClient(config, console)


def get_templates_dir() -> Path:
    """Get templates directory path."""
    config_dir = Path.home() / ".config" / "clickup-toolkit"
    templates_dir = config_dir / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    return templates_dir


def load_built_in_templates() -> dict[str, dict[str, Any]]:
    """Load built-in templates."""
    return {
        "bug_report": {
            "name": "[Bug] {title}",
            "description": """## 🐛 Bug Description
{description}

## 🔄 Steps to Reproduce
1. {step1}
2. {step2}
3. {step3}

## ✅ Expected Behavior
{expected}

## ❌ Actual Behavior
{actual}

## 🌐 Environment
- Browser/OS: {environment}
- Version: {version}

## 📸 Screenshots/Logs
{attachments}

## 🚨 Severity: {severity}""",
            "priority": 2,
            "variables": [
                "title",
                "description",
                "step1",
                "step2",
                "step3",
                "expected",
                "actual",
                "environment",
                "version",
                "attachments",
                "severity",
            ],
        },
        "feature_request": {
            "name": "[Feature] {title}",
            "description": """## 📋 Feature Description
{description}

## 🎯 Problem Statement
{problem}

## 💡 Proposed Solution
{solution}

## 🔄 User Story
As a {user_type}, I want {want} so that {benefit}.

## ✅ Acceptance Criteria
- [ ] {criteria1}
- [ ] {criteria2}
- [ ] {criteria3}

## 🎨 Design/Mockups
{design}

## 📊 Success Metrics
{metrics}""",
            "priority": 3,
            "variables": [
                "title",
                "description",
                "problem",
                "solution",
                "user_type",
                "want",
                "benefit",
                "criteria1",
                "criteria2",
                "criteria3",
                "design",
                "metrics",
            ],
        },
        "sprint_task": {
            "name": "{epic} - {task_name}",
            "description": """## 📝 Task Description
{description}

## 🎯 Objective
{objective}

## ✅ Definition of Done
- [ ] {done1}
- [ ] {done2}
- [ ] {done3}

## 📋 Subtasks
- [ ] {subtask1}
- [ ] {subtask2}
- [ ] {subtask3}

## 🔗 Dependencies
{dependencies}

## 📊 Estimate
{estimate} story points""",
            "priority": 3,
            "variables": [
                "epic",
                "task_name",
                "description",
                "objective",
                "done1",
                "done2",
                "done3",
                "subtask1",
                "subtask2",
                "subtask3",
                "dependencies",
                "estimate",
            ],
        },
        "meeting_notes": {
            "name": "Meeting Notes - {meeting_title} ({date})",
            "description": """## 📅 Meeting Details
- **Date**: {date}
- **Time**: {time}
- **Attendees**: {attendees}
- **Meeting Type**: {meeting_type}

## 🎯 Agenda
{agenda}

## 📋 Discussion Points
{discussion}

## ✅ Action Items
- [ ] {action1} - @{assignee1}
- [ ] {action2} - @{assignee2}
- [ ] {action3} - @{assignee3}

## 📝 Decisions Made
{decisions}

## 🔄 Next Steps
{next_steps}""",
            "priority": 3,
            "variables": [
                "meeting_title",
                "date",
                "time",
                "attendees",
                "meeting_type",
                "agenda",
                "discussion",
                "action1",
                "assignee1",
                "action2",
                "assignee2",
                "action3",
                "assignee3",
                "decisions",
                "next_steps",
            ],
        },
    }


@app.command("list")
def list_templates(
    include_custom: bool = typer.Option(
        False, "--include-custom", help="Include custom templates from ~/.config/clickup/templates."
    ),
) -> None:
    """List all available templates."""
    built_in = load_built_in_templates()
    templates_dir = get_templates_dir()

    table = Table(title="Available Templates", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Variables", style="yellow")

    # Built-in templates
    for name, template in built_in.items():
        table.add_row(name, "Built-in", str(len(template.get("variables", []))))

    # Custom templates
    if templates_dir.exists():
        for template_file in templates_dir.glob("*.json"):
            try:
                with open(template_file, encoding="utf-8") as f:
                    template = json.load(f)
                table.add_row(template_file.stem, "Custom", str(len(template.get("variables", []))))
            except Exception:
                continue

    console.print(table)


@app.command("show")
def show_template(name: str = typer.Argument(..., help="Template name")) -> None:
    """Show template details."""
    built_in = load_built_in_templates()
    templates_dir = get_templates_dir()

    template = None
    template_type = "Unknown"

    # Check built-in templates
    if name in built_in:
        template = built_in[name]
        template_type = "Built-in"
    else:
        # Check custom templates
        template_file = templates_dir / f"{name}.json"
        if template_file.exists():
            try:
                with open(template_file, encoding="utf-8") as f:
                    template = json.load(f)
                template_type = "Custom"
            except Exception as e:
                render_error(f"Error loading template: {e}")
                raise typer.Exit(1) from e

    if not template:
        render_error(f"Template '{name}' not found")
        raise typer.Exit(1)

    # Display template details
    table = Table(title=f"Template: {name} ({template_type})", show_header=False)
    table.add_column("Field", style="cyan", width=15)
    table.add_column("Value", style="white")

    table.add_row("Name Pattern", template.get("name", ""))
    table.add_row("Priority", str(template.get("priority", "")))
    table.add_row("Variables", ", ".join(template.get("variables", [])))

    console.print(table)
    console.print("\n[bold]Description Template:[/bold]")
    console.print(template.get("description", ""))


# Define options as module-level constants to avoid B008 error
_VARIABLES_FILE_OPTION = typer.Option(None, "--variables", help="JSON file with variable values")
_TEMPLATE_FILE_OPTION = typer.Option(None, "--template-file", help="Custom template file")
_VAR_OPTION = typer.Option(None, "--var", help="Variable assignment (key=value)")


@app.command("create")
def create_from_template(
    template_name: str | None = typer.Option(None, "--template", "-t", help="Template name"),
    list_id: str | None = typer.Option(None, "--list-id", "-l", help="List ID to create task in"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="Interactive mode for variables"),
    variables_file: str | None = _VARIABLES_FILE_OPTION,
    template_file: str | None = _TEMPLATE_FILE_OPTION,
    var: list[str] | None = _VAR_OPTION,
) -> None:
    """Create a task from a template."""

    async def _create_from_template() -> None:
        nonlocal var
        if var is None:
            var = []
        config = Config()
        list_id_to_use = list_id or config.get("default_list_id")

        if not list_id_to_use:
            render_error("Error: No list ID provided and no default list configured.")
            console.print("Use --list-id or set a default with 'clickup config set default_list_id <id>'")
            raise typer.Exit(1)

        if not template_name and not template_file:
            render_error("Error: Either template name or template file is required.")
            console.print("Use --template for built-in templates or --template-file for custom templates")
            raise typer.Exit(1)

        built_in = load_built_in_templates()
        templates_dir = get_templates_dir()

        template = None

        # Load template
        if template_file:
            # Load from custom template file
            try:
                with open(template_file, encoding="utf-8") as f:
                    template = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                render_error(f"Error loading template file: {e}")
                raise typer.Exit(1) from e
        elif template_name in built_in:
            template = built_in[template_name]
        else:
            template_file_path = templates_dir / f"{template_name}.json"
            if template_file_path.exists():
                try:
                    with open(template_file_path, encoding="utf-8") as f:
                        template = json.load(f)
                except Exception as e:
                    render_error(f"Error loading template: {e}")
                    raise typer.Exit(1) from e

        if not template:
            render_error(f"Template '{template_name}' not found")
            raise typer.Exit(1)

        # Get variable values
        variables = {}

        # Process --var options first
        for var_assignment in var:
            if "=" not in var_assignment:
                render_error(f"Invalid variable format: {var_assignment}. Use key=value")
                raise typer.Exit(1)
            key, value = var_assignment.split("=", 1)
            variables[key.strip()] = value.strip()

        if variables_file:
            # Load from file (will override --var values)
            try:
                with open(variables_file, encoding="utf-8") as f:
                    file_variables = json.load(f)
                    variables.update(file_variables)
            except Exception as e:
                render_error(f"Error loading variables file: {e}")
                raise typer.Exit(1) from e
        elif interactive and not var:
            # Interactive mode
            console.print(f"[bold]Creating task from template: {template_name}[/bold]")
            console.print("Enter values for template variables (press Enter for empty):\n")

            for var_name in template.get("variables", []):
                value = Prompt.ask(f"[cyan]{var_name}[/cyan]", default="")
                if value:
                    variables[var_name] = value

        # Fill template
        name = template.get("name", "").format(**variables)
        description = template.get("description", "").format(**variables)
        priority = template.get("priority", 3)

        # Create task
        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Creating task from template...", total=None)

                    task_data = {"name": name, "description": description, "priority": priority}

                    task = await client.create_task(list_id_to_use, **task_data)

                console.print(f"✅ Created task from template: {task.name}")
                console.print(f"🆔 Task ID: {task.id}")
                if task.url:
                    console.print(f"🔗 URL: {task.url}")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e
        except Exception as e:
            render_error(f"Error: {e}")
            raise typer.Exit(1) from e

    run_async(_create_from_template())


@app.command("save")
def save_template(
    name: str = typer.Argument(..., help="Template name"),
    task_id: str = typer.Option(..., "--from-task", help="Create template from existing task"),
    name_pattern: str | None = typer.Option(
        None,
        "--name-pattern",
        help="Template name pattern (use {variable} syntax). Defaults to the source task name.",
    ),
    description_pattern: str | None = typer.Option(
        None,
        "--description-pattern",
        help="Template description pattern (use {variable} syntax). Defaults to the source task description.",
    ),
) -> None:
    """Save a task as a template.

    Non-interactive: pass --name-pattern and --description-pattern to control
    the saved template. Variables are extracted from any ``{variable}``
    placeholders in either pattern. Without flags, the source task's literal
    name/description are used as the patterns (no variables).
    """

    async def _save_template() -> None:
        try:
            async with await get_client() as client:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Fetching task...", total=None)
                    task = await client.get_task(task_id)

                template: dict[str, Any] = {
                    "name": task.name,
                    "description": task.description or "",
                    "priority": int(task.priority.priority) if task.priority and task.priority.priority else 3,
                    "variables": [],
                }

                template_name = name_pattern if name_pattern is not None else task.name
                template_desc = description_pattern if description_pattern is not None else (task.description or "")
                template["name"] = template_name
                template["description"] = template_desc

                # Extract variables from patterns
                import re

                variables = set()
                for text in [template_name, template_desc]:
                    variables.update(re.findall(r"\{(\w+)\}", text))

                template["variables"] = sorted(variables)
                variables_list: list[str] = template["variables"]

                # Save template
                templates_dir = get_templates_dir()
                template_file = templates_dir / f"{name}.json"

                with open(template_file, "w", encoding="utf-8") as f:
                    json.dump(template, f, indent=2, ensure_ascii=False)

                console.print(f"✅ Saved template: {name}")
                console.print(f"📁 Location: {template_file}")
                console.print(f"🔤 Variables: {', '.join(variables_list)}")

        except ClickUpError as e:
            render_error(f"ClickUp API Error: {e}")
            raise typer.Exit(1) from e
        except Exception as e:
            render_error(f"Error: {e}")
            raise typer.Exit(1) from e

    run_async(_save_template())
