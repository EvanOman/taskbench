---
name: cli-agent-eval
description: Run a fanned-out swarm eval of the ClickUp CLI from an agent's perspective. Dispatches 18 parallel sub-agents, each given a real-world task that exercises a specific behavior. Use when the user asks to evaluate, benchmark, or assess agent-usability of the CLI; or after non-trivial CLI changes to confirm they didn't regress agent ergonomics. Compares results against the most recent baseline in evals/.
---

# ClickUp CLI Agent-Usability Eval

A fixed set of agent-perspective tasks, codified for reuse. Re-run after CLI changes to see whether agent ergonomics improved or regressed. The suite measures the CLI, not the sub-agents: every task is something a real coding agent plausibly does for a user, phrased without hints about which commands or flags exist.

**Integrity rule:** when a task fails or shows friction, the fix belongs in the CLI, its docs, or its error messages — never in softening the task prompt, the success criteria, or the grading. Task prompts may only be edited to remove genuine ambiguity, and any such edit must be noted in the run report.

## How to invoke

When the user asks for an eval / benchmark / agent-usability check, or right after a substantial CLI change, run the procedure below. **Do not ask which tasks to run** — the suite is fixed.

## Setup checks (do these first, in parallel)

1. Confirm `.env` exists at project root with a real `CLICKUP_API_KEY`. If missing, stop and ask the user to provide one.
2. **Isolate eval config from real user config.** Run:
   ```bash
   export CLICKUP_CONFIG_PATH="/tmp/clickup-eval-$(date +%s)/config.json"
   mkdir -p "$(dirname "$CLICKUP_CONFIG_PATH")"
   ```
   This uses the `CLICKUP_CONFIG_PATH` env var (honoured by `Config()`) so the eval's setup wizard, `config set-token`, and any other config writes go to a disposable path instead of `~/.config/clickup-toolkit/config.json`. **Pass this env var to every sub-agent prompt** (see base prompt template below).
3. **Pre-warm the uvx wheel cache** so 18 parallel agents don't race the build, and so a stale cached wheel can't shadow current source (uvx caches by name+version — see AGENT.md "Local dev caveat"):
   `uvx --python 3.13 --refresh-package clickup-toolkit --from /home/evan/dev/clickup-tools clickup version`
   Confirm the reported version matches `pyproject.toml`. If it doesn't, the cache is stale — investigate before dispatching.
4. Confirm the user's workspace state. Real values for the eval:
   - User: Evan Oman, ID `150240437`, email `evan058@gmail.com`
   - Workspace: `90131945555` ("Evan Oman's Workspace") — singleton
   - Space: `90138201902` ("Team Space")
   - Lists: Omega Point `901315992466`, Personal `901316076590` (**use for all write tests**), Gen Work Overhead `901316076575`, Historical Echoes `901315992464`

## Dispatch the swarm (18 sub-agents in parallel)

Use the Agent tool, `subagent_type: general-purpose`, `model: opus`, single message with 18 tool calls. Each gets the **base prompt** below with `{TASK}` and `{CLICKUP_CONFIG_PATH}` substituted.

### Base prompt template

```
You are evaluating whether the ClickUp CLI is easy for a brand-new AI agent to use. You have never seen this CLI before. Behave like a competent coding agent doing a real job for a user — not like a QA engineer hunting for bugs.

SETUP
- Project root: /home/evan/dev/clickup-tools
- A real CLICKUP_API_KEY is in .env there.
- Invoke the CLI as a real user would: `uvx --python 3.13 --from /home/evan/dev/clickup-tools clickup ...` (Python 3.13 required — pydantic-core build fails on 3.14).
- Both `clickup` and `cup` are valid binary names after install.
- IMPORTANT: Before running any CLI command, export the isolated config path so your writes don't pollute the user's real config:
  `export CLICKUP_CONFIG_PATH="{CLICKUP_CONFIG_PATH}"`

HARD CONSTRAINTS
- Do NOT read the CLI's source code. No Read on clickup/cli/* or clickup/core/*. No grep through those dirs. No reading AGENT.md or CLAUDE.md.
- Your only docs are `--help` output, the README at /home/evan/dev/clickup-tools/README.md, and trial-and-error.
- If you create anything, you must also clean it up (delete it / restore original state) before finishing, and say so in your report.
- Time budget ~5 minutes. If you hit a wall, stop and report honestly — a truthful FAIL is more valuable than a flattering PARTIAL.

YOUR TASK
{TASK}

REPORT (under 350 words)
1. Did you succeed? Y / N / Partial. One-line outcome.
2. Verbatim sequence of CLI commands run, in order, with one-line outcome each. Include failed attempts — they are data, not embarrassment. Mark `--help` calls as (help).
3. Top friction points (up to 3) — be specific: what you ran, what you expected, what you got.
4. One concrete suggestion to make this easier for the next agent.

Last lines of your report MUST be a fenced JSON block:
```json
{"verdict":"pass|partial|fail", "command_count": <int>, "help_count": <int>, "elapsed_seconds": <int>, "cleanup_done": true|false, "top_friction": "<one sentence>"}
```
command_count = CLI invocations that did real work (exclude --help calls; count failed attempts). help_count = --help invocations. elapsed_seconds = rough wall-clock estimate. cleanup_done = whether you deleted/restored everything you created (true if you created nothing).
```

