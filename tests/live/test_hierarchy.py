"""Live integration tests for ClickUp hierarchy operations.

These tests verify that space, folder, and list operations work correctly
with the real ClickUp API.
"""

import pytest

from taskbench.core import ClickUpClient, Space, Team
from taskbench.core import List as ClickUpList


@pytest.mark.live
class TestSpaces:
    """Test space operations with real ClickUp API."""

    async def test_get_spaces(self, live_client: ClickUpClient, test_team: Team) -> None:
        """Test getting all spaces for a team."""
        spaces = await live_client.get_spaces(test_team.id)

        assert spaces is not None
        assert len(spaces) > 0

        space = spaces[0]
        assert space.id is not None
        assert space.name is not None
        assert len(space.name) > 0

    async def test_get_space_details(self, live_client: ClickUpClient, test_space: Space) -> None:
        """Test getting specific space details."""
        space = await live_client.get_space(test_space.id)

        assert space is not None
        assert space.id == test_space.id
        assert space.name == test_space.name

    async def test_space_has_expected_properties(self, test_space: Space) -> None:
        """Test that space objects have expected properties."""
        assert hasattr(test_space, "id")
        assert hasattr(test_space, "name")
        assert hasattr(test_space, "private")
        assert isinstance(test_space.id, str)
        assert isinstance(test_space.name, str)


@pytest.mark.live
class TestFolders:
    """Test folder operations with real ClickUp API."""

    async def test_get_folders(self, live_client: ClickUpClient, test_space: Space) -> None:
        """Test getting all folders in a space."""
        folders = await live_client.get_folders(test_space.id)

        assert folders is not None
        # Folders are optional - some spaces may not have any
        assert isinstance(folders, list)

        if folders:
            folder = folders[0]
            assert folder.id is not None
            assert folder.name is not None

    async def test_get_folder_details(self, live_client: ClickUpClient, test_space: Space) -> None:
        """Test getting specific folder details if folders exist."""
        folders = await live_client.get_folders(test_space.id)

        if not folders:
            pytest.skip("No folders in test space")

        folder = await live_client.get_folder(folders[0].id)

        assert folder is not None
        assert folder.id == folders[0].id
        assert folder.name == folders[0].name


@pytest.mark.live
class TestLists:
    """Test list operations with real ClickUp API."""

    async def test_get_folderless_lists(self, live_client: ClickUpClient, test_space: Space) -> None:
        """Test getting folderless lists in a space."""
        lists = await live_client.get_folderless_lists(test_space.id)

        assert lists is not None
        assert isinstance(lists, list)

    async def test_get_lists_from_folder(self, live_client: ClickUpClient, test_space: Space) -> None:
        """Test getting lists from a folder if folders exist."""
        folders = await live_client.get_folders(test_space.id)

        if not folders:
            pytest.skip("No folders in test space")

        lists = await live_client.get_lists(folders[0].id)

        assert lists is not None
        assert isinstance(lists, list)

    async def test_get_list_details(self, live_client: ClickUpClient, test_list: ClickUpList) -> None:
        """Test getting specific list details."""
        list_details = await live_client.get_list(test_list.id)

        assert list_details is not None
        assert list_details.id == test_list.id
        assert list_details.name == test_list.name

    async def test_list_has_expected_properties(self, test_list: ClickUpList) -> None:
        """Test that list objects have expected properties."""
        assert hasattr(test_list, "id")
        assert hasattr(test_list, "name")
        assert isinstance(test_list.id, str)
        assert isinstance(test_list.name, str)


@pytest.mark.live
class TestHierarchyNavigation:
    """Test navigating through the ClickUp hierarchy."""

    async def test_full_hierarchy_traversal(self, live_client: ClickUpClient, test_team: Team) -> None:
        """Test traversing from team -> space -> folder/list."""
        # Get spaces
        spaces = await live_client.get_spaces(test_team.id)
        assert len(spaces) > 0

        # For each space, get folders and folderless lists
        for space in spaces[:2]:  # Limit to first 2 spaces to avoid too many API calls
            folders = await live_client.get_folders(space.id)
            folderless_lists = await live_client.get_folderless_lists(space.id)

            # At least one of these should exist for a useful workspace
            assert isinstance(folders, list)
            assert isinstance(folderless_lists, list)

            # Get lists from folders
            for folder in folders[:2]:  # Limit iterations
                lists = await live_client.get_lists(folder.id)
                assert isinstance(lists, list)

    async def test_space_to_list_path(
        self, live_client: ClickUpClient, test_space: Space, test_list: ClickUpList
    ) -> None:
        """Test that we can find a list within a space."""
        # Get all lists in the space (both folderless and in folders)
        all_lists: list[ClickUpList] = []

        # Get folderless lists
        folderless = await live_client.get_folderless_lists(test_space.id)
        all_lists.extend(folderless)

        # Get lists from folders
        folders = await live_client.get_folders(test_space.id)
        for folder in folders:
            folder_lists = await live_client.get_lists(folder.id)
            all_lists.extend(folder_lists)

        # The test_list should be findable
        list_ids = [lst.id for lst in all_lists]
        assert test_list.id in list_ids
