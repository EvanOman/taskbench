# Agent 15 Report (v2)

## Use case

Error-mode shakedown (round 2). Intentionally exercised every failure path an agent is likely to hit: nonexistent resources, invalid values, missing required args, bogus subcommands, empty inputs.

## Transcript

### 1. `task update mock_9999 --name "x"` (nonexistent task)
- **Exit code:** 1
- **stderr:** `{"error": "ClickUp API Error: Task not found: mock_9999"}`
- **stdout:** empty
- **Error shape:** JSON envelope `{"error": ...}` on stderr
- **Recoverable:** Yes. Clear ID cited; agent can list tasks and retry.

### 2. `task status mock_9999 done` (nonexistent task)
- **Exit code:** 1
- **stderr:** `{"error": "ClickUp API Error: Task not found: mock_9999"}`
- **stdout:** empty
- **Error shape:** JSON envelope on stderr
- **Recoverable:** Yes. Same pattern as #1.

### 3. `task create "x" --list-id totally_fake_list` (nonexistent list)
- **Exit code:** 1
- **stderr:** `{"error": "ClickUp API Error: List not found: totally_fake_list"}`
- **stdout:** empty
- **Error shape:** JSON envelope on stderr
- **Recoverable:** Yes. Agent could discover lists and retry.

### 4. `task update mock_1001 --priority 99` (invalid priority)
- **Exit code:** 2
- **stderr:** `{"error": "Error: --priority must be 1 (urgent), 2 (high), 3 (normal), or 4 (low). Got 99."}`
- **stdout:** empty
- **Error shape:** JSON envelope on stderr. Includes valid values.
- **Recoverable:** Yes. Error message is self-correcting -- tells the agent exactly what to pass.

### 5. `task list --list-id inbox --sort fartfield` (unknown sort field)
- **Exit code:** 2
- **stderr:** `{"error": "Error: invalid --sort field 'fartfield'. Use one of: created, due_date, priority, updated."}`
- **stdout:** empty
- **Error shape:** JSON envelope on stderr. Lists valid options.
- **Recoverable:** Yes. Same self-correcting pattern.

### 6. `task create "" --list-id inbox` (empty name)
- **Exit code:** 2
- **stderr:** `{"error": "Error: task name cannot be empty or whitespace-only."}`
- **stdout:** empty
- **Error shape:** JSON envelope on stderr
- **Recoverable:** Yes. Agent knows it needs a non-empty name.

### 7. `task status mock_1001 "totally-not-a-status"` (unknown status)
- **Exit code:** 1
- **stderr:** `{"error": "ClickUp API Error: Unknown status 'totally-not-a-status'. Available: to do, in progress, on-deck, complete."}`
- **stdout:** empty
- **Error shape:** JSON envelope on stderr. Lists all valid statuses.
- **Recoverable:** Yes. Best error message in the suite -- gives exact valid options.

### 8. `task list` (no list-id, no default in flag)
- **Exit code:** 0
- **stderr:** empty
- **stdout:** Full JSON task list from default list (`list_inbox` per config)
- **Error shape:** N/A -- not an error. Config's `default_list_id` kicked in.
- **Recoverable:** N/A. This is actually a success case.

### 9. `task get mock_9999` (nonexistent task)
- **Exit code:** 1
- **stderr:** `{"error": "ClickUp API Error: Task not found: mock_9999"}`
- **stdout:** empty
- **Error shape:** JSON envelope on stderr
- **Recoverable:** Yes.

### 10. `task delete mock_1001` (without --force)
- **Exit code:** 2
- **stderr:** `{"error": "Refusing to delete without --force/--yes (this CLI never prompts)."}`
- **stdout:** empty
- **Error shape:** JSON envelope on stderr
- **Recoverable:** Yes. Tells agent exactly what flag to add.

### 11. `task frobnicate` (bogus subcommand)
- **Exit code:** 2
- **stderr:** Typer's built-in Rich-formatted error (not JSON): `No such command 'frobnicate'.`
- **stdout:** empty
- **Error shape:** PROSE with Rich box-drawing characters -- NOT a JSON envelope
- **Recoverable:** Partially. Agent can parse "No such command" but has to handle non-JSON.

### 12. `task create "   " --list-id inbox` (whitespace-only name)
- **Exit code:** 2
- **stderr:** `{"error": "Error: task name cannot be empty or whitespace-only."}`
- **stdout:** empty
- **Error shape:** JSON envelope on stderr
- **Recoverable:** Yes.

