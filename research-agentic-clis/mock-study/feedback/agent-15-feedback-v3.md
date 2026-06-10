# Agent 15 Report (v3)

## Use case

Error-mode shakedown (round 3).

## Transcript

| # | Command | Exit | Channel | Error shape | Recoverable? |
|---|---------|------|---------|-------------|--------------|
| 1 | `task update mock_9999 --name "x"` | 0 | stderr | `{"error": "...", "type": "NotFoundError"}` | Yes |
| 2 | `task status mock_9999 done` | 0 | stderr | `{"error": "... (mock_9999): ...", "type": "NotFoundError"}` | Yes |
| 3 | `task create "x" --list-id totally_fake_list` | 0 | stderr | `{"error": "...", "type": "NotFoundError"}` | Yes |
| 4 | `task update mock_1001 --priority 99` | 0 | stderr | `{"error": "..."}` (no `type`) | Yes |
| 5 | `task list --list-id inbox --sort fartfield` | 0 | stderr | `{"error": "..."}` (no `type`) | Yes |
| 6 | `task create "" --list-id inbox` | 0 | stderr | `{"error": "..."}` (no `type`) | Yes |
| 7 | `task status mock_1001 "totally-not-a-status"` | 0 | stderr | `{"error": "...", "type": "ValidationError"}` | Yes |
| 8b | `task list` (no default list in config) | 0 | stderr | `{"error": "...", "hint": "..."}` (no `type`) | Yes |
| 9 | `frobnicate` (bad subcommand) | **2** | stderr | `{"error": "...", "type": "UsageError", "command": "clickup"}` | Yes |
| 10 | `task list --list-id inbox --limit abc` | **2** | stderr | `{"error": "...", "type": "BadParameter", "command": "clickup task list"}` | Yes |
| 11 | `task done` (zero IDs) | **2** | stderr | `{"error": "...", "type": "MissingParameter", "command": "clickup task done"}` | Yes |
| 12 | `task done mock_1001 mock_9999` (batch) | 0 | stdout: success for mock_1001; stderr: error for mock_9999 | Mixed: stdout `{"data":[...]}`, stderr `{"error":"...","type":"NotFoundError"}` | Yes |
| 13b | `task update mock_1001` (no fields) | 0 | stderr | `{"message": "No updates specified.", "level": "warn"}` | Yes |
| 13c | `task get mock_9999` | 0 | stderr | `{"error": "...", "type": "NotFoundError"}` | Yes |
| 13d | `task delete mock_1001` (no --force) | 0 | stderr | `{"error": "Refusing to delete without --force/--yes ..."}` (no `type`) | Yes |

## What worked well

1. **All errors are JSON on stderr; stdout stays clean.** An agent with a single parse path (`JSON.parse(stderr)`) can detect every failure. No Rich formatting leaks into error output.
2. **Typer-level errors (tests 9, 10, 11) get a proper JSON envelope** with `type` + `command` fields and exit code 2. This is excellent -- many CLIs dump raw Click prose here.
3. **Batch partial-failure (test 12) is handled perfectly.** The successful task appears on stdout as normal `{"data":[...]}`, the failure goes to stderr as a JSON error. An agent can parse both streams independently.
4. **Error messages are actionable** -- they name the invalid value, list valid options (sort fields, statuses, priorities), and include task IDs in context.
5. **`hint` field in test 8b** is a nice touch for agent self-correction.
6. **Warning (test 13b)** uses `{"message", "level": "warn"}` -- distinct from errors, not alarming.

## Friction / surprises / broken things

1. **EXIT CODE BUG: Application-level errors all exit 0.** Tests 1-8b, 12, 13b-13d all exit 0 despite clearly being errors. Only Typer-native errors (9, 10, 11) exit non-zero. AGENT.md states errors should exit 1 (API/runtime) or 2 (usage). An agent checking `$?` cannot distinguish success from failure.
2. **Inconsistent envelope shape.** Three distinct shapes appear:
   - API errors: `{"error", "type"}` -- good
   - CLI validation errors (4, 5, 6, 8b, 13d): `{"error"}` only, sometimes `{"error", "hint"}` -- missing `type`
   - Warnings: `{"message", "level"}` -- different top-level key
   - Typer errors: `{"error", "type", "command"}` -- extra `command` field

   An agent needs `if "error" in obj or "message" in obj` -- two key checks instead of one.
3. **Test 2 vs Test 1 inconsistency.** `task update` says "Task not found: mock_9999" but `task status` says "(mock_9999): Task not found: mock_9999" -- the task ID prefix is inconsistent between commands for the same underlying error.
4. **No `type` on CLI-validation errors.** Tests 4 (bad priority), 5 (bad sort), 6 (empty name), 8b (no list), 13d (no --force) lack a `type` field. An agent wanting to distinguish "re-tryable API error" from "fix your arguments" cannot do so reliably for these cases.

## Concrete improvement suggestions

1. **Fix exit codes.** `render_error()` + `raise typer.Exit(code=N)` should be the only path. Application validation errors should exit 2; API/runtime errors should exit 1. This is the single most important fix for agent consumption.
2. **Always include `type` in the error envelope.** Define a small enum: `UsageError`, `ValidationError`, `NotFoundError`, `AuthError`, `RefusalError`. CLI validation (bad priority, bad sort, empty name, no --force) should use `ValidationError` or `UsageError`.
3. **Normalize the task-ID prefix.** Either always include `(task_id):` or never -- pick one and apply consistently.
4. **Consider a `"success": false` top-level field** for all error envelopes, making the single-parse-path even simpler: `obj.get("success", True)`.

## Verdict

**partial**

The JSON-on-stderr design is solid and agent-recoverable. The fatal flaw is that exit codes are universally 0 for application-level errors, making it impossible for an agent to detect failure without parsing stderr. The envelope shape inconsistency (missing `type` on half the errors) is a secondary issue. Fix the exit codes and this passes cleanly.
