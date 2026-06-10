# JSON-backend mock study — round 3 (full end-to-end validation)

Same 15 sub-agents, same scenarios as rounds 1 and 2 (Agent 11's scenario
extended to include the new `folder create`), fresh stores, run against
master @ `6cb8f67` — after all P0/P1/P2/P3 work from issue #29 landed.

## Verdict trajectory

| Agent | Scenario | R1 | R2 | R3 |
|---|---|---|---|---|
| 01 | Triage + start work | pass | pass | pass |
| 02 | Create + schedule | pass | pass | pass (3 cmds) |
| 03 | Search + chained update | pass | pass | pass |
| 04 | Cross-list open/priority view | **partial** | pass | **pass — one command** |
| 05 | Delete by name | pass | pass | pass |
| 06 | Comment audit | pass | pass | **pass — 1 data call (was 7)** |
| 07 | Status discovery | pass | pass | pass (3 cmds) |
| 08 | Bulk status moves | pass | pass | **pass — 3 ops, variadic done** |
| 09 | Edge-character names | pass | pass | pass |
| 10 | Date filter | pass | pass | pass |
| 11 | New folder + list + tasks | **partial** | pass | **pass — full hierarchy, 4 creates, 0 errors** |
| 12 | Append to description | partial | partial | **pass — 2 cmds via --description-append** |
| 13 | Workspace tree | pass | pass | pass (flagged depth default) |
| 14 | JSON pipeline | pass | pass | pass — "clean JSON, piped directly" |
| 15 | Error shakedown | partial | partial | **partial → pass after fix** (see below) |

**Round 3: 14 pass, 1 partial → 15/15 pass after the exit-code fix.**
(R1: 11/4/0. R2: 13/2/0.)

## The big catch: exit codes were broken — and only this study found it

Agent 15 discovered that **every application-level error exited 0** through
the real entry point: NotFound, validation failures, --force refusals — all
of them. Only Click-native parse errors exited nonzero.

Root cause: PR #33 switched `main()` to `app(standalone_mode=False)` so
Click parse errors could be wrapped in the JSON envelope. But in
non-standalone mode, Click catches `typer.Exit` raised during command
invoke and **returns** the exit code from `app()` instead of raising.
`main()` discarded that return value and fell through to exit 0.

Why 504 tests missed it: every CLI test uses Typer's `CliRunner`, which
invokes `app` directly and never goes through `main()`. The unit tests
added with PR #33 covered only the Click-parse-error paths (which raise,
not return). The blind spot was exactly the seam between the test harness
and the real process boundary.

Fixed in `862feea`: `main()` propagates a nonzero int return as
`sys.exit`, plus three regression tests that drive `main()` end-to-end
against a seeded JSON store via monkeypatched `sys.argv` +
`CLICKUP_CONFIG_PATH`. Agent 15's re-run (v3b): **13/13 exit codes
correct**, verdict pass — "An agent can reliably branch on `$?` (0/1/2)
and parse stderr JSON via `.error` for all failure modes."

This is the strongest argument for re-running the study after every
change wave: a process-boundary regression that an entire green test
suite, three reviewer agents, and two manual smoke sessions all missed
fell out of one adversarial agent checking `$?`.

## Confirmed wins (features shipped since round 2, observed in the wild)

- **`comment_count`** turned Agent 06's 7-call audit into **1 data call**
  ("a standout ergonomic design choice").
- **`folder create`** let Agent 11 build folder → list → 2 tasks in 4
  commands with zero errors (round 1: hard failure; round 2: worked only
  by routing around the missing command).
- **`--description-append`** flipped Agent 12's verdict to pass after
  three rounds: 2 commands, "the CLI had exactly the right primitive."
- **Variadic `task done`** + `--status` filter + `--brief` composed into
  Agent 08's 3-operation bulk flow.
- **`task mine --open-only --sort priority --brief`** solved Agent 04's
  whole scenario in **one command** (round 1: broken; round 2: workable).
- **Batch partial-failure** earned an unprompted "excellent" from
  Agent 15: successes on stdout, failures on stderr, independently
  parseable.

## Fixed during this round (from v3 feedback)

- Exit-code propagation in `main()` (`862feea`, above).
- `_usage_error` and every `--force` refusal now carry
  `type: "UsageError"` — envelope shape is now uniform across all error
  classes (`a2553e1`).
- `discover hierarchy` default depth 3 → 5: depth 3 stopped at folders
  and returned empty `"lists": []` arrays that read as genuinely empty
  folders (Agent 13). Help text documents the level meanings (`862feea`).
- `PlankaProvider.create_folder` added — the Protocol gained the method
  in parallel with the Planka adapter PR and master CI went red on the
  type check; the adapter now refuses with a ValidationError since
  Planka has no folder concept (`a2553e1`).

## Recurring perception finding (third round)

Agents 04, 05, 06, and 08 again reported "info messages on stdout
alongside JSON." Stream-separated verification (round 3, same as round
2): stdout is a single valid JSON document; the info envelope is on
stderr. Agents conflate the streams because they read merged terminal
output. Three rounds in a row means the perception is itself the
ergonomic fact: as long as info messages on stderr *look like data*
(JSON-shaped), agents will report them as contamination. Options if it
keeps burning attention: drop info messages entirely in JSON mode (the
data envelope already carries `count`), or switch stderr commentary to
plain prose.

## Remaining small items (none load-bearing)

- `task search` lacks `--sort`/`--status`/time filters — repeatedly the
  asymmetric corner of the filter matrix (Agents 04, 08, 10).
- `folder get` shows an empty `lists` array even when children exist;
  folder `task_count` doesn't roll up (Agents 11, 13).
- `bulk bulk-update` lacks `--all-lists` (Agent 08's "single invocation"
  wish).
- `list show` naming asymmetry vs `folder list`/`task list` (Agent 11).
- Mock seed config lacks `default_status`, so the on-deck default
  documented in the user's CLAUDE.md doesn't apply in studies
  (Agents 02, 09).

## Quantitative

| Metric | R1 | R2 | R3 |
|---|---|---|---|
| Pass / partial / fail | 11/4/0 | 13/2/0 | 14/1/0 → 15/0/0 post-fix |
| Median commands per scenario | 8 | 6 | ~4 |
| Scenarios solved in 1–2 substantive commands | 0 | 3 | 6 (02, 04, 06, 07, 10, 12) |
| Critical bugs found | 1 (seam) | 0 | 1 (exit codes) |

## Takeaway

The interface work has converged: every scenario passes, median command
count halved twice, and six scenarios are now one-or-two-command flows.
The round-3 catch (exit codes) validates the study loop itself — the
adversarial error-shakedown agent is the highest-value seat in the
study and should run after any change to the entry point or error
handling, even when the suite is green.
