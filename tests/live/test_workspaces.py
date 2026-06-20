"""Live integration tests for workspace/team operations.

These tests verify that workspace operations work correctly with the real ClickUp API.
"""

import pytest

from taskbench.core import ClickUpClient, Team


@pytest.mark.live
class TestWorkspaces:
    """Test workspace/team operations with real ClickUp API."""

    async def test_get_teams(self, live_client: ClickUpClient) -> None:
        """Test getting all teams/workspaces."""
        teams = await live_client.get_teams()

        assert teams is not None
        assert len(teams) > 0

        team = teams[0]
        assert team.id is not None
        assert team.name is not None
        assert len(team.name) > 0

    async def test_get_team_details(self, live_client: ClickUpClient, test_team: Team) -> None:
        """Test getting specific team details."""
        team = await live_client.get_team(test_team.id)

        assert team is not None
        assert team.id == test_team.id
        assert team.name == test_team.name

    async def test_get_team_members(self, live_client: ClickUpClient, test_team: Team) -> None:
        """Test getting team members."""
        members = await live_client.get_team_members(test_team.id)

        assert members is not None
        # Should have at least the current user
        assert len(members) >= 1

        member = members[0]
        assert member.id is not None
        assert member.username is not None

    async def test_team_has_expected_properties(self, test_team: Team) -> None:
        """Test that team objects have expected properties."""
        assert hasattr(test_team, "id")
        assert hasattr(test_team, "name")
        # Team ID should be a string (ClickUp uses string IDs)
        assert isinstance(test_team.id, str)
        assert len(test_team.id) > 0
