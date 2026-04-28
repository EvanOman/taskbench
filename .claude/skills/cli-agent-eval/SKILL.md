---
name: cli-agent-eval
description: Run a fanned-out swarm eval of the ClickUp CLI from an agent's perspective. Dispatches 12 parallel sub-agents, each given a real-world task that exercises a specific behavior. Use when the user asks to evaluate, benchmark, or assess agent-usability of the CLI; or after non-trivial CLI changes to confirm they didn't regress agent ergonomics. Compares results against the baseline captured before the multi-agent refactor.
---

# ClickUp CLI Agent-Usability Eval

This skill is a "poor man's eval" — a fixed set of agent-perspective tasks that were originally hand-run as a research swarm, codified for reuse. Re-run it after CLI changes to see whether agent ergonomics improved or regressed.

## How to invoke

When the user asks for an eval / benchmark / agent-usability check, or right after a substantial CLI change, run the procedure below. **Do not ask which tasks to run** — the suite is fixed.

## Setup checks (do these first, in parallel)

1. Confirm `.env` exists at project root with a real `CLICKUP_API_KEY`. If missing, stop and ask the user to provide one.
2. Confirm uvx works for this project:
   `uvx --python 3.13 --from /home/evan/dev/clickup-tools clickup --help` (Python 3.13 is needed because uvx defaults to 3.14 which has a pydantic-core build issue).
3. Confirm the user's workspace state. Real values for the eval:
   - User: Evan Oman, ID `150240437`, email `evan058@gmail.com`
   - Workspace: `90131945555` ("Evan Oman's Workspace") — singleton
   - Space: `90138201902` ("Team Space")
   - Lists: Omega Point `901315992466` (most active), Personal `901316076590` (use for write tests), Gen Work Overhead `901316076575`, Historical Echoes `901315992464`

## Dispatch the swarm (12 sub-agents in parallel)

Use the Agent tool, `subagent_type: general-purpose`, `model: opus`, single message with 12 tool calls. Each gets the **base prompt** below with the task-specific bit substituted. Run all in **background** if you want to interleave with other work; otherwise foreground.

### Base prompt template

```
You are evaluating whether the ClickUp CLI is easy for a brand-new AI agent to use.

SETUP
- Project root: /home/evan/dev/clickup-tools
- A real CLICKUP_API_KEY is in .env there.
- Invoke the CLI as a real user would: `uvx --python 3.13 --from /home/evan/dev/clickup-tools clickup ...` (Python 3.13 required — pydantic-core build fails on 3.14).
- Both `clickup` and `cup` are valid binary names after install.

HARD CONSTRAINTS
- Do NOT read the CLI's source code. No Read on clickup/cli/* or clickup/core/*. No grep through those dirs.
- Your only docs are `--help` output, the README at /home/evan/dev/clickup-tools/README.md, and trial-and-error.
- Time budget ~5 minutes. If you hit a wall, stop and report.

YOUR TASK
{TASK}

REPORT (under 300 words)
1. Did you succeed? Y / N / Partial. One-line outcome.
2. Verbatim sequence of commands run, in order, with one-line outcome each.
3. Top 3 friction points — be specific (what command, what expected, what got).
4. One concrete suggestion to make this easier for the next agent.
```

### The 12 tasks

