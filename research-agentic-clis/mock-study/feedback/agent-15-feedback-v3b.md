# Agent 15 Report (v3b -- post-fix re-verification)

## Transcript

### 1. `task update mock_9999 --name "x"` -- nonexistent task
- **Exit code:** 1
- **stdout:** empty
- **stderr:** `{"error": "ClickUp API Error: Task not found: mock_9999", "type": "NotFoundError"}`

### 2. `task status mock_9999 done` -- nonexistent task
- **Exit code:** 1
- **stdout:** empty
- **stderr:** `{"error": "ClickUp API Error (mock_9999): Task not found: mock_9999", "type": "NotFoundError"}`

### 3. `task create "x" --list-id totally_fake_list` -- nonexistent list
- **Exit code:** 1
- **stdout:** empty
- **stderr:** `{"error": "ClickUp API Error: List not found: totally_fake_list", "type": "NotFoundError"}`

### 4. `task update mock_1001 --priority 99` -- invalid priority
- **Exit code:** 2
- **stdout:** empty
- **stderr:** `{"error": "Error: --priority must be 1 (urgent), 2 (high), 3 (normal), or 4 (low). Got 99.", "type": "UsageError"}`

### 5. `task list --list-id inbox --sort fartfield` -- invalid sort field
- **Exit code:** 2
- **stdout:** empty
- **stderr:** `{"error": "Error: invalid --sort field 'fartfield'. Use one of: created, due_date, priority, updated.", "type": "UsageError"}`

### 6. `task create "" --list-id inbox` -- empty name
- **Exit code:** 2
- **stdout:** empty
- **stderr:** `{"error": "Error: task name cannot be empty or whitespace-only.", "type": "UsageError"}`

### 7. `task status mock_1001 "totally-not-a-status"` -- invalid status
- **Exit code:** 1
- **stdout:** empty
- **stderr:** `{"error": "ClickUp API Error (mock_1001): Unknown status 'totally-not-a-status'. Available: to do, in progress, on-deck, complete.", "type": "ValidationError"}`

### 8. `task delete mock_1001` -- no --force
- **Exit code:** 2
- **stdout:** empty
- **stderr:** `{"error": "Refusing to delete without --force/--yes (this CLI never prompts)."}`

### 9. `frobnicate` -- unknown subcommand
- **Exit code:** 2
- **stdout:** empty
- **stderr:** `{"error": "No such command 'frobnicate'.", "type": "UsageError", "command": "clickup"}`

### 10. `task list --list-id inbox --limit abc` -- non-numeric limit
- **Exit code:** 2
- **stdout:** empty
- **stderr:** `{"error": "Invalid value for '--limit' (env var: 'None'): 'abc' is not a valid integer.", "type": "BadParameter", "command": "clickup task list"}`

### 11. `task done` -- zero IDs
- **Exit code:** 2
- **stdout:** empty
- **stderr:** `{"error": "Missing argument 'TASK_ID...'.", "type": "MissingParameter", "command": "clickup task done"}`

### 12. `task done mock_1001 mock_9999` -- partial success
- **Exit code:** 1
- **stdout:** JSON data envelope with `mock_1001` updated to "complete" (`{"data": [...], "count": 1}`)
- **stderr:** `{"error": "ClickUp API Error (mock_9999): Task not found: mock_9999", "type": "NotFoundError"}`

### 13. `task list --list-id inbox --brief` -- happy path
- **Exit code:** 0
- **stdout:** `{"data": [...], "count": 3}` with brief fields (id, name, status, priority, priority_label, assignees, url, list, comment_count)
- **stderr:** empty

## Exit-code matrix

| # | Command | Expected | Actual | Match |
|---|---------|----------|--------|-------|
| 1 | `task update mock_9999 --name "x"` | 1 | 1 | YES |
| 2 | `task status mock_9999 done` | 1 | 1 | YES |
| 3 | `task create "x" --list-id totally_fake_list` | 1 | 1 | YES |
| 4 | `task update mock_1001 --priority 99` | 2 | 2 | YES |
| 5 | `task list --list-id inbox --sort fartfield` | 2 | 2 | YES |
| 6 | `task create "" --list-id inbox` | 2 | 2 | YES |
| 7 | `task status mock_1001 "totally-not-a-status"` | 1 | 1 | YES |
| 8 | `task delete mock_1001` (no --force) | 2 | 2 | YES |
| 9 | `frobnicate` | 2 | 2 | YES |
| 10 | `task list --list-id inbox --limit abc` | 2 | 2 | YES |
| 11 | `task done` (zero IDs) | 2 | 2 | YES |
| 12 | `task done mock_1001 mock_9999` | 1 | 1 | YES |
| 13 | `task list --list-id inbox --brief` | 0 | 0 | YES |

**13/13 match.**

## Envelope consistency

Three envelope shapes appear across all failure modes:

1. **Application/API errors** (exit 1): `{"error": "<message>", "type": "<ErrorClass>"}` -- always on stderr, stdout empty (or data for partial-success case #12).
2. **Usage errors** (exit 2): `{"error": "<message>", "type": "UsageError"|"BadParameter"|"MissingParameter"}` -- Typer-originated errors include an additional `"command"` field; app-level usage errors omit it. Always on stderr, stdout empty.
3. **Refusal errors** (exit 2, --force guard): `{"error": "<message>"}` -- type field absent. Stderr only, stdout empty.

All errors are valid single-line JSON. The `error` field is always present. The `type` field is present in all cases except the `--force` refusal (#8). The `command` field appears only on Typer-framework errors (#9, #10, #11).

**Stream routing is clean:** every error goes to stderr; stdout is reserved for data (success or partial-success). An agent can parse stderr as JSON on any nonzero `$?`.

## Verdict

**pass**

All 13 exit codes match expectations. Error envelopes are consistently JSON on stderr with a reliable `error` key. The exit-code split (1 = runtime/API, 2 = usage/validation) is maintained across all failure modes. An agent can now rely on `$?` + one `jq .error` parse path on stderr for all failure modes. The only minor inconsistency is the missing `type` field on the `--force` refusal (#8), but the `error` message is unambiguous and the exit code is correct.
