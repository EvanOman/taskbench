# Smoke A: --brief projection

## Discovery path
`clickup --help` -> `clickup task --help` -> `clickup task list --help`. The `--brief` flag is listed in `task list` options with a clear description: "Return only id/name/status/priority/assignees/due_date. Drops noisy null fields and flattens status to a string."

## Transcript
1. `clickup --help` -- found `task` subgroup
2. `clickup task --help` -- found `list` command
3. `clickup task list --help` -- found `--brief` flag
4. `clickup --format json task list --list-id inbox --limit 2` -- default: 35 keys per task, status is a nested object
5. `clickup --format json task list --list-id inbox --limit 2 --brief` -- brief: 8 keys per task, status flattened to string

## Did it work as expected?
Yes. Default returned 35 fields per task (many null). Brief returned 8 fields (id, name, status, priority, priority_label, assignees, url, list). Status was flattened from a 4-key object to a plain string. Null fields eliminated.

## Friction
- None. Three hops through `--help` to find the flag; description was accurate.
- The help text is slightly truncated (`due_…`) but still communicates intent.

## Verdict
pass
