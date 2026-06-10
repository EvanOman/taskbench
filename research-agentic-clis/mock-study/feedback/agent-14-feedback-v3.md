# Agent 14 Report (v3)

## Use case
Produce a JSON list of all tasks across all lists, pipe to `jq` to count tasks still in "to do" status.

## Transcript
1. `clickup --help` -- found `task` subcommand group.
2. `clickup task list --help` -- discovered `--all-lists` flag and `--status` filter.
3. `clickup --format json task list --all-lists` -- returned clean JSON with all 5 tasks across both configured lists (inbox + active). Piped to `jq '[.data[] | select(.status.status == "to do")] | length'` -- result: **2**.
4. Verified with `clickup --format json task list --all-lists --status "to do" --brief` -- same 2 tasks, cleaner payload.
5. Cross-checked with `list show --folder-id folder_daily` to confirm only 2 lists exist in the workspace.

## What worked well
- **stdout is cleanly parseable**: `--format json` output piped to `jq` without any stderr contamination or spinner noise. This is the core agent-first promise and it delivers.
- **`--all-lists` flag**: exactly what was needed. One command, all configured lists, single JSON envelope.
- **`--status` server-side filter**: eliminated the need for client-side jq filtering entirely. Could have just used `clickup --format json task list --all-lists --status "to do"` and read `.count`.
- **`--brief` flag**: dramatically reduces payload noise for programmatic use. Null fields stripped, status flattened to a string.
- **JSON envelope shape `{"data": [...], "count": N}`**: consistent, predictable, easy to pipe.

## Friction / surprises / broken things
1. **`--all-lists` means "all aliases", not "all lists"** -- the help text does explain this, but the flag name is misleading for a first-time user. If `default_lists` config is incomplete, you silently miss lists. The help text even says to use `task search` or `task mine` for workspace-wide queries, but `task search` requires a `--query` which makes it unsuitable for "give me everything."
2. **`list show --space-id` returns 0 for lists inside folders** -- this is ClickUp API semantics (space-level only returns "folderless" lists), but it's a trap. An agent trying to enumerate all lists in a space will miss folder-nested ones. No hint in the `--help`.
3. **Config sets `output_format: table` but the task is JSON-centric** -- an agent must always pass `--format json` explicitly. Not a bug (the global flag works fine), but worth noting that the config default can fight the agent's needs.

## Concrete improvement suggestions
1. Consider a `task list --all` or `task list --workspace` flag that truly queries every list in the workspace (e.g., by enumerating folders/lists automatically), distinct from `--all-lists` which only hits aliases.
2. Add a note to `list show --space-id` help text explaining that folder-nested lists require `--folder-id`.
3. Consider adding `task search` without `--query` as a way to dump all tasks workspace-wide (or make `--query` optional with a default of matching everything).

## Verdict
pass
