# Agent 09 Report (v2)

## Use case
Create a task whose name contains brackets and special characters (`[bug] Fix login page (urgent!)`), verify the name round-trips intact, then create a second task with a multi-line description.

## Transcript
1. `clickup --help` -- discovered top-level commands and `--format` flag.
2. `clickup task --help` -- found `create`, `get`, etc.
3. `clickup task create --help` -- confirmed positional `NAME`, `--list-id`, `--description`.
4. `clickup task create '[bug] Fix login page (urgent!)' --list-id inbox` -- created `mock_1008`. JSON output showed name stored verbatim.
5. `clickup task get mock_1008` -- confirmed name round-trips: `[bug] Fix login page (urgent!)`.
6. `clickup --format table task get mock_1008` -- table mode also renders brackets correctly (Rich markup escaping works).
7. `clickup task create 'Multi-line description test' --list-id inbox --description $'First line of description.\nSecond line of description.'` -- created `mock_1009`. JSON shows `\n` in description.
8. `clickup task get mock_1009` -- confirmed multi-line description round-trips.

Total commands: 7 (including help). Task-creation commands: 2. Zero errors.

## What worked well
- **Special characters preserved end-to-end.** Brackets, parentheses, and exclamation marks in the task name were stored and displayed without corruption in both JSON and table formats. The Rich markup escaping noted in AGENT.md is clearly working.
- **Multi-line descriptions work via shell `$'...\n...'` syntax.** The CLI accepts literal newlines in `--description` and round-trips them correctly.
- **Help is well-organized.** Commands are grouped into clear panels (Get started, Task workflow, Workspace navigation). The `task create` help is concise and complete.
- **JSON-by-default is ideal for agents.** The structured output let me verify fields programmatically without parsing table formatting.
- **List aliases (`inbox`) work as documented.** No need to look up raw list IDs.

## Friction / surprises / broken things
- **No `default_status` applied.** The config has no `default_status` key, so both tasks got status `to do` (the list default). This is fine but worth noting -- the CLAUDE.md instructions mention `on-deck` as the typical default, and an agent following those instructions might expect it.
- **No way to pass multi-line descriptions without shell tricks.** The `--description` flag is a plain `TEXT` type. Passing newlines requires shell-specific syntax (`$'...\n...'`). An alternative like `--description-file` or accepting `\n` escape sequences in the string would be more portable across shells and agent harnesses.
- **Verbose JSON output for create.** The full task object (30+ fields, most null) is returned on create. A summary or just `{id, name, url, status}` would reduce noise for the common case. (The full object is useful for verification, so this is a minor point.)

## Concrete improvement suggestions
1. **Accept `\n` literal escape sequences in `--description`.** Pre-process the description string to convert `\n` to actual newlines. This makes multi-line descriptions trivial for any caller without relying on shell features.
2. **Add `--description-file PATH` option.** For longer descriptions, reading from a file (or `-` for stdin) is more robust than quoting multi-line strings on the command line.
3. **Consider a `--brief` flag or summary output mode for mutations.** After `task create` / `task update`, emit just `{id, name, url, status}` to reduce output noise. The full object could remain the default for `task get`.

## Verdict
Smooth. Both tasks -- one with tricky special characters, one with a multi-line description -- were created and verified in a single attempt each. The CLI handled edge cases (brackets that could be misinterpreted as Rich markup, embedded newlines) without any errors or data corruption. The only real friction was needing shell-specific syntax for newlines in descriptions, which is a minor portability concern rather than a bug.
