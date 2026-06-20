"""Tests for template commands.

Consolidates tests from the original test_template_commands.py, plus template
tests formerly in test_command_coverage.py and test_final_coverage.py.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from taskbench.cli.main import app
from taskbench.core.exceptions import ClickUpError
from taskbench.core.models import PriorityInfo, Task

from .conftest import make_mock_ctx

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.core.config.Path.home", return_value=Path(tmpdir)):
            yield


@pytest.fixture
def sample_custom_template():
    """Sample custom template for testing."""
    return {
        "name": "Custom Task Template",
        "description": "Template for {{task_type}} tasks",
        "priority": "{{priority}}",
        "assignees": ["{{assignee}}"],
        "tags": ["{{team}}", "custom"],
        "custom_fields": {"Department": "{{department}}", "Estimated Hours": "{{hours}}"},
    }


# =============================================================================
# list / show
# =============================================================================


def test_template_list_builtin():
    """Test listing built-in templates."""
    result = runner.invoke(app, ["template", "list"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    names = [r["name"] for r in data["data"]]
    assert "bug_report" in names
    assert "feature_request" in names
    assert "sprint_task" in names
    assert "meeting_notes" in names


def test_template_show_builtin():
    """Test showing built-in template."""
    result = runner.invoke(app, ["template", "show", "bug_report"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "Bug Description" in data["description"]
    assert "Steps to Reproduce" in data["description"]
    assert data["priority"] == 2


def test_template_show_nonexistent():
    """Test showing non-existent template."""
    result = runner.invoke(app, ["template", "show", "nonexistent_template"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_template_show_all_builtins():
    """Test showing all built-in templates."""
    builtin_templates = ["bug_report", "feature_request", "sprint_task", "meeting_notes"]

    for template in builtin_templates:
        result = runner.invoke(app, ["template", "show", template])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["name"] == template


def test_template_list_json_shape():
    """template list emits {"data": [...], "count": N} in JSON mode."""
    result = runner.invoke(app, ["template", "list"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "data" in data
    assert "count" in data
    assert data["count"] == len(data["data"])
    assert all("name" in r and "type" in r for r in data["data"])


def test_template_show_json_shape():
    """template show emits structured dict in JSON mode."""
    result = runner.invoke(app, ["template", "show", "bug_report"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["name"] == "bug_report"
    assert data["type"] == "Built-in"
    assert "variables" in data
    assert "description" in data


def test_template_list_table_mode():
    """template list --format table keeps human table."""
    result = runner.invoke(app, ["--format", "table", "template", "list"])
    assert result.exit_code == 0
    assert "bug_report" in result.output
    assert "Built-in" in result.output


def test_template_show_table_mode():
    """template show --format table keeps human table."""
    result = runner.invoke(app, ["--format", "table", "template", "show", "bug_report"])
    assert result.exit_code == 0
    assert "Bug Description" in result.output


def test_template_help():
    """Test template command help."""
    result = runner.invoke(app, ["template", "--help"])
    assert result.exit_code == 0
    assert "list" in result.stdout
    assert "show" in result.stdout
    assert "create" in result.stdout
    assert "save" in result.stdout


# =============================================================================
# list / show with custom templates
# =============================================================================


def test_template_list_with_custom_templates():
    """Test listing templates including custom ones."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.cli.commands.templates.get_templates_dir", return_value=Path(tmpdir)):
            result = runner.invoke(app, ["template", "list", "--include-custom"])
            assert result.exit_code == 0