### The 18 tasks

| # | Task description (substitute into `{TASK}`) | Probes |
|---|---|---|
| 1 | "Find out who is currently authenticated. Just need their name and email." | identity discovery |
| 2 | "List all the ClickUp teams (workspaces) the user has access to. Report each team's ID and name." | basic read |
| 3 | "Build a tree of the user's workspace: every space, folder, and list under it." | hierarchy navigation |
| 4 | "List tasks currently assigned to the authenticated user." | `task mine` discoverability |
| 5 | "Pick any list with tasks and show the 5 most-recently-updated tasks." | sort discoverability |
| 6 | "Create a new task titled `agent-test-eval-6 hello world` in the list with ID 901316076590. Report the task ID and URL. Then DELETE it." | create + delete |
| 7 | "Create a task named `agent-test-eval-7 update-flow` with description `original` in list 901316076590. Update ONLY its priority to 2. Re-fetch and verify name and description are unchanged. Then delete the task." | modify-if-passed |
| 8 | "Search the workspace for tasks containing the word 'test'. Report the match count and three example titles." | search |
| 9 | "Pick any existing task. Get its full details and list its comments. Report which fields came back." | task get expansion, comments read |
| 10 | "Export tasks from any non-empty list to JSON at /tmp/clickup-export-eval-10.json. Then `head -c 500` the file to confirm." | export |
| 11 | "Find which list is the user's most active (most tasks and most recent activity). Explain how you decided." | list-level stats |
| 12 | "Starting from zero configuration, end with `clickup task list` working without any flags. If a default isn't set, set one using only non-interactive commands." | onboarding, default resolution |
| 13 | "Pick any task in list 901316076590. Find out which statuses are valid for that list, move the task to a different valid status, verify the change, then move it back to its original status." | status discovery + transition |
| 14 | "Create three tasks named `agent-test-eval-14-a`, `agent-test-eval-14-b`, `agent-test-eval-14-c` in list 901316076590. Then, in as few commands as possible, mark all three complete, verify, and delete all three." | batch ops over explicit IDs |
| 15 | "Report all open (not closed/done) tasks in list 901316076575 that were updated in the last 30 days, sorted most-recently-updated first. Give the count and the titles." | date filters, open-only, sort |
| 16 | "Create a task named `agent-test-eval-16 comment-flow` in list 901316076590, add the comment `status: looking into it`, read the comments back to verify, then delete the task." | comment write + read round-trip |
| 17 | "Try to fetch a task with ID `doesnotexist123`. Then create a task named `agent-test-eval-17 err-probe` in list 901316076590 and try to delete it WITHOUT any confirmation/force flags; note what happens; then delete it properly. For each error you encountered: report exactly what the CLI said (message, where it printed, exit code) and whether that output alone told you how to proceed without consulting --help." | error quality: envelopes, exit codes, actionability |
| 18 | "Using only CLI commands, configure a list alias named `inbox` that points to list 901316076590, then list that list's tasks via the alias. Finally remove the alias you added." | alias configuration + use |

## Grading — the dispatcher assigns final verdicts

Sub-agent self-verdicts are input, not the result. After all reports return, **you** (the dispatcher) grade each task from its command transcript against the criteria below. Where your grade differs from the self-verdict, note why.

**Verdicts:**
- **PASS** — goal fully achieved; ≤6 working CLI invocations (excluding `--help`); no manual workaround for something the CLI should do (e.g., piping JSON to python to filter/sort when a flag exists or should exist); no misleading error encountered; cleanup done.
- **PARTIAL** — goal achieved but with a workaround, >6 working invocations, a misleading/opaque error along the way, or incomplete cleanup.
- **FAIL** — goal not achieved within budget.

