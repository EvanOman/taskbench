"""Taskbench - An agent-first task CLI, backend-pluggable."""

__version__ = "1.0.0"

# Import main modules
from . import cli, core

__all__ = ["core", "cli"]
