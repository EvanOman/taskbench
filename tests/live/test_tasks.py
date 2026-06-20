"""Live integration tests for task CRUD operations.

These tests verify that task creation, reading, updating, and deletion
work correctly with the real ClickUp API.
"""

import pytest

from taskbench.core import ClickUpClient, Task, Team
from taskbench.core import List as ClickUpList
from taskbench.core.exceptions import NotFoundError


@pytest.mark.live
class TestTaskRead:
    """Test task reading operations with real ClickUp API."""

    async def test_get_tasks(self, live_client: ClickUpClient, test_list: ClickUpList) -> None:
        """Test getting tasks from a list."""
        tasks = await live_client.get_tasks(test_list.id)

        assert tasks is not None
        assert isinstance(tasks, list)

    async def test_get_task_details(self, live_client: ClickUpClient, test_task: Task) -> None:
        """Test getting specific task details."""
        task = await live_client.get_task(test_task.id)

        assert task is not None
        assert task.id == test_task.id
        assert task.name == test_task.name

    async def test_task_has_expected_properties(self, test_task: Task) -> None:
        """Test that task objects have expected properties."""
        assert hasattr(test_task, "id")
        assert hasattr(test_task, "name")
        assert hasattr(test_task, "status")
        assert hasattr(test_task, "url")
        assert isinstance(test_task.id, str)
        assert isinstance(test_task.name, str)


@pytest.mark.live
class TestTaskCreate:
    """Test task creation with real ClickUp API."""

    async def test_create_task_minimal(self, live_client: ClickUpClient, test_list: ClickUpList) -> None:
        """Test creating a task with minimal fields."""
        task = await live_client.create_task(
            test_list.id,
            name="Test Task - Minimal",
        )

        try:
            assert task is not None
            assert task.id is not None
            assert task.name == "Test Task - Minimal"
        finally:
            # Cleanup
            await live_client.delete_task(task.id)

    async def test_create_task_with_description(self, live_client: ClickUpClient, test_list: ClickUpList) -> None:
        """Test creating a task with a description."""
        task = await live_client.create_task(
            test_list.id,
            name="Test Task - With Description",
            description="This is a test description for the integration test.",
        )

        try:
            assert task is not None
            assert task.name == "Test Task - With Description"
            # Fetch full task to verify description
            full_task = await live_client.get_task(task.id)
            assert full_task.description is not None
            assert "test description" in full_task.description.lower()
        finally:
            await live_client.delete_task(task.id)

    async def test_create_task_with_priority(self, live_client: ClickUpClient, test_list: ClickUpList) -> None:
        """Test creating a task with a priority."""
        task = await live_client.create_task(
            test_list.id,
            name="Test Task - High Priority",
            priority=2,  # High priority
        )

        try:
            assert task is not None
            assert task.name == "Test Task - High Priority"
        finally:
            await live_client.delete_task(task.id)


@pytest.mark.live
class TestTaskUpdate:
    """Test task update operations with real ClickUp API."""

    async def test_update_task_name(self, live_client: ClickUpClient, test_list: ClickUpList) -> None:
        """Test updating a task's name."""
        # Create a task
        task = await live_client.create_task(
            test_list.id,
            name="Original Name",
        )

        try:
            # Update the name
            updated_task = await live_client.update_task(task.id, name="Updated Name")

            assert updated_task is not None
            assert updated_task.name == "Updated Name"
        finally:
            await live_client.delete_task(task.id)

    async def test_update_task_description(self, live_client: ClickUpClient, test_list: ClickUpList) -> None:
        """Test updating a task's description."""
        task = await live_client.create_task(
            test_list.id,
            name="Task to Update Description",
            description="Original description",
        )

        try:
            updated_task = await live_client.update_task(task.id, description="New updated description")

            assert updated_task is not None
            # Verify by fetching
            fetched = await live_client.get_task(task.id)
            assert fetched.description is not None
            assert "new updated description" in fetched.description.lower()
        finally:
            await live_client.delete_task(task.id)

    async def test_update_task_priority(self, live_client: ClickUpClient, test_list: ClickUpList) -> None:
        """Test updating a task's priority."""
        task = await live_client.create_task(
            test_list.id,
            name="Task to Update Priority",
            priority=4,  # Low priority
        )

        try:
            # Update to high priority
            updated_task = await live_client.update_task(task.id, priority=1)  # Urgent

            assert updated_task is not None
        finally:
            await live_client.delete_task(task.id)


@pytest.mark.live
class TestTaskDelete:
    """Test task deletion with real ClickUp API."""

    async def test_delete_task(self, live_client: ClickUpClient, test_list: ClickUpList) -> None:
        """Test deleting a task."""
        # Create a task to delete
        task = await live_client.create_task(
            test_list.id,
            name="Task to Delete",
        )

        # Verify it exists
        fetched = await live_client.get_task(task.id)
        assert fetched is not None

        # Delete it
        result = await live_client.delete_task(task.id)
        assert result is True

        # Verify it's gone
        with pytest.raises(NotFoundError):
            await live_client.get_task(task.id)


@pytest.mark.live
class TestTaskSearch:
    """Test task search operations with real ClickUp API."""

    async def test_search_tasks(self, live_client: ClickUpClient, test_team: Team, test_list: ClickUpList) -> None:
        """Test searching for tasks."""
        # Create a task with a unique name
        unique_name = "UniqueSearchTestTask12345"
        task = await live_client.create_task(
            test_list.id,
            name=unique_name,
        )

        try:
            # Search for the task
            results = await live_client.search_tasks(test_team.id, unique_name)

            assert results is not None
            assert isinstance(results, list)
            # The task should be in the results
            task_ids = [t.id for t in results]
            assert task.id in task_ids
        finally:
            await live_client.delete_task(task.id)


@pytest.mark.live
class TestTaskComments:
    """Test task comment operations with real ClickUp API."""

    async def test_get_task_comments(self, live_client: ClickUpClient, test_task: Task) -> None:
        """Test getting comments from a task."""
        comments = await live_client.get_task_comments(test_task.id)

        assert comments is not None
        assert isinstance(comments, list)

    async def test_create_comment(self, live_client: ClickUpClient, test_task: Task) -> None:
        """Test creating a comment on a task."""
        comment = await live_client.create_comment(
            test_task.id,
            comment_text="This is a test comment from integration tests.",
        )

        assert comment is not None
        assert comment.id is not None

        # Verify comment appears in list
        comments = await live_client.get_task_comments(test_task.id)
        comment_ids = [c.id for c in comments]
        assert comment.id in comment_ids