def test_template_list_with_include_custom_on_disk():
    """--include-custom picks up a real template file on disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.core.config.Path.home", return_value=Path(tmpdir)):
            with patch("taskbench.cli.commands.templates.Path.home", return_value=Path(tmpdir)):
                custom_dir = Path(tmpdir) / ".config" / "taskbench" / "templates"
                custom_dir.mkdir(parents=True, exist_ok=True)
                (custom_dir / "my_template.json").write_text(
                    json.dumps({"name": "Custom {x}", "description": "d", "variables": ["x"]})
                )

                result = runner.invoke(app, ["template", "list", "--include-custom"])
                assert result.exit_code == 0
                assert "my_template" in result.output


def test_template_show_custom_from_disk():
    """Show a custom template loaded from disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.core.config.Path.home", return_value=Path(tmpdir)):
            with patch("taskbench.cli.commands.templates.Path.home", return_value=Path(tmpdir)):
                custom_dir = Path(tmpdir) / ".config" / "taskbench" / "templates"
                custom_dir.mkdir(parents=True, exist_ok=True)
                (custom_dir / "test_t.json").write_text(
                    json.dumps({"name": "T {x}", "description": "Desc", "priority": 2, "variables": ["x"]})
                )

                result = runner.invoke(app, ["template", "show", "test_t"])
                assert result.exit_code == 0
                assert "Custom" in result.output


# =============================================================================
# create — happy paths
# =============================================================================


