# Agent 09 Report (v3)

## Use case
Create a task whose name contains Rich-hostile characters (`[bug]`, parentheses, `!`) and verify they survive round-trip. Create a second task with a newline in the description.

## Transcript
1. `clickup --help` -> found `task` subgroup.
2. `clickup task create --help` -> NAME is a positional arg, `--description/-d` for body.
3. `clickup mock init --force` -> seeded the JSON backend.
4. `clickup task create '[bug] Fix login page (urgent!)' --list-id inbox` -> created mock_1006, name intact in JSON.
5. `clickup task get mock_1006` -> round-tripped, name identical.
6. `clickup --format table task get mock_1006` -> table output also preserves brackets (Rich markup escaped correctly).
7. `clickup task create 'Multiline description test' --list-id inbox --description "$(printf 'Line one.\nLine two.')"` -> created mock_1007, description `"Line one.\nLine two."`.
8. `clickup task get mock_1007` -> newline preserved in JSON.
9. `clickup --format table task get mock_1007` -> table renders two description lines correctly.

## What worked well
- Special characters in task names (`[`, `]`, `(`, `)`, `!`) are fully preserved in both JSON and table output. The Rich markup escaping mentioned in AGENT.md is working.
- Multiline descriptions work out of the box via shell command substitution (`$(printf ...)`). No special flag needed.
- Help text is clear and sufficient; `--list-id` accepts aliases (`inbox`) which removes the need to look up raw IDs.
- Mock backend initializes in one command and the config file already points to it, so no extra wiring needed.
- JSON is the default output format, which is ideal for an agent parsing results.

## Friction / surprises / broken things
- **No `default_status` applied.** The config has no `default_status` key, and CLAUDE.md says new tasks default to `on-deck`, but the created tasks landed in `to do`. Minor inconsistency between docs and behavior for this mock config, though `task create --help` correctly explains the fallback chain.
- **No confirmation of which list a task was created in from the CLI's perspective.** The JSON response includes `list.id` and `list.name` which is fine, but a brief "Created task mock_1006 in Inbox" stderr message would help an agent confirm success without parsing the full JSON.
- **Newline in `--description` requires shell tricks.** Passing a literal `\n` (backslash-n) would likely store two characters, not a newline. An agent must use `$(printf ...)` or `$'...\n...'` syntax. This is a shell limitation, not a CLI bug, but documenting the pattern or accepting `\n` escape sequences in the description flag would help.

## Concrete improvement suggestions
1. Consider emitting a one-line success summary to stderr after `task create` (e.g., `Created mock_1006 "[bug] Fix login page (urgent!)" in Inbox`). Agents can parse JSON from stdout and still get a human-readable confirmation on stderr.
2. Document the `$(printf 'line1\nline2')` pattern for multiline descriptions in help text or AGENT.md, since agents will hit this.
3. Seed mock configs with `default_status` matching the documented default (`on-deck`) so the mock experience matches the docs.

## Verdict
pass
