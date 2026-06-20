"""Typed parameter shapes for TaskProvider methods.

These TypedDicts document the keyword arguments accepted by the three
main write/query operations on tasks.  They are the canonical reference
for what keys adapters should read from ``**kwargs`` / ``**filters`` /
``**updates``.

Usage
-----
Adapters and CLI call sites can import these for documentation and
IDE auto-complete.  The ``TaskProvider`` protocol docstrings reference
them by name; the protocol signatures themselves remain ``**kwargs: Any``
because ``Unpack`` on ``Protocol`` methods requires all implementers
to adopt the same typed signature, which creates a cascade of changes
across adapters for marginal type-safety gain.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict


class TaskCreateParams(TypedDict, total=False):
    """Keyword arguments for ``TaskProvider.create_task``.

    All fields are optional; the only required positional args on the
    method are ``list_id`` and ``name``.
    """

    description: NotRequired[str | None]
    status: NotRequired[str]
    priority: NotRequired[int | None]
    due_date: NotRequired[str | None]
    assignees: NotRequired[list[str]]


class TaskUpdateParams(TypedDict, total=False):
    """Keyword arguments for ``TaskProvider.update_task``.

    Only fields present in the dict are applied (modify-if-passed
    semantics — see AGENT.md, architecture decision 3).
    """

    name: NotRequired[str]
    description: NotRequired[str | None]
    status: NotRequired[str]
    priority: NotRequired[int | None]
    due_date: NotRequired[str | None]
    assignees: NotRequired[list[str]]
    archived: NotRequired[bool]


class TaskFilterParams(TypedDict, total=False):
    """Keyword arguments for ``TaskProvider.get_tasks`` and ``search_tasks``.

    Servers MUST honor ``statuses`` and ``include_closed``; the date
    filters SHOULD be honored but the CLI treats server-side filtering
    as best-effort (it re-filters client-side).
    """

    statuses: NotRequired[list[str]]
    include_closed: NotRequired[bool]
    date_updated_gt: NotRequired[int | str]
    date_updated_lt: NotRequired[int | str]
    date_created_gt: NotRequired[int | str]
    date_created_lt: NotRequired[int | str]
    assignees: NotRequired[list[str]]
    page: NotRequired[int]
    order_by: NotRequired[str]
    reverse: NotRequired[bool]