### 13. `task update mock_1001` (no mutation flags)
- **Exit code:** 0
- **stderr:** `{"message": "No updates specified.", "level": "warn"}`
- **stdout:** empty
- **Error shape:** JSON warning envelope on stderr (not `{"error": ...}` -- uses `{"message": ..., "level": "warn"}`)
- **Recoverable:** Yes, but the different shape from error messages is something an agent would need to handle separately.

### 14. `task list --list-id nonexistent_alias` (non-existent alias passed as list-id)
- **Exit code:** 1
- **stderr:** `{"error": "ClickUp API Error: List not found: nonexistent_alias"}`
- **stdout:** empty
- **Error shape:** JSON envelope on stderr
- **Recoverable:** Yes.

### 15. `--format json task frobnicate` (bogus subcommand, explicit JSON mode)
- **Exit code:** 2
- **stderr:** Typer's Rich-formatted prose error, same as #11 -- `--format json` has NO effect on Typer-level errors.
- **stdout:** empty
- **Error shape:** PROSE, not JSON
- **Recoverable:** Same as #11.

### 16. `task status mock_1001` (missing required status argument)
- **Exit code:** 2
- **stderr:** `{"error": "Error: Status is required. Usage: clickup task status TASK_ID STATUS"}`
- **stdout:** empty
- **Error shape:** JSON envelope on stderr, includes usage hint
- **Recoverable:** Yes.

## What worked well

1. **Consistent JSON error envelope.** 13 of 16 test cases returned `{"error": "..."}` on stderr. An agent can parse errors with a single `json.loads()` path in almost every case.
2. **Self-correcting error messages.** Tests #4, #5, #7, and #16 all include the valid values or usage syntax directly in the error. An agent can extract these and retry without needing `--help`.
3. **Clean stdout/stderr separation.** Errors never pollute stdout. An agent piping `stdout > file` will never get error text mixed into data.
4. **Exit code discipline.** `1` for API/runtime errors, `2` for usage errors. This is a meaningful distinction an agent can branch on.
5. **Default list fallback.** `task list` without `--list-id` silently uses the configured default. This is exactly what an agent wants -- no error, just works.
6. **Delete safety gate.** The `--force` refusal message (test #10) tells the agent exactly what flag to add, and never prompts interactively.
7. **Warning envelope for no-op.** `task update` with no flags doesn't error -- it warns. Exit 0 is correct (nothing went wrong), and the warn on stderr is a nice touch.

## Friction / surprises / broken things

1. **Typer-level errors bypass JSON envelope.** Bogus subcommands (#11, #15) produce Rich-formatted prose on stderr (`No such command 'frobnicate'`) regardless of `--format json`. An agent expecting uniform JSON errors will choke on the box-drawing characters. This is the only real gap.
2. **Warning envelope shape differs from error envelope.** Errors are `{"error": "..."}` but warnings are `{"message": "...", "level": "warn"}`. An agent needs two parse paths. Consider unifying under a single shape like `{"error": ..., "level": "error"|"warn"}` or `{"message": ..., "ok": false}`.
3. **No "did you mean?" on bogus subcommands.** Typer says `No such command 'frobnicate'` but doesn't suggest the closest match. Low priority, but easy to add with `click.suggest_external_cli_plugins` or a Levenshtein check.

## Concrete improvement suggestions

1. **Wrap Typer's error handler to emit JSON on stderr.** Override the Typer/Click exception handler so that even `UsageError` and `NoSuchCommand` exceptions produce `{"error": "No such command 'frobnicate'"}` instead of Rich prose. This would make *every* error path machine-readable.
2. **Unify warning and error envelopes.** Either always use `{"error": "...", "level": "error"|"warn"|"info"}` or have warnings also use the `{"error": ...}` key (with a distinguishing field). Two different shapes for "something didn't go as expected" is unnecessary complexity.
3. **Consider adding a `hint` field for self-correcting errors.** E.g., `{"error": "Invalid priority 99", "hint": "Use 1-4", "valid_values": [1,2,3,4]}`. This would let agents programmatically correct without regex-parsing the error string. Low priority since the current messages are already good.

## Verdict

Excellent error UX for an agent-first CLI. The JSON error envelope on stderr, the self-correcting messages listing valid values, and the clean stdout/stderr separation make this highly automatable. The only real gap is Typer-native errors (bogus subcommands, missing Click-level args) bypassing the JSON envelope and emitting Rich prose instead. Fixing that one issue would give 100% machine-parseable errors across every failure mode. As-is, an agent can handle 13/16 tested cases with a single JSON parse path -- the remaining 3 (Typer errors) need a prose fallback.
