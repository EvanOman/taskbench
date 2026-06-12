"""Pure filter, sort, and validation helpers for task commands.

Extracted from ``clickup.cli.commands.task`` so the helpers can be tested
and reused without pulling in the full Typer command tree.

All functions are the module's public API -- no leading underscores.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from .shared import usage_error

RELATIVE_TIME_RE = re.compile(r"^(?P<count>\d+)(?P<unit>[dhw])$")


def epoch_ms(value: str) -> int:
    """Parse an epoch-ms, ISO date/datetime, or relative duration into epoch milliseconds."""
    trimmed = value.strip()
    if not trimmed:
        usage_error("Error: date filter value is empty.")
    if trimmed.isdigit():
        return int(trimmed)

    relative = RELATIVE_TIME_RE.match(trimmed.lower())
    if relative:
        count = int(relative.group("count"))
        unit = relative.group("unit")
        delta = {
            "d": timedelta(days=count),
            "h": timedelta(hours=count),
            "w": timedelta(weeks=count),
        }[unit]
        return int((datetime.now(tz=UTC) - delta).timestamp() * 1000)

    try:
        if len(trimmed) == 10 and trimmed[4] == "-" and trimmed[7] == "-":
            dt = datetime.fromisoformat(trimmed).replace(tzinfo=UTC)
        else:
            dt = datetime.fromisoformat(trimmed.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            else:
                dt = dt.astimezone(UTC)
    except ValueError as exc:
        _ = exc
        usage_error(
            "Error: date filters accept epoch milliseconds, YYYY-MM-DD, ISO datetime, or relative values like 7d."
        )
    return int(dt.timestamp() * 1000)


def set_exclusive_date_filter(filters: dict[str, Any], key: str, values: list[tuple[str, str | None]]) -> None:
    """Set a ClickUp date filter when exactly one of several aliases is provided."""
    provided = [(name, value) for name, value in values if value is not None]
    if len(provided) > 1:
        names = ", ".join(name for name, _value in provided)
        usage_error(f"Error: conflicting date filters for {key}: {names}.")
    if provided:
        filters[key] = epoch_ms(provided[0][1])


def annotate_source_list(task: Any, list_id: str) -> Any:
    """Attach source list metadata when a fanout query merges multiple lists."""
    try:
        task.source_list_id = list_id
    except (AttributeError, TypeError):
        pass
    return task


def parse_sort(sort: str | None, reverse_flag: bool) -> tuple[str | None, bool]:
    """Parse ``--sort`` (with optional direction) and the ``--reverse`` flag.

    Returns ``(field, descending)``. Accepted forms for ``sort``:

        field          -> (field, reverse_flag)        # plain, --reverse applies
        field:asc      -> (field, False)
        field:desc     -> (field, True)
        -field         -> (field, True)                 # git/jq-style
        +field         -> (field, False)

    Surrounding whitespace is trimmed. Direction tokens are case-insensitive.
    Empty/whitespace-only input, empty field after prefix/colon, invalid
    direction, and combining an explicit direction with ``--reverse`` are
    all usage errors (exit 2) so an agent never gets silent input swallowing
    or double-toggle behavior.
    """
    if sort is None:
        return None, reverse_flag

    sort = sort.strip()
    if not sort:
        usage_error("Error: --sort value is empty.")

    field: str
    explicit_desc: bool | None = None

    if sort.startswith("-"):
        field, explicit_desc = sort[1:].strip(), True
    elif sort.startswith("+"):
        field, explicit_desc = sort[1:].strip(), False
    elif ":" in sort:
        raw_field, _, direction = sort.partition(":")
        field = raw_field.strip()
        direction = direction.strip().lower()
        if direction == "desc":
            explicit_desc = True
        elif direction == "asc":
            explicit_desc = False
        else:
            usage_error(f"Error: invalid sort direction '{direction}'. Use 'asc' or 'desc'.")
    else:
        field = sort

    if explicit_desc is None:
        return field, reverse_flag

    if not field:
        usage_error("Error: --sort field name is empty.")
    if reverse_flag:
        usage_error("Error: --reverse can't be combined with an explicit direction in --sort.")

    return field, explicit_desc


# Priority is a fixed 1..4 scale (1=urgent, 4=low). Reject anything else
# at the CLI boundary instead of letting it slip through to the backend.
VALID_PRIORITIES: set[int] = {1, 2, 3, 4}


def validate_priority(priority: int | None) -> None:
    """Reject priorities outside ClickUp's 1..4 scale with a usage error."""
    if priority is None:
        return
    if priority not in VALID_PRIORITIES:
        usage_error(f"Error: --priority must be 1 (urgent), 2 (high), 3 (normal), or 4 (low). Got {priority}.")