| # | Task description (substitute into `{TASK}`) | Probes |
|---|---|---|
| 1 | "Find out who is currently authenticated. Just need their name and email." | identity, status/whoami discovery |
| 2 | "List all the ClickUp teams (workspaces) the user has access to. Report each team's ID and name." | basic read |
| 3 | "Build a tree of the user's workspace: every space, folder, and list under it." | hierarchy navigation |
| 4 | "List tasks currently assigned to the authenticated user." | cross-list filtering, `task mine` discoverability |
| 5 | "Pick any list with tasks and show the 5 most-recently-updated tasks." | sort/order-by discoverability |
| 6 | "Create a new task titled `agent-test-eval-6 hello world` in any list. Report the task ID and URL. Then DELETE it." | create + delete + 204 handling + bracket safety (note: don't use brackets in the name — that was a bug we fixed but verify) |
| 7 | "Create `agent-test-eval-7 update-flow` with description `'original'`. Update ONLY its priority to 2. Re-fetch and verify name and description are unchanged. Then delete the task." | modify-if-passed semantics |
| 8 | "Search the workspace for tasks containing the word 'test'. Report match count and a few examples." | search auto-workspace, semantics |
| 9 | "Pick any task. Get its full details and list its comments. Note every field that comes back." | task get expansion, comments command |
| 10 | "Export tasks from any non-empty list to JSON at /tmp/clickup-export-eval-10.json. Then `head -c 500` to confirm." | bulk export |
| 11 | "Find which list is the user's most active (most tasks / most recent activity). Explain how you decided." | list ranking heuristics |
| 12 | "Run the no-flag flow: end with `clickup task list` working without any flags. If a default isn't set, set one." | onboarding wizard, default resolution |

## Scoring rubric

For each task report, classify the outcome:

- **PASS** — succeeded with ≤4 commands AND no friction worth reporting
- **PARTIAL** — succeeded but with notable friction (>4 commands, or unclear errors, or workarounds)
- **FAIL** — couldn't complete

Then compare to the **baseline** below.

## Baseline (pre-refactor swarm, recorded for comparison)

Captured before the 6-agent refactor (commits `9966d6c` and earlier). 15 friction items found across the original 15-agent run:

| Probe | Baseline issue | Expected post-refactor verdict |
|---|---|---|
| identity (#1) | `status` omitted email; `whoami` didn't exist | resolved (whoami added; status shows email) |
| hierarchy (#3) | spinner bled into stdout; no JSON output | partial — spinner still bleeds in some commands; `--format json` works at top level |
| my tasks (#4) | no `task mine`; required 6+ commands | resolved (`task mine` added) |
| sort (#5) | no `--sort` / `--order-by`; Updated column missing | resolved |
| create (#6) | brackets `[...]` silently stripped from names | resolved (markup escape) |
| update (#7) | modify-if-passed worked; `if X:` truthy bug allowed silent drops on empty values | resolved (CLI uses `is not None`) |
| search (#8) | required `--workspace-id` even with one workspace | partial — auto-detect added but `task search` may still require it |
| task get (#9) | only 10 of ~25 API fields shown; comments unavailable | resolved (D expanded fields; comments commands added) |
| bulk export (#10) | `--format` was freeform TEXT not Choice | resolved |
| most-active (#11) | no `list rank` or activity sort; manual scoring required | NOT addressed — still manual |
| default list (#12) | required 7-step onboarding; no wizard | resolved (`setup` wizard) |
| name aliases | `default_lists` field accepted writes but never read | resolved (C wired resolver) |
| HTTP delete | 204 No Content parsed as error | resolved (B) |
| workspace members | endpoint 404 | resolved (B) |
| timestamps | epoch-ms in all output | resolved (ISO in JSON, human in tables) |
| help discoverability | flat command list, no grouping | resolved (rich panels) |

## Synthesis report + JSON storage

When you dispatch the swarm, **add this clause to each sub-agent's prompt** so the report is parseable:

> "Last lines of your report MUST be a fenced JSON block of the form:
> ```json
> {\"verdict\":\"pass|partial|fail\", \"command_count\": <int>, \"elapsed_seconds\": <int>, \"top_friction\": \"<one sentence>\"}
> ```
> Use the start of your response and the end as your elapsed_seconds estimate (round to whole seconds). command_count is the count of CLI invocations you actually ran (not --help calls)."

After all 12 return, write a markdown summary AND save a structured JSON to `evals/<short-sha>.json` (where `<short-sha>` = `git rev-parse --short HEAD` at eval time). JSON shape:

```json
{
  "commit": "<short-sha>",
  "commit_full": "<full-sha>",
  "timestamp": "<ISO 8601>",
  "summary": {
    "pass": N, "partial": N, "fail": N,
    "total_command_count": N,
    "total_elapsed_seconds": N
  },
  "tasks": [
    {
      "id": 1, "name": "identity",
      "verdict": "pass", "command_count": 7, "elapsed_seconds": 64,
      "top_friction": "whoami at config not top-level"
    },
    ...
  ]
}
```

Markdown report sections (in addition to JSON):

```
# CLI Agent-Usability Eval — <date> @ <short-sha>

## Summary
- Tasks run: 12; Pass N · Partial N · Fail N
- Total commands across all agents: N (delta vs last eval: ±N)
- Total elapsed across all agents: N seconds (delta vs last eval: ±N)

## Per-task results
| # | Task | Verdict | Cmds | Elapsed | Top friction |
|---|------|---------|------|---------|--------------|
...

## Verdict on each baseline issue (comparison table)
...

## New friction discovered
...

## Recommended next moves
- ranked list of 3-5 items
```

If a previous eval JSON exists in `evals/`, compare summary metrics and call out direction (improved / regressed / mixed).

## Cleanup

After the eval, ensure:
- All test tasks created (anything with `agent-test-eval-*` prefix) are deleted from list `901316076590` (Personal). Use `cup task delete <id> --force`.
- `~/.config/clickup-toolkit/config.json` is **not** polluted with eval-leftover values. If task #12's wizard ran against the real config, restore from a backup taken at start, or accept the persisted defaults if they reflect real intent (Omega Point as default, etc.).

## Why this exists

This skill is a regression eval. The original 15-agent swarm surfaced 16 friction items, most of which were addressed in a 6-agent worktree refactor. Re-running this is the cheapest way to confirm fixes stuck and catch new regressions. Each run costs ~12 Opus agent invocations + their tool calls — not free, so don't run it casually.
