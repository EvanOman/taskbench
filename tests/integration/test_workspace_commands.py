"""Tests for workspace management commands."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from clickup.cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("clickup.core.config.Path.home", return_value=Path(tmpdir)):
            yield


@pytest.fixture
def sample_teams():
    """Sample teams/workspaces for testing."""
    teams = []
    for i, name in enumerate(["Engineering Team", "Marketing Team", "Sales Team"], 1):
        team = Mock()
        team.id = f"team{i}"
        team.name = name
        team.color = "#000000"  # Add missing color attribute
        team.members = []
        # Fix the closure issue with lambda by using a proper closure
        team.__str__ = lambda name=name: name
        team.__repr__ = lambda name=name: f"Team({name})"
        teams.append(team)
    return teams


@pytest.fixture
def sample_spaces():
    """Sample spaces for testing."""
    spaces = []
    for i, (name, private) in enumerate([("Development", False), ("QA Testing", True), ("Documentation", False)], 1):
        space = Mock()
        space.id = f"space{i}"
        space.name = name
        space.private = private
        space.statuses = []  # Add missing statuses
        space.multiple_assignees = True
        space.features = {}
        space.archived = False
        # Fix the closure issue with lambda by using a proper closure
        space.__str__ = lambda name=name: name
        space.__repr__ = lambda name=name: f"Space({name})"
        spaces.append(space)
    return spaces


@pytest.fixture
def sample_folders():
    """Sample folders for testing."""
    folders = []
    for i, (name, count) in enumerate([("Backend", 15), ("Frontend", 8), ("DevOps", 5)], 1):
        folder = Mock()
        folder.id = f"folder{i}"
        folder.name = name
        folder.task_count = str(count)  # Rich expects strings
        folder.hidden = False
        # Fix the closure issue with lambda by using a proper closure
        folder.__str__ = lambda name=name: name
        folder.__repr__ = lambda name=name: f"Folder({name})"
        folders.append(folder)
    return folders


@pytest.fixture
def sample_members():
    """Sample team members for testing."""
    members = []
    for i, (username, email, role) in enumerate(
        [
            ("john.doe", "john@example.com", "owner"),
            ("jane.smith", "jane@example.com", "admin"),
            ("bob.wilson", "bob@example.com", "member"),
        ],
        1,
    ):
        member = Mock()
        member.id = f"user{i}"
        member.username = username
        member.email = email
        member.role = role
        member.color = "#FF0000"  # Add missing color attribute
        # Fix the closure issue with lambda by using a proper closure
        member.__str__ = lambda username=username: username
        member.__repr__ = lambda username=username: f"Member({username})"
        members.append(member)
    return members


@patch("clickup.cli.commands.workspace.get_client")
def test_workspace_list(mock_get_client, sample_teams):
    """Test listing all workspaces/teams."""
    mock_client = AsyncMock()
    mock_client.get_teams.return_value = sample_teams
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "list"])

    assert result.exit_code == 0
    assert "Engineering Team" in result.output
    assert "Marketing Team" in result.output
    assert "Sales Team" in result.output


@patch("clickup.cli.commands.workspace.get_client")
def test_workspace_spaces(mock_get_client, sample_spaces):
    """Test listing spaces in a workspace."""
    mock_client = AsyncMock()
    mock_client.get_spaces.return_value = sample_spaces
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "spaces", "--workspace-id", "team123"])

    assert result.exit_code == 0
    assert "Development" in result.output
    assert "QA Testing" in result.output
    assert "Documentation" in result.output


@patch("clickup.cli.commands.workspace.get_client")
def test_workspace_folders(mock_get_client, sample_folders):
    """Test listing folders in a space."""
    mock_client = AsyncMock()
    mock_client.get_folders.return_value = sample_folders
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "folders", "--space-id", "space123"])

    assert result.exit_code == 0
    assert "Backend" in result.output
    assert "Frontend" in result.output
    assert "DevOps" in result.output


@patch("clickup.cli.commands.workspace.get_client")
def test_workspace_members(mock_get_client, sample_members):
    """Test listing team members."""
    mock_client = AsyncMock()
    mock_client.get_team_members.return_value = sample_members
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "members", "--workspace-id", "team123"])

    assert result.exit_code == 0
    assert "john.doe" in result.output
    assert "jane.smith" in result.output
    assert "bob.wilson" in result.output
    assert "owner" in result.output
    assert "admin" in result.output
    assert "member" in result.output


def test_workspace_spaces_missing_team_id():
    """Test spaces command without team ID."""
    result = runner.invoke(app, ["workspace", "spaces"])
    assert result.exit_code != 0
    assert "workspace" in result.output.lower()


def test_workspace_folders_missing_space_id():
    """Test folders command without space ID."""
    result = runner.invoke(app, ["workspace", "folders"])
    assert result.exit_code != 0
    assert "space-id" in result.output


def test_workspace_members_missing_team_id():
    """Test members command without team ID."""
    result = runner.invoke(app, ["workspace", "members"])
    assert result.exit_code != 0
    assert "no workspace id" in result.output.lower()


@patch("clickup.cli.commands.workspace.get_client")
async def test_workspace_list_empty(mock_get_client):
    """Test listing workspaces when none exist."""
    mock_client = AsyncMock()
    mock_client.get_teams.return_value = []
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "list"])

    assert result.exit_code == 0
    assert "No workspaces found" in result.stdout or len(result.stdout.strip()) == 0


@patch("clickup.cli.commands.workspace.get_client")
async def test_workspace_spaces_empty(mock_get_client):
    """Test listing spaces when none exist."""
    mock_client = AsyncMock()
    mock_client.get_spaces.return_value = []
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "spaces", "--workspace-id", "team123"])

    assert result.exit_code == 0
    assert "No spaces found" in result.stdout or len(result.stdout.strip()) == 0


@patch("clickup.cli.commands.workspace.get_client")
async def test_workspace_folders_empty(mock_get_client):
    """Test listing folders when none exist."""
    mock_client = AsyncMock()
    mock_client.get_folders.return_value = []
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "folders", "--space-id", "space123"])

    assert result.exit_code == 0
    assert "No folders found" in result.stdout or len(result.stdout.strip()) == 0


@patch("clickup.cli.commands.workspace.get_client")
async def test_workspace_members_empty(mock_get_client):
    """Test listing members when none exist."""
    mock_client = AsyncMock()
    mock_client.get_team_members.return_value = []
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "members", "--workspace-id", "team123"])

    assert result.exit_code == 0
    assert "No members found" in result.stdout or len(result.stdout.strip()) == 0


@patch("clickup.cli.commands.workspace.get_client")
async def test_workspace_spaces_with_privacy_filter(mock_get_client, sample_spaces):
    """Test listing spaces with privacy information displayed."""
    mock_client = AsyncMock()
    mock_client.get_spaces.return_value = sample_spaces
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "spaces", "--team-id", "team123", "--show-private"])

    assert result.exit_code == 0
    assert "Development" in result.stdout
    # Should show privacy indicators
    assert "private" in result.stdout.lower() or "public" in result.stdout.lower()


@patch("clickup.cli.commands.workspace.get_client")
async def test_workspace_folders_with_task_counts(mock_get_client, sample_folders):
    """Test listing folders with task count information."""
    mock_client = AsyncMock()
    mock_client.get_folders.return_value = sample_folders
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "folders", "--space-id", "space123", "--show-counts"])

    assert result.exit_code == 0
    assert "Backend" in result.stdout
    assert "15" in result.stdout  # Task count
    assert "8" in result.stdout  # Task count
    assert "5" in result.stdout  # Task count


@patch("clickup.cli.commands.workspace.get_client")
async def test_workspace_members_with_role_filter(mock_get_client, sample_members):
    """Test listing members filtered by role."""
    mock_client = AsyncMock()
    mock_client.get_team_members.return_value = sample_members
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "members", "--team-id", "team123", "--role", "admin"])

    assert result.exit_code == 0
    # Should filter to only show admins and owners
    assert "jane.smith" in result.stdout or "admin" in result.stdout


def test_workspace_help():
    """Test workspace command help."""
    result = runner.invoke(app, ["workspace", "--help"])
    assert result.exit_code == 0
    assert "list" in result.stdout
    assert "spaces" in result.stdout
    assert "folders" in result.stdout
    assert "members" in result.stdout


@patch("clickup.cli.commands.workspace.get_client")
async def test_workspace_error_handling(mock_get_client):
    """Test workspace command error handling."""
    mock_client = AsyncMock()
    mock_client.get_teams.side_effect = Exception("API Error")
    mock_get_client.return_value.__aenter__.return_value = mock_client

    result = runner.invoke(app, ["workspace", "list"])

    assert result.exit_code != 0
    assert "error" in result.output.lower() or "failed" in result.output.lower()
