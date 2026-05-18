# JSON-backend mock study — round 2 (post-fix validation)

Same 15 sub-agents, same 15 scenarios, fresh stores, run against master after
shipping the four P0 commits (b1bafb7, f1d66be, a80290a, e25225e). Goal: did
agent experience actually change?

## Verdict deltas

| Agent | Scenario | Round 1 | Round 2 | Delta |
|---|---|---|---|---|
| 01 | Triage + start work | pass | pass | smoother (12 → ~6 cmds) |
| 02 | Create + schedule | pass | pass | flat |
| 03 | Search + chained update | pass | pass | flat |
| 04 | Cross-list sort | **partial** | **pass** | ✅ fixed |
| 05 | Delete by name | pass | pass | flat |
| 06 | Comment audit | pass | pass | flat (N+1 still bites) |
| 07 | Status discovery | pass | pass | flat |
| 08 | Bulk status moves | pass | pass | smoother |
| 09 | Edge-character names | pass | pass | flat |
| 10 | Date filter | pass | pass | one-shot |
| 11 | New list + tasks | **partial** | **pass** | ✅ fixed |
| 12 | Append to description | partial | partial | flat (no --append yet) |
| 13 | Workspace tree | pass | pass | flat |
| 14 | JSON pipeline | pass | pass | smoother |
| 15 | Error shakedown | partial | partial → near-pass | ✅ 6/16 → 13/16 enveloped |

Headline: **2 partials promoted to pass, 1 partial dramatically improved.** No
regressions. No agent reported a new bug that wasn't already friction in round 1.

## What the agents actually felt change

### Confirmed fixes (the P0s landed)

**Agent 04 — cross-list sort works in one command.** "The whole use case
completed in a single command (`task list --all-lists --sort priority`) with
no errors or retries." Last round this exact command was silently broken;
`priority:asc` and `priority:desc` produced identical output. Now `cup task
list --all-lists --sort priority` returns priorities `2, 2, 3, 4, None` in
order, lists interleaved by priority, not bucketed.

**Agent 11 — `list create` + `task create` now share the JSON store.** "The
happy path worked with zero failures in 6 commands... clean experience." Last
round Agent 11 reproduced the half-applied seam: created a list via real
ClickUp API, got "List not found" when adding tasks to it. Round 2 they
created `list_3` in the JSON store and added two tasks to it without leaving
the local store.

**Agent 15 — 13/16 broken commands now emit structured JSON envelopes** (was
6/16 in round 1). Priority 99 → exit 2, JSON envelope, lists valid options
inline. Unknown status → exit 1, JSON envelope, lists valid statuses inline.
Empty name → exit 2, JSON envelope. The "self-correcting messages" line
made it into a positive callout this round.

### Stream-perception mismatch (not actually a bug, but worth knowing)

Three agents (05, 06, 08) report that "info messages still appear on stdout
alongside JSON data." Direct verification (`> stdout 2> stderr`):

```text
=== stdout ===
{"data": [...], "count": 1}
=== stderr ===
{"message": "Found 1 task(s)", "level": "info"}
```

The contract is correct — data on stdout, info on stderr. But by default a
shell merges both into the terminal. An agent looking at "what the CLI
printed" without separating streams perceives them as mixed.

This is a real ergonomic finding even though the pipeline contract is sound.
Two ways to mitigate:

1. **Make info-on-stderr feel less data-shaped.** The current
   `{"message": "...", "level": "info"}` envelope on stderr looks like data
   because it's JSON. Plain prose on stderr in JSON mode would be visually
   distinct.
2. **Document the stream split prominently.** AGENT.md mentions it but the
   `--help` text doesn't. A line in `cup --help` saying "info/warn go to
   stderr in JSON mode" would prime agents to capture them separately.

### Still open (P1+ in issue #29, untouched)

- **`--append-description` missing.** Agent 12 still has to read-modify-write
  to add to a field.
- **No `--open-only` / `--exclude-closed`.** Agents 04, 08, 14 all want
  "everything except closed" without enumerating statuses.
- **`task mine` parity with `task list`.** Agent 01 still wants
  `--status`/`--sort`/`--updated-since` on `mine`.
- **No `--brief`/`--fields` projection.** Agents 01, 04, 07, 12 noted 30+
  fields per task with many nulls is noisy.
- **No batch verb form.** Agent 08 ran `task done` four times instead of
  `task done mock_1002 mock_1004 ...`.
- **`--all-lists` actually means "configured aliases".** Agents 04, 08, 14
  said the name is misleading — they expected workspace-wide.
- **Typer-level errors still leak Rich prose.** Agent 15: `cup frobnicate`
  emits box-drawing characters instead of `{"error": "..."}`. 13 of 16 error
  paths are now uniform; this is the last 3.
- **Comment audit is N+1.** Agent 06 still needed 7 calls (1 list + 5
  per-task fetches) to know which tasks have comments.

### New positive callouts that didn't appear in round 1

- "Self-correcting messages were the standout feature: invalid priority,
  unknown sort field, unknown status, and missing args all include the valid
  values directly in the error string, letting an agent retry without
  consulting `--help`." (Agent 15)
- "`task statuses` discovery command and positional `task status TASK_ID
  STATUS` syntax are well-designed and agent-friendly." (Agent 07)
- "The `--all-lists` + `--sort` combination directly addressed the use
  case." (Agent 04)

## Quantitative

| Metric | Round 1 | Round 2 |
|---|---|---|
| Pass | 11 | 13 |
| Partial | 4 | 2 |
| Fail | 0 | 0 |
| Median commands per scenario | 8 | 6 |
| Scenarios solved in 1–2 commands | 0 | 3 (04, 10, 14) |
| Reports flagging a critical bug | 1 (Agent 11) | 0 |

## Recommendation

The P0 slice paid off — the two partial verdicts most attributable to bugs
(seam half-applied, cross-list sort) flipped to pass, and the error-UX
verdict near-flipped. The remaining open items are ergonomics (P1+ in #29),
not correctness. Worth shipping P1 next iteration if velocity allows; none of
the remaining items are agent-blockers in the way the P0s were.