def validate_task_name(name: str | None, *, field: str = "task name") -> None:
    """Reject empty/whitespace-only task names."""
    if name is None:
        return
    if not name.strip():
        usage_error(f"Error: {field} cannot be empty or whitespace-only.")


# Fields we can sort tasks by client-side. Server-side sort isn't reliable
# (priority in particular isn't natively orderable), and multi-list queries
# need a global re-sort over the merged result set anyway, so we just sort
# everything ourselves.
SORTABLE_FIELDS = {"created", "updated", "due_date", "priority"}


def task_sort_value(task: Any, field: str) -> int | None:
    """Return the sortable int value for the chosen field, or None if missing.

    All four sortable fields are epoch-ms strings (created/updated/due_date)
    or priority strings ("1".."4"). Anything that doesn't coerce to int is
    treated as missing -- mixing types in the sort key would crash ``sorted``.
    """
    if field == "priority":
        raw = task.priority.priority if task.priority is not None else None
    elif field == "created":
        raw = task.date_created
    elif field == "updated":
        raw = task.date_updated
    elif field == "due_date":
        raw = task.due_date
    else:
        return None
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def filter_open_only(tasks: list[Any]) -> list[Any]:
    """Drop tasks whose status type is ``closed``.

    Lets agents say "show me what's still active" without having to first
    enumerate every non-closed status name on every list.
    """
    return [t for t in tasks if not (t.status and getattr(t.status, "type", None) == "closed")]


def sort_tasks_locally(tasks: list[Any], field: str | None, descending: bool) -> list[Any]:
    """Globally sort tasks client-side. No-op when ``field`` is None.

    Tasks missing the field always sort last regardless of direction so a
    pile of None entries never pushes the values an agent actually wants out
    of the top of a `--reverse` view.
    """
    if not field:
        return tasks
    if field not in SORTABLE_FIELDS:
        usage_error(f"Error: invalid --sort field '{field}'. Use one of: {', '.join(sorted(SORTABLE_FIELDS))}.")
    present = [t for t in tasks if task_sort_value(t, field) is not None]
    missing = [t for t in tasks if task_sort_value(t, field) is None]
    present.sort(key=lambda t: task_sort_value(t, field), reverse=descending)
    return present + missing


def apply_task_filters(
    tasks: list[Any],
    *,
    statuses: set[str] | None = None,
    updated_since_ms: int | None = None,
    open_only: bool = False,
    sort_field: str | None = None,
    sort_descending: bool = False,
) -> list[Any]:
    """Shared client-side post-filter + sort pipeline.

    Used by ``task list``, ``task mine``, and ``task search`` so the
    ``--status``/``--sort``/``--updated-since``/``--open-only`` filters
    behave identically everywhere.
    """
    if statuses:
        tasks = [t for t in tasks if t.status and t.status.status and t.status.status.lower() in statuses]
    if updated_since_ms is not None:
        tasks = [t for t in tasks if t.date_updated and int(t.date_updated) >= updated_since_ms]
    if open_only:
        tasks = filter_open_only(tasks)
    tasks = sort_tasks_locally(tasks, sort_field, sort_descending)
    return tasks


def normalise_status(status: Any) -> dict[str, Any]:
    """Convert ClickUp status shapes into a stable JSON/table dict."""
    if isinstance(status, dict):
        return {
            "status": status.get("status"),
            "type": status.get("type"),
            "color": status.get("color"),
            "orderindex": status.get("orderindex"),
        }
    return {
        "status": getattr(status, "status", str(status)),
        "type": getattr(status, "type", None),
        "color": getattr(status, "color", None),
        "orderindex": getattr(status, "orderindex", None),
    }


def statuses_from_list(list_obj: Any) -> list[dict[str, Any]]:
    """Extract allowed statuses from list metadata returned by ClickUp."""
    raw_statuses = (getattr(list_obj, "model_extra", None) or {}).get("statuses")
    if isinstance(raw_statuses, list):
        return [normalise_status(status) for status in raw_statuses]
    list_status = getattr(list_obj, "status", None)
    if list_status is not None:
        return [normalise_status(list_status)]
    return []
