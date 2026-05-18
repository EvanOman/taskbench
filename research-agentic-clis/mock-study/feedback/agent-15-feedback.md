# Agent 15 Report

## Use case
Error-mode shakedown. Deliberately exercise broken inputs and evaluate whether the CLI's error responses are structured, routed correctly (stderr vs stdout), and programmatically recoverable.

## Transcript

### Test 1: `task update mock_9999 --name "x"` (nonexistent task)
- **Exit code:** 1
- **Stdout:** empty
- **Stderr:** `{"error": "ClickUp API Error: Task not found: mock_9999"}`
- **Error shape:** JSON envelope
- **Recoverable:** Yes. Structured error, clean stdout, nonzero exit.

### Test 2: `task status mock_9999 done` (nonexistent task)
- **Exit code:** 1
- **Stdout:** empty
- **Stderr:** `{"error": "ClickUp API Error: Task not found: mock_9999"}`
- **Error shape:** JSON envelope
- **Recoverable:** Yes.

### Test 3: `task create "x" --list-id totally_fake_list` (nonexistent list)
- **Exit code:** 1
- **Stdout:** empty
- **Stderr:** `{"error": "ClickUp API Error: List not found: totally_fake_list"}`
- **Error shape:** JSON envelope
- **Recoverable:** Yes.

### Test 4: `task update mock_1001 --priority 99` (invalid priority)
- **Exit code:** 0
- **Stdout:** full task JSON with `"priority": 99`
- **Stderr:** empty
- **Error shape:** No error at all -- silently accepted
- **Recoverable:** N/A. The CLI did not treat this as an error. Help text says "1-4" but no validation enforced.

### Test 5: `task list --list-id inbox --sort fartfield` (bogus sort field)
- **Exit code:** 0
- **Stdout:** full task list JSON (unsorted or default-sorted)
- **Stderr:** empty
- **Error shape:** No error -- silently ignored
- **Recoverable:** N/A. Agent has no way to know the sort was ignored.

### Test 6: `task get mock_9999` (nonexistent task)
- **Exit code:** 1
- **Stdout:** empty
- **Stderr:** `{"error": "ClickUp API Error: Task not found: mock_9999"}`
- **Error shape:** JSON envelope
- **Recoverable:** Yes.

### Test 7: `task delete mock_1001` (without --force)
- **Exit code:** 2
- **Stdout:** empty
- **Stderr:** `{"error": "Refusing to delete without --force/--yes (this CLI never prompts)."}`
- **Error shape:** JSON envelope
- **Recoverable:** Yes. Exit code 2 distinguishes usage error from API error. Error message tells you exactly what to do.

### Test 8: `task create "" --list-id inbox` (empty name)
- **Exit code:** 0
- **Stdout:** full task JSON with `"name": ""`
- **Stderr:** empty
- **Error shape:** No error -- silently accepted
- **Recoverable:** N/A. A task with an empty name was created and persisted. An agent would not know this was likely a mistake.

### Test 9: `task done mock_9999` (nonexistent task)
- **Exit code:** 1
- **Stdout:** empty
- **Stderr:** `{"error": "ClickUp API Error: Task not found: mock_9999"}`
- **Error shape:** JSON envelope
- **Recoverable:** Yes.

### Test 10: `task list` (no config, no list-id)
- **Exit code:** 1
- **Stdout:** `Use --list-id or set a default with 'clickup config set default_list_id <id>'` (guidance text leaked to stdout)
- **Stderr:** `{"error": "Error: No list ID provided and no default list configured."}`
- **Error shape:** JSON envelope on stderr, but also prose on stdout
- **Recoverable:** Partially. The JSON error on stderr is parseable, but the stdout guidance pollutes the data stream. An agent piping stdout to a file would get unexpected text.

### Test 11: `task update --name "x"` (no task ID at all)
- **Exit code:** 2
- **Stdout:** empty
- **Stderr:** `{"error": "Error: Task ID or --task-ids is required."}`
- **Error shape:** JSON envelope
- **Recoverable:** Yes.

### Test 12: `task create "zero priority" --list-id inbox --priority 0`
- **Exit code:** 0
- **Stdout:** task JSON with `"priority": null`
- **Stderr:** empty
- **Error shape:** No error. Priority 0 was silently mapped to null (ClickUp convention). Acceptable but undocumented -- help text says "1-4".

