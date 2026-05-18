# Smoke B: --open-only

## Discovery path
`clickup --help` -> `clickup task --help` -> `clickup task list --help`. The `--open-only` / `--open` flag was clearly documented: "Hide tasks whose status type is 'closed'". Three commands from cold start.

## Transcript
1. `clickup task list --all-lists --brief` -- 5 tasks, all open
2. `clickup task done mock_1001` -- marked "Draft weekly project update" as complete (status type: closed)
3. `clickup task list --all-lists --brief --open-only` -- 4 tasks, mock_1001 absent
4. `clickup task list --all-lists --brief` (no filter) -- 5 tasks, confirming mock_1001 still exists

## Did it work as expected?
Yes. 5 total -> 4 with `--open-only`. The closed task was excluded; all open tasks retained.

## Friction
- None. The flag name is intuitive, the help text is clear, and `--open` as a short alias is nice.
- `task done` worked in one step with no status lookup needed.

## Verdict
pass