**Per-task success criteria:**

| # | Must be true for PASS |
|---|---|
| 1 | Correct name + email reported |
| 2 | Workspace ID + name reported |
| 3 | All spaces and all 4+ lists enumerated with IDs |
| 4 | Assigned-task query executed successfully (an empty result is still a pass — workspace state varies) |
| 5 | 5 tasks in correct updated-desc order |
| 6 | ID + URL reported; task verifiably deleted |
| 7 | Re-fetch shows name and description unchanged, priority 2; task deleted |
| 8 | Count + 3 example titles from a workspace-wide search (not a single-list grep) |
| 9 | Full field inventory + a comments read (empty list OK) |
| 10 | File exists, valid JSON, >0 tasks |
| 11 | A defensible answer naming one list, justified by both task count and recency, without hand-rolling JSON post-processing |
| 12 | Final bare `clickup task list` exits 0 with task data; no interactive prompts used |
| 13 | Valid statuses enumerated via the CLI (not guessed); both transitions verified; original status restored |
| 14 | All three closed AND deleted via batched commands (one command per operation type, not per task) |
| 15 | Filtering and sorting done by CLI flags, not manual post-processing; count + titles reported |
| 16 | Comment text read back verbatim; task deleted |
| 17 | Both errors structured (stderr, correct exit codes: 1 runtime / 2 usage), and agent judged them actionable without --help |
| 18 | Alias works for task listing; alias removed afterwards |

## Synthesis report + JSON storage

After grading, write a markdown summary AND save structured JSON to `evals/<short-sha>.json` (`<short-sha>` = `git rev-parse --short HEAD`). If that file already exists for the same sha (re-run), suffix `-r2`, `-r3`, ....

JSON shape:

```json
{
  "commit": "<short-sha>",
  "commit_full": "<full-sha>",
  "timestamp": "<ISO 8601>",
  "suite_version": 2,
  "summary": {
    "pass": N, "partial": N, "fail": N,
    "total_command_count": N,
    "total_elapsed_seconds": N
  },
  "tasks": [
    {
      "id": 1, "name": "identity",
      "verdict": "pass", "self_verdict": "pass",
      "command_count": 1, "elapsed_seconds": 30,
      "top_friction": "<one sentence>"
    }
  ]
}
```

`suite_version: 2` marks the 18-task suite (v1 = the original 12 tasks; totals are not directly comparable across versions — compare per-task and pass-rate instead).

Markdown report sections:

```
# CLI Agent-Usability Eval — <date> @ <short-sha> (suite v2)

## Summary
- Tasks run: 18; Pass N · Partial N · Fail N
- Pass rate vs previous run: ±
- Total commands / elapsed (with per-suite-version caveat)

## Per-task results
| # | Task | Verdict | Self | Cmds | Elapsed | Top friction |

## Grade overrides (dispatcher vs self-verdict, with reasons)

## New friction discovered

## Recommended next moves (ranked, ≤5)
```

If previous eval JSONs exist in `evals/`, compare per-task verdicts for tasks 1–12 and call out direction (improved / regressed / mixed).

## Cleanup

After the eval:
- Verify no `agent-test-eval-*` tasks remain in list `901316076590` (Personal): `cup --format json task list --list-id 901316076590` and check; delete leftovers with `cup task delete --task-ids ... --force`.
- Verify no stray `inbox` alias or other config leaked into the REAL user config (`~/.config/clickup-toolkit/config.json`) — it shouldn't have, thanks to `CLICKUP_CONFIG_PATH`.
- Remove the disposable eval config dir: `rm -rf "$(dirname "$CLICKUP_CONFIG_PATH")"`.
- Remove `/tmp/clickup-export-eval-10.json`.

## Result history

| Run | Suite | Commit | Pass/Partial/Fail | Notes |
|---|---|---|---|---|
| 2026-05 (baseline) | v1 (12) | `b8bb6b8` | 10/2/0 | pre-refactor friction batch |
| 2026-06-11 | v1 (12) | `a22824e` | 11/1/0 | post batches A–G; cmds 84→41 |

Append a row after every run.

## Why this exists

This is a regression eval. The original swarm surfaced 16 friction items; subsequent refactors addressed them, and this suite is the cheapest way to confirm fixes stuck and catch new regressions. Each run costs ~18 Opus agent invocations + tool calls — not free, so don't run it casually.
