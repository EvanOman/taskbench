# Agent 14 Report

## Use case
Get all tasks across all lists as JSON, pipe to jq to count tasks in "to do" status.

## Transcript
1. `clickup --help` -- discovered top-level commands and `--format` global flag
2. `clickup task --help` -- found `list` subcommand with `--all-lists` and `--status` filter
3. `clickup task list --help` -- confirmed `--all-lists` flag and `--status` option
4. `clickup list show --help` -- explored list discovery (not needed in the end)
5. `clickup config show` -- confirmed two default_lists aliases (inbox, active)
6. `clickup list show --space-id space_ops` -- failed with "Space ID invalid" (mock provider issue)
7. `clickup --format json task list --all-lists` -- got all 5 tasks as JSON, clean structured output
8. `... | jq '[.data[] | select(.status.status == "to do")] | length'` -- result: **2**
9. `clickup --format json task list --all-lists --status "to do" | jq '.count'` -- server-side filter also returned 2, confirming result

## What worked well
- `--all-lists` flag is exactly what an agent needs for cross-list queries; no need to enumerate list IDs manually
- JSON output is clean and well-structured with `{"data": [...], "count": N}` envelope
- `--format` as a global flag before the subcommand is intuitive once you see it in `--help`
- `--status` server-side filter works and matches the jq approach, good for simpler pipelines
- The `default_lists` config concept means `--all-lists` just works without any discovery

## Friction / surprises / broken things
- `list show --space-id space_ops` returned "Space ID invalid" even though space_ops is the configured default_space_id; the mock provider doesn't seem to support this endpoint
- The `--format` flag must go before the subcommand (i.e., `clickup --format json task list`, not `clickup task list --format json`); this is documented but easy to get wrong on first try since most CLIs put flags after the command
- No built-in way to get a cross-list task count without piping to jq; `--status` filter helps but still requires `jq '.count'` or similar to extract the number

## Concrete improvement suggestions
- Support `list show` in the mock provider so workspace discovery works end-to-end in test scenarios
- Consider adding a `task count` subcommand or `--count-only` flag that emits just the integer count, useful for scripts and agents that only need the number
- Add a note in `task list --help` that `--all-lists` requires `default_lists` to be configured (currently you have to check `config show` to understand what it queries)

## Verdict
pass