### Test 13: `task yeet` (nonexistent subcommand)
- **Exit code:** 2
- **Stdout:** empty
- **Stderr:** Typer error box: `No such command 'yeet'.`
- **Error shape:** Prose (Rich-formatted), not JSON envelope
- **Recoverable:** Partially. Exit code 2 is correct for usage error, but the error is not in JSON envelope form. An agent parsing stderr for `{"error": ...}` would miss this.

### Test 14: `task update mock_1001 --priority -1` (negative priority)
- **Exit code:** 0
- **Stdout:** task JSON with `"priority": -1`
- **Stderr:** empty
- **Error shape:** No error -- silently accepted
- **Recoverable:** N/A. Invalid value persisted.

### Test 15: `task status mock_1001 "nonexistent_status_xyzzy"` (invalid status)
- **Exit code:** 0
- **Stdout:** task JSON with `"status": "nonexistent_status_xyzzy"`
- **Stderr:** empty
- **Error shape:** No error -- silently accepted
- **Recoverable:** N/A. The mock provider accepted a nonsense status. The real API might reject it, but the CLI layer did no pre-validation.

### Test 16: `task list --list-id inbox --limit abc` (non-integer limit)
- **Exit code:** 2
- **Stdout:** empty
- **Stderr:** Typer error: `'abc' is not a valid integer.`
- **Error shape:** Prose (Rich-formatted), not JSON envelope
- **Recoverable:** Partially. Same issue as test 13 -- Typer's built-in validation errors bypass the JSON envelope.

## What worked well
- **Not-found errors are excellent.** Task/list not found consistently returns exit 1, JSON envelope on stderr, clean stdout. An agent can reliably parse `{"error": ...}` and decide what to do.
- **Destructive-op guard (--force) is well-designed.** Exit code 2 distinguishes usage from API errors. Error message tells you the fix. JSON envelope format maintained.
- **Missing-argument errors are solid.** No task ID -> exit 2, JSON error, clear message.
- **Stdout/stderr separation is mostly correct.** For API-level errors, stdout stays clean.

## Friction / surprises / broken things
- **No priority validation.** Help says "1-4" but the CLI silently accepts 99, -1, 0. An agent has no guardrail against setting garbage priority values. Priority 0 silently maps to null which is semi-defensible but undocumented.
- **No sort-field validation.** `--sort fartfield` silently succeeds. An agent cannot tell its sort was ignored. Should reject unknown fields with an error.
- **Empty task name accepted.** `task create "" --list-id inbox` creates a task with no name. Should reject or warn.
- **Typer-level validation errors are not JSON-enveloped.** Invalid subcommands and type-coercion errors (e.g., `--limit abc`) produce Rich-formatted prose on stderr, not `{"error": ...}`. An agent that consistently parses `{"error": ...}` from stderr will miss these.
- **Stdout pollution in "no list ID" error.** Test 10 showed guidance text leaking to stdout alongside the JSON error on stderr. Breaks `> data.json` pipelines.
- **Mock provider does not validate status names.** `task status mock_1001 "nonexistent_status_xyzzy"` succeeds silently. Whether this is a CLI bug or a mock-only gap is unclear, but it means the mock doesn't catch status typos that the real API might reject.

## Concrete improvement suggestions
1. **Validate priority range (1-4) in the CLI layer** before sending to provider. Reject out-of-range values with exit 2 and a JSON error. Priority 0 could remain valid as "clear priority" but should be documented.
2. **Validate sort field** against the known set `{created, updated, due_date, priority}`. Reject unknown fields with exit 2 and a JSON error listing valid options.
3. **Reject empty task names** at creation time. Exit 2 with a clear error.
4. **Wrap Typer validation errors in JSON envelope.** Add an exception handler or Typer callback that catches `click.exceptions.BadParameter` / `click.exceptions.UsageError` and routes them through `render_error()` before exiting. This makes all errors consistently parseable.
5. **Move the guidance text in the "no list ID" error to stderr** (or embed it in the JSON error's message field). Nothing but data should hit stdout.
6. **Consider status pre-validation** in the mock provider (and optionally the real provider) -- at minimum, warn on stderr if the status doesn't match any known status for the list.

## Verdict
partial

The happy-path error handling (not-found, missing args, destructive-op guards) is agent-grade: structured JSON, correct exit codes, clean stdout. But input validation is porous -- invalid priorities, bogus sort fields, empty names, and nonsense statuses all slip through silently. Typer-level errors also break the JSON envelope contract. An agent that only checks exit codes would silently corrupt data; one that parses `{"error": ...}` from stderr would miss Typer validation failures.
