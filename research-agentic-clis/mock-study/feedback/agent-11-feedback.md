# Agent 11 Report

## Use case
Create a new list called "Reading" under an existing folder, then add 2 tasks to it.

## Transcript
1. `clickup --help` -- discovered top-level commands including `list`, `task`, `discover`
2. `clickup list --help` -- found `list create` subcommand
3. `clickup list create --help` -- learned it takes `--folder-id` or `--space-id`
4. `clickup task --help` -- confirmed `task create` exists
5. `clickup config show` -- saw mock provider config with `space_ops`, `folder_daily`, etc.
6. `clickup discover hierarchy` -- returned real ClickUp API data (space `90138201902`), not mock data
7. `clickup list create "Reading" --space-id 90138201902` -- succeeded, created list `901327247659` (hit real API)
8. `clickup task create "Finish Designing Data-Intensive Applications" --list-id 901327247659` -- FAILED: "List not found: 901327247659"
9. `clickup list get --list-id 901327247659` -- succeeded, confirmed list exists (via real API)
10. `clickup list create "Reading" --folder-id folder_daily` -- FAILED: "Folder ID invalid" (mock IDs rejected by real API)
11. `clickup list create "Reading" --space-id space_ops` -- FAILED: "Space ID invalid" (same issue)
12. `clickup api POST /list/901327247659/task -d '{"name": "Finish Designing Data-Intensive Applications"}'` -- succeeded via raw API
13. `clickup api POST /list/901327247659/task -d '{"name": "Re-read DDD blue book ch. 4"}'` -- succeeded via raw API
14. `clickup api GET /list/901327247659/task` -- confirmed both tasks present

## What worked well
- `--help` is clear and well-organized at every level; discoverable command groups
- `list create` help clearly shows `--folder-id` vs `--space-id` options
- `discover hierarchy` gave a useful tree of the workspace structure
- `api` raw command was a lifesaver escape hatch when typed commands failed
- JSON default output is agent-friendly

## Friction / surprises / broken things
- **Mock/real provider split is invisible and breaks workflows.** Config says `provider: json` but `list create`, `list get`, and `discover hierarchy` all hit the real ClickUp API, while `task create` and `task list` use the mock JSON provider. There is no indication which commands route where. This caused the core failure: a list created via the real API was invisible to the mock-backed task commands.
- **`task create --list-id <real-id>` fails with "List not found"** even though `list get --list-id <same-id>` succeeds. The error message gives no hint that the problem is a provider mismatch rather than a genuinely missing list.
- **`list get` takes `--list-id` as an option, not a positional argument**, unlike `task get` which takes the task ID as a positional. Inconsistent argument style across sibling commands.
- **No folder creation command.** The scenario asked to create a list under "your existing folder," but `workspace folders` only lists folders -- there's no `folder create`. Minor since folderless lists work, but the gap is visible.
- **`discover hierarchy` ignores the mock provider.** It returned real workspace data even though the config is set to the JSON mock provider. An agent trying to find IDs to use with mock-backed commands gets IDs that won't work.

## Concrete improvement suggestions
- Route `list create`, `list get`, `list show`, and `discover` commands through the same provider as `task` commands, so the mock backend is self-consistent.
- Make the error message for "List not found" mention if a provider mismatch might be the cause, or at least log which provider is handling the request.
- Make `list get` accept the list ID as a positional argument (like `task get <id>`) for consistency.
- Add a `folder create` command to support the full hierarchy CRUD.
- Consider a `--provider` diagnostic flag or `clickup status` output that shows which provider each command group uses.

## Verdict
partial
