# Agent 12 Report (v2)

## Use case
Append " — due Friday" to the description of task "Draft weekly project update" without losing existing text.

## Transcript
1. `clickup --help` -- discovered top-level commands
2. `clickup task --help` -- found `get` and `update` subcommands
3. `clickup task get mock_1001` -- retrieved current description: "Summarize completed work, blockers, and next actions."
4. `clickup task update mock_1001 --description "Summarize completed work, blockers, and next actions. — due Friday"` -- replaced description with old text + appended suffix
5. `clickup task get mock_1001` -- verified description now includes appended text

Total: 5 commands (3 discovery/verification, 1 read, 1 write).

## What worked well
- JSON-default output made it trivial to extract the `description` field from `task get`.
- `task update` with modify-if-passed semantics worked exactly as documented: only the description changed, everything else stayed put.
- Help text was clear and complete; flags like `-d` for `--description` are well-chosen.
- The update command echoes the full updated task back, giving immediate confirmation without a separate `get`.

## Friction / surprises / broken things
- **No append/prepend semantics for description.** I had to read the current description, manually concatenate, and write back. This is a read-modify-write race in any concurrent scenario and adds an extra round-trip every time an agent wants to add to (not replace) a description.
- **Finding the right task required knowing the ID.** There was no `task search --name "Draft weekly"` attempt needed here because I already saw the store, but an agent coming in cold would need to `task list`, parse JSON, and filter. A `--name` filter on `task list` or better `task search` integration would help.
- **The em-dash in " — due Friday" could be tricky.** Shell quoting handled it fine here, but special characters in descriptions are a latent risk for agents constructing shell commands.

## Concrete improvement suggestions
1. Add `--append-description` / `--prepend-description` flags to `task update` so agents can add text without a read-modify-write cycle.
2. Add `task search --name <substring>` that returns matching tasks from the default list (or a specified list) so agents don't have to list-then-filter.
3. Consider a `task get --field description` flag to return just one field's value as plain text, avoiding JSON parsing for simple read-then-append workflows.

## Verdict
The task completed in 5 commands with no errors. The CLI is well-structured for agent use. The main gap is the lack of atomic append for text fields, which forces a fragile read-modify-write pattern for what should be a one-step operation.