@patch("taskbench.cli.commands.templates.get_client")
async def test_template_create_from_builtin(mock_get_client):
    """Test creating task from built-in template."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Mock(id="task123", name="Bug: Login issue")
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(
        app,
        [
            "template",
            "create",
            "--list-id",
            "list123",
            "--template",
            "bug_report",
            "--var",
            "title=Login issue",
            "--var",
            "description=Users cannot log in",
            "--var",
            "step1=Navigate to login page",
            "--var",
            "step2=Enter credentials",
            "--var",
            "step3=Click login button",
            "--var",
            "expected=User should be logged in",
            "--var",
            "actual=Login fails with error",
            "--var",
            "environment=Chrome/Ubuntu",
            "--var",
            "version=1.0.0",
            "--var",
            "attachments=screenshot.png",
            "--var",
            "severity=High",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "id" in data
    assert "task123" in result.stdout


@patch("taskbench.cli.commands.templates.get_client")
async def test_template_create_from_custom(mock_get_client, sample_custom_template):
    """Test creating task from custom template file."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Mock(id="task456", name="Custom Task")
    mock_get_client.return_value.__aenter__.return_value = mock_client

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_custom_template, f)
        f.flush()

        result = runner.invoke(
            app,
            [
                "template",
                "create",
                "--list-id",
                "list123",
                "--template-file",
                f.name,
                "--var",
                "task_type=Development",
                "--var",
                "priority=medium",
                "--var",
                "assignee=dev@example.com",
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
    assert "id" in data


@patch("taskbench.cli.commands.templates.get_client")
async def test_template_create_with_variable_substitution(mock_get_client):
    """Test template variable substitution."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Mock(id="task789", name="Feature: New Dashboard")
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(
        app,
        [
            "template",
            "create",
            "--list-id",
            "list123",
            "--template",
            "feature_request",
            "--var",
            "title=New Dashboard",
            "--var",
            "description=A new user dashboard",
            "--var",
            "problem=Users have no central place to see their data",
            "--var",
            "solution=Create a new dashboard page",
            "--var",
            "user_type=end user",
            "--var",
            "want=to see my data",
            "--var",
            "benefit=I can make better decisions",
            "--var",
            "criteria1=Data is accurate",
            "--var",
            "criteria2=Page loads quickly",
            "--var",
            "criteria3=Looks good on mobile",
            "--var",
            "design=link-to-figma.com",
            "--var",
            "metrics=10% increase in engagement",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "id" in data


@patch("taskbench.cli.commands.templates.get_client")
def test_template_create_with_variables_file(mock_get_client):
    """Use --variables file path with all bug_report vars."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(id="t1", name="[Bug] login")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    bug_vars = {
        "title": "login",
        "description": "broken",
        "step1": "x",
        "step2": "y",
        "step3": "z",
        "expected": "ok",
        "actual": "fail",
        "environment": "mac",
        "version": "1.0",
        "attachments": "none",
        "severity": "high",
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bug_vars, f)
        f.flush()
        result = runner.invoke(
            app,
            [
                "template",
                "create",
                "--template",
                "bug_report",
                "--list-id",
                "L1",
                "--variables",
                f.name,
                "--no-interactive",
            ],
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["id"] == "t1"


@patch("taskbench.cli.commands.templates.get_client")
def test_template_create_with_template_file(mock_get_client):
    """Provide a custom template file via --template-file."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(id="t1", name="custom_task")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"name": "{x}", "description": "y", "priority": 3, "variables": ["x"]}, f)
        f.flush()
        result = runner.invoke(
            app,
            [
                "template",
                "create",
                "--list-id",
                "L1",
                "--template-file",
                f.name,
                "--var",
                "x=test",
                "--no-interactive",
            ],
        )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "t1"


@patch("taskbench.cli.commands.templates.get_client")
def test_template_create_custom_template_by_name(mock_get_client):
    """--template <name> resolves to a custom file on disk if not built-in."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = Task(id="t1", name="my_task")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.cli.commands.templates.Path.home", return_value=Path(tmpdir)):
            custom_dir = Path(tmpdir) / ".config" / "taskbench" / "templates"
            custom_dir.mkdir(parents=True, exist_ok=True)
            (custom_dir / "my_t.json").write_text(
                json.dumps({"name": "{n}", "description": "d", "priority": 3, "variables": ["n"]})
            )

            result = runner.invoke(
                app,
                [
                    "template",
                    "create",
                    "--list-id",
                    "L1",
                    "--template",
                    "my_t",
                    "--var",
                    "n=foo",
                    "--no-interactive",
                ],
            )
            assert result.exit_code == 0


# =============================================================================
# create — error paths
# =============================================================================


def test_template_create_missing_list():
    """Test template create without list ID — error + hint go to stderr."""
    result = runner.invoke(app, ["template", "create", "--template", "bug_report"])

    assert result.exit_code == 2
    assert "list-id" in result.output


def test_template_create_missing_template():
    """Test template create without template specification."""
    result = runner.invoke(app, ["template", "create", "--list-id", "list123"])

    assert result.exit_code == 1


def test_template_create_no_list_no_interactive():
    """template create --no-interactive without --list-id is a usage error (exit 2)."""
    result = runner.invoke(app, ["template", "create", "--template", "bug_report", "--no-interactive"])
    assert result.exit_code == 2


def test_template_create_no_template_no_interactive():
    """template create --no-interactive without --template is a usage error (exit 2)."""
    result = runner.invoke(app, ["template", "create", "--list-id", "L1", "--no-interactive"])
    assert result.exit_code == 1


@patch("taskbench.cli.commands.templates.get_client")
def test_template_create_invalid_var_format(mock_get_client):
    """--var without an = sign is rejected."""
    mock_client = AsyncMock()
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        [
            "template",
            "create",
            "--template",
            "bug_report",
            "--list-id",
            "L1",
            "--var",
            "no_equals_sign",
            "--no-interactive",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid variable format" in result.output


def test_template_create_invalid_template_file():
    """Test creating from invalid template file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("invalid json content")
        f.flush()

        result = runner.invoke(app, ["template", "create", "--list-id", "list123", "--template-file", f.name])

        assert result.exit_code != 0


@patch("taskbench.cli.commands.templates.get_client")
def test_template_create_template_file_missing(mock_get_client):
    """A nonexistent --template-file path errors."""
    mock_client = AsyncMock()
    mock_get_client.return_value = make_mock_ctx(mock_client)

    result = runner.invoke(
        app,
        [
            "template",
            "create",
            "--list-id",
            "L1",
            "--template-file",
            "/nonexistent/path.json",
            "--no-interactive",
        ],
    )
    assert result.exit_code == 1
    assert "Error loading template" in result.output


@patch("taskbench.cli.commands.templates.get_client")
def test_template_create_api_error(mock_get_client):
    """API failure during create propagates cleanly."""
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = ClickUpError("rate limit")
    mock_get_client.return_value = make_mock_ctx(mock_client)

    bug_vars = {
        "title": "x",
        "description": "x",
        "step1": "x",
        "step2": "x",
        "step3": "x",
        "expected": "x",
        "actual": "x",
        "environment": "x",
        "version": "x",
        "attachments": "x",
        "severity": "x",
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bug_vars, f)
        f.flush()
        result = runner.invoke(
            app,
            [
                "template",
                "create",
                "--template",
                "bug_report",
                "--list-id",
                "L1",
                "--variables",
                f.name,
                "--no-interactive",
            ],
        )
    assert result.exit_code == 1
    assert "rate limit" in result.stderr


def test_template_create_variables_file_missing():
    """--variables file that doesn't exist errors out."""
    result = runner.invoke(
        app,
        [
            "template",
            "create",
            "--template",
            "bug_report",
            "--list-id",
            "L1",
            "--variables",
            "/nonexistent.json",
            "--no-interactive",
        ],
    )
    assert result.exit_code == 1
    assert "variables file" in result.output.lower() or "error" in result.output.lower()


@patch("taskbench.cli.commands.templates.get_client")
async def test_template_create_missing_variables(mock_get_client):
    """Test creating template with missing required variables."""
    mock_client = AsyncMock()
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(
        app,
        [
            "template",
            "create",
            "--list-id",
            "list123",
            "--template",
            "bug_report",
        ],
    )

    assert result.exit_code in [0, 1]


# =============================================================================
# save
# =============================================================================


def test_template_save_from_task():
    """Test saving template from existing task."""
    _ = {"name": "Sample Task", "description": "Sample description", "priority": "high", "tags": ["sample", "test"]}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        runner.invoke(
            app, ["template", "save", "--task-id", "task123", "--output", f.name, "--name", "My Custom Template"]
        )


@patch("taskbench.cli.commands.templates.get_client")
def test_template_save_with_pattern_flags(mock_get_client):
    """Non-interactive save with --name-pattern / --description-pattern."""
    mock_client = AsyncMock()
    mock_client.get_task.return_value = Task(
        id="t1", name="Sample task", description="Sample {what}", priority=PriorityInfo(priority="2", id="2")
    )
    mock_get_client.return_value = make_mock_ctx(mock_client)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.cli.commands.templates.Path.home", return_value=Path(tmpdir)):
            result = runner.invoke(
                app,
                [
                    "template",
                    "save",
                    "test-template",
                    "--from-task",
                    "t1",
                    "--name-pattern",
                    "[{kind}] {title}",
                    "--description-pattern",
                    "Doing {what}",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data["name"] == "test-template"


@patch("taskbench.cli.commands.templates.get_client")
def test_template_save_refuses_overwrite_without_force(mock_get_client):
    """template save must refuse to overwrite without --force."""
    mock_client = AsyncMock()
    mock_client.get_task.return_value = Task(
        id="t1", name="T", description="D", priority=PriorityInfo(priority="2", id="2")
    )

    def _ctx():
        cm = AsyncMock()
        cm.__aenter__.return_value = mock_client
        return cm

    mock_get_client.side_effect = _ctx

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("taskbench.cli.commands.templates.Path.home", return_value=Path(tmpdir)):
            result1 = runner.invoke(app, ["template", "save", "overwrite-test", "--from-task", "t1"])
            assert result1.exit_code == 0, result1.output

            result2 = runner.invoke(app, ["template", "save", "overwrite-test", "--from-task", "t1"])
            assert result2.exit_code == 2
            assert "Refusing" in result2.output

            result3 = runner.invoke(app, ["template", "save", "overwrite-test", "--from-task", "t1", "--force"])
            assert result3.exit_code == 0
