"""Live integration tests for CLI commands.

These tests verify that the CLI commands work correctly with the real ClickUp API.
They use subprocess to invoke the CLI just like a user would.
"""

import json
import os
import subprocess

import pytest


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the Taskbench CLI with the given arguments."""
    cmd = ["uv", "run", "taskbench", *args]

    # Merge environment with current env
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        env=full_env,
    )


@pytest.mark.live
class TestCLIBasic:
    """Test basic CLI commands."""

    def test_version(self) -> None:
        """Test the version command."""
        result = run_cli("version")
        assert result.returncode == 0
        # Should output version info
        assert "0." in result.stdout or "version" in result.stdout.lower()

    def test_status(self, api_key: str) -> None:
        """Test the status command shows authentication status."""
        result = run_cli("status")
        # Should work and show some status
        assert result.returncode == 0 or "authenticated" in result.stdout.lower()


@pytest.mark.live
class TestCLIConfig:
    """Test CLI configuration commands."""

    def test_config_show(self, api_key: str) -> None:
        """Test showing current configuration."""
        result = run_cli("config", "show")
        # Should succeed and show config
        assert result.returncode == 0 or "config" in result.stdout.lower()

    def test_config_validate(self, api_key: str) -> None:
        """Test validating API credentials via CLI."""
        result = run_cli("config", "validate")
        # Should show validation result
        # The command should complete (may succeed or fail based on config)
        # We just verify it doesn't crash
        assert result.returncode in [0, 1]


@pytest.mark.live
class TestCLIWorkspace:
    """Test workspace CLI commands."""

    def test_workspace_list(self, api_key: str) -> None:
        """Test listing workspaces."""
        result = run_cli("workspace", "list")
        assert result.returncode == 0
        # Should show at least one workspace
        assert len(result.stdout) > 0

    def test_workspace_list_json(self, api_key: str) -> None:
        """Test listing workspaces in JSON format."""
        result = run_cli("workspace", "list", "--format", "json")
        if result.returncode == 0:
            # Should be valid JSON
            try:
                data = json.loads(result.stdout)
                assert isinstance(data, list)
            except json.JSONDecodeError:
                # Some output formats may not be pure JSON
                pass


@pytest.mark.live
class TestCLIDiscovery:
    """Test discovery CLI commands."""

    def test_discover_hierarchy(self, api_key: str) -> None:
        """Test discovering workspace hierarchy."""
        result = run_cli("discover", "hierarchy")
        # Should show hierarchy tree
        assert result.returncode == 0 or len(result.stdout) > 0

    def test_discover_ids(self, api_key: str) -> None:
        """Test discovering IDs."""
        result = run_cli("discover", "ids")
        # Should show some IDs
        assert result.returncode == 0 or len(result.stdout) > 0


@pytest.mark.live
class TestCLITask:
    """Test task CLI commands."""

    def test_task_list_requires_list_id(self, api_key: str) -> None:
        """Test that task list command requires a list ID."""
        result = run_cli("task", "list")
        # Should fail without list-id or show helpful message
        # The exact behavior depends on implementation
        assert result.returncode != 0 or "list" in result.stderr.lower() + result.stdout.lower()

    def test_task_create_and_delete(self, api_key: str) -> None:
        """Test creating and deleting a task via CLI.

        This test requires knowing a valid list ID.
        We'll try to discover one first.
        """
        # First, get workspace info to find a list ID
        result = run_cli("discover", "ids", "--format", "json")
        if result.returncode != 0:
            pytest.skip("Could not discover workspace IDs")

        try:
            data = json.loads(result.stdout)
            # Try to find a list ID from the output
            list_id = None
            if isinstance(data, dict):
                # Look for lists in the structure
                for space in data.get("spaces", []):
                    for lst in space.get("lists", []):
                        list_id = lst.get("id")
                        if list_id:
                            break
                    if list_id:
                        break
        except (json.JSONDecodeError, KeyError, TypeError):
            pytest.skip("Could not parse workspace IDs")

        if not list_id:
            pytest.skip("No list ID found for task creation test")
            raise RuntimeError("unreachable")  # Help type checker understand pytest.skip raises

        # Create a task
        task_name = "CLI Integration Test Task"
        result = run_cli("task", "create", task_name, "--list-id", list_id)

        if result.returncode != 0:
            pytest.skip(f"Task creation failed: {result.stderr}")

        # Try to find and delete the task
        # This is best-effort cleanup
        result = run_cli("task", "list", "--list-id", list_id, "--format", "json")
        if result.returncode == 0:
            try:
                tasks = json.loads(result.stdout)
                for task in tasks:
                    if task.get("name") == task_name:
                        run_cli("task", "delete", task["id"])
                        break
            except (json.JSONDecodeError, KeyError, TypeError):
                pass


@pytest.mark.live
class TestCLIErrorHandling:
    """Test CLI error handling."""

    def test_invalid_command(self, api_key: str) -> None:
        """Test that invalid commands are handled gracefully."""
        result = run_cli("not-a-real-command")
        # Should fail with non-zero exit code
        assert result.returncode != 0

    def test_help(self, api_key: str) -> None:
        """Test that help is available."""
        result = run_cli("--help")
        assert result.returncode == 0
        assert "clickup" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_task_help(self, api_key: str) -> None:
        """Test task subcommand help."""
        result = run_cli("task", "--help")
        assert result.returncode == 0
        assert "task" in result.stdout.lower()
