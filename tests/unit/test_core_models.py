"""Tests for data models."""

import pytest

from taskbench.core.models import CustomField, PriorityInfo, Space, StatusInfo, Task, Team, User
from taskbench.core.models import List as ClickUpList


def test_task_model() -> None:
    """Test Task model creation and validation."""
    task = Task(
        id="task123",
        name="Test Task",
        description="A test task",
        status=StatusInfo(status="open"),
        priority=PriorityInfo(priority="3"),
        assignees=[],
        date_created="2024-01-01T00:00:00Z",
    )
    assert task.id == "task123"
    assert task.name == "Test Task"
    assert task.description == "A test task"
    assert task.status is not None
    assert task.status.status == "open"
    assert task.priority is not None
    assert task.priority.priority == "3"


def test_task_model_minimal() -> None:
    """Test Task model with minimal required fields."""
    task = Task(id="task123", name="Minimal Task")
    assert task.id == "task123"
    assert task.name == "Minimal Task"
    assert task.description is None
    assert task.assignees == []
    assert task.archived is False


def test_user_model() -> None:
    """Test User model creation."""
    user = User(id=123, username="testuser", email="test@example.com", color="#ff0000")
    assert user.id == 123
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.color == "#ff0000"


def test_team_model() -> None:
    """Test Team model creation."""
    team = Team(id="team123", name="Test Team", color="#00ff00", members=[])
    assert team.id == "team123"
    assert team.name == "Test Team"
    assert team.color == "#00ff00"
    assert team.members == []


def test_space_model() -> None:
    """Test Space model creation."""
    space = Space(
        id="space123",
        name="Test Space",
        private=False,
        multiple_assignees=True,
        statuses=[StatusInfo(status="open"), StatusInfo(status="closed")],
    )
    assert space.id == "space123"
    assert space.name == "Test Space"
    assert space.private is False
    assert space.multiple_assignees is True
    assert len(space.statuses) == 2


def test_list_model() -> None:
    """Test List model creation."""
    clickup_list = ClickUpList(id="list123", name="Test List", orderindex=1, task_count=5, archived=False)
    assert clickup_list.id == "list123"
    assert clickup_list.name == "Test List"
    assert clickup_list.orderindex == 1
    assert clickup_list.task_count == 5
    assert clickup_list.archived is False


def test_custom_field_model() -> None:
    """Test CustomField model creation."""
    field = CustomField(id="field123", name="Priority Level", type="drop_down", value="high")
    assert field.id == "field123"
    assert field.name == "Priority Level"
    assert field.type == "drop_down"
    assert field.value == "high"


def test_task_with_custom_fields() -> None:
    """Test Task model with custom fields."""
    task = Task(
        id="task123",
        name="Task with Custom Fields",
        custom_fields=[
            CustomField(id="field1", name="Sprint", type="text", value="Sprint 23"),
            CustomField(id="field2", name="Story Points", type="number", value=5),
        ],
    )
    assert len(task.custom_fields) == 2
    assert task.custom_fields[0].name == "Sprint"
    assert task.custom_fields[0].value == "Sprint 23"
    assert task.custom_fields[1].name == "Story Points"
    assert task.custom_fields[1].value == 5


def test_model_extra_fields() -> None:
    """Test that models accept extra fields."""
    # Should not raise validation error - pydantic allows extra fields
    task = Task(id="task123", name="Test Task")  # type: ignore[call-arg]
    # Extra fields would be passed via model_validate for dynamic data
    assert task.id == "task123"
    assert task.name == "Test Task"


def test_model_validation() -> None:
    """Test model validation with invalid data."""
    # Missing required field
    with pytest.raises(ValueError):
        Task(name="Task without ID")  # type: ignore[call-arg]  # Missing id field

    # Invalid type
    with pytest.raises(ValueError):
        User(id="not_an_int", username="test", email="test@example.com")  # type: ignore[arg-type]
