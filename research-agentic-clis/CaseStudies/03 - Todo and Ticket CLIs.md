---
tags:
  - ai-generated
  - agentic-cli
  - todo-cli
---

# Todo and Ticket CLIs

## Executive Summary

Strong task and ticket CLIs converge on a small set of patterns: stable selectors, explicit state-changing verbs, composable filters, and machine-readable output that preserves identifiers. Taskwarrior is the strongest example for personal task queues because it treats filters and modifications as first-class grammar rather than one-off flags. GitHub CLI and GitLab `glab` are better examples for agent-facing ticket systems because their commands expose repository selectors, JSON fields, and predictable object subcommands. For `clickup-tools`, the product lesson is to design for agent reliability first: one canonical update surface, consistent JSON for every mutation, named saved queries, and no invented workflow semantics that ClickUp itself does not store.

## What "Agentic" Means For This CLI

For human CLIs, discoverability and terseness matter. For LLM agents, the winning properties are different:

- A command should be reconstructable from help text without hidden UI state.
- Selectors should be stable across sessions: task IDs, URLs, list IDs, saved aliases, and explicit filters.
- Mutations should be idempotent or at least explicit enough that an agent can reason about what will change.
- Output should be structured by default or easy to request with one global flag.
- Errors should be parseable and should name missing configuration, ambiguous selectors, or invalid transitions.

The strongest tools in this survey generally have a clean split between "find the thing", "inspect the thing", and "change the thing". The weak points show up when CLIs optimize for interactive use: prompts, TUI views, implicit current project context, and prose-only success messages.

## Case Study: Taskwarrior

Taskwarrior is the most mature command grammar for a personal to-do queue. Its syntax is not built around object subcommands like `task issue update`; instead, it composes four parts: filters, command, modifications, and miscellaneous arguments. The official syntax page states that "there are four parts to the syntax (`filter`, `command`, `modifications`, and `miscellaneous`)" and shows examples like `task +home list` and `task 12 modify project:Garden` [Taskwarrior syntax](https://taskwarrior.org/docs/syntax/).

This grammar is powerful for agents because selection and mutation are separate but adjacent:

```bash
task +home status:pending list
task 12 modify project:Garden due:tomorrow +errand
task project:outdoors and /planting/ modify -home +garden
```

The design lesson is not to copy the exact syntax. Taskwarrior's free-form filter language can be hard for an agent to generate safely. The lesson is that a task CLI should have a real query model, not just a growing list of special cases. Filters should be reusable across commands, and the same selector should work for `list`, `count`, `export`, and carefully bounded updates.

Taskwarrior also has an unusually good distinction between stored metadata and derived query conveniences. Plain tags use `+TAG` and `-TAG` for presence and absence, while virtual tags expose computed state such as `BLOCKED`, `WAITING`, `READY`, `PENDING`, `COMPLETED`, and `OVERDUE` [Taskwarrior tags](https://taskwarrior.org/docs/tags/). This is valuable for ClickUp because we should not force the user to store a `ready` field just to query "not done, not blocked, not waiting". Some filters can be derived from native ClickUp fields and local configuration.

Taskwarrior's waiting/blocking model also clarifies a product boundary. `WAITING` is a computed tag for tasks hidden by a wait date; `BLOCKED` is computed from dependencies [Taskwarrior tags](https://taskwarrior.org/docs/tags/). That maps to our earlier conclusion: a `waiting on` board or list should not be assumed. If ClickUp has native dependencies, use them. If it does not have native external blockers, do not invent storage.

The main caution is bulk mutation. Taskwarrior's `modify` docs note that changing more than three tasks triggers confirmation by default, and warn that unbounded filters can change completed and deleted tasks if `status:pending` is omitted [Taskwarrior modify](https://taskwarrior.org/docs/commands/modify/). Agents need the same guardrails, but in non-interactive form:

```bash
cup task update --query "status=on-deck tag=review" --status "in progress" --dry-run
cup task update --query "status=on-deck tag=review" --status "in progress" --expect-count 2
```

Taskwarrior also has a strong export story. `task export` accepts a filter and emits JSON, with one object per task or a JSON array depending on configuration [Taskwarrior export](https://taskwarrior.org/docs/commands/export/). For agents, this suggests that `clickup-tools` should make every list-like query exportable as JSON without changing the query semantics:

```bash
cup task list --mine --status open --json
cup task export --query ready --format jsonl
```

## Case Study: GitHub CLI (`gh`)

GitHub CLI is probably easy for models because both things are true: it has good design, and it appears heavily in training data. The design is object-oriented and predictable:

```bash
gh issue list --assignee @me --label bug --state open
gh issue view 123 --json number,title,labels,state,url
gh issue edit 123 --add-label "bug,help wanted" --remove-label "needs triage"
gh issue close 123
```

The issue command group is organized around nouns and verbs: `create`, `list`, `status`, `view`, `close`, `comment`, `edit`, `reopen`, and so on [GitHub CLI issue manual](https://cli.github.com/manual/gh_issue). This matters for agents because command intent is visible in the command path. `gh issue edit 23 --add-label bug` is more reliable to synthesize than a generic `gh api` call or a natural-language command.

The strongest piece is JSON field selection. `gh issue list` supports `--json <fields>`, `--jq <expression>`, `--template`, `--limit`, `--state`, `--search`, labels, assignees, authors, and milestones [GitHub CLI issue list](https://cli.github.com/manual/gh_issue_list). The manual lists JSON fields such as `assignees`, `author`, `body`, `createdAt`, `id`, `labels`, `number`, `state`, `title`, `updatedAt`, and `url` [GitHub CLI issue list](https://cli.github.com/manual/gh_issue_list). The formatting docs explain that `--json` requires a comma-separated field list and that `--jq` can transform the JSON without requiring the system `jq` binary [GitHub CLI formatting](https://cli.github.com/manual/gh_help_formatting).

This pattern is highly relevant:

```bash
cup task list --json id,name,status,list,assignees,url,updated_at
cup task view abc123 --json id,name,description,status,custom_fields,url
cup task list --json id,name,status --jq '.[] | select(.status == "on-deck")'
```

The "field list" model is better than dumping huge task objects every time. Agents often need just ID, title, status, URL, and updated timestamp. Smaller structured output reduces context cost and hallucinated field names.

`gh issue edit` also has a useful mutation model: one command can change title/body/milestone and add or remove labels, assignees, and projects [GitHub CLI issue edit](https://cli.github.com/manual/gh_issue_edit). That supports an "update surface" design:

```bash
cup task update TASK_ID \
  --name "Review ClickUp CLI JSON behavior" \
  --status "in progress" \
  --add-tag agentic-cli \
  --remove-tag stale \
  --assignee me
```

The notable limitation is that GitHub state is simple: open or closed. ClickUp status is workspace-specific. For ClickUp, a generic `close` command may not be enough; agents need status discovery and aliases:

```bash
cup status list --list LIST_ID --json
cup task status TASK_ID done
cup config set status.done "complete"
```

## Case Study: GitLab CLI (`glab`)

`glab` closely resembles `gh`, but it exposes several useful issue-tracker details that GitHub issues do not. `glab issue list` defaults to open issues, supports group or repository scope, and has filters for assignee, author, label, milestone, issue type, iteration, epic, search fields, sorting, pagination, and output [GitLab issue list](https://docs.gitlab.com/cli/issue/list/). It also distinguishes machine-readable output from compact human output: `--output text|json` and `--output-format details|ids|urls` [GitLab issue list](https://docs.gitlab.com/cli/issue/list/).

That split is a good lesson. Agents often need either full JSON or just IDs:

```bash
cup task list --status "to do" --output json
cup task list --status "to do" --output ids
cup task list --status "to do" --output urls
```

The `ids` and `urls` formats are especially useful for shell composition and for passing task selections between agent steps without preserving a giant JSON blob.

`glab issue create` is also instructive because it is non-interactive when given sufficient flags, but can still support interactive creation for humans. It accepts title, description, assignees, labels, due date, epic, milestone, linked issues, linked merge request, time estimate, time spent, template, web continuation, and `--yes` to skip confirmation [GitLab issue create](https://docs.gitlab.com/cli/issue/create/). This is a good shape for `clickup-tools`: do not remove human-friendly prompting if it already exists, but give agents a complete non-interactive path.

`glab issue update <id>` provides another concrete update model. Assignee updates can add, remove, or replace depending on prefixes, while labels have explicit add and remove flags [GitLab issue update](https://docs.gitlab.com/cli/issue/update/). This is a place where ClickUp should be more explicit than clever. Prefix semantics like `+user` and `-user` are compact for humans but easy for agents to misuse. Prefer flags:

```bash
cup task update TASK_ID --add-assignee evan
cup task update TASK_ID --remove-assignee evan
cup task update TASK_ID --set-assignees evan,alex
```

`glab issue close` and `glab issue view` show a clean selector model: an issue can be selected by ID or full URL, and repository context is controlled by `-R/--repo` [GitLab issue close](https://docs.gitlab.com/cli/issue/close/), [GitLab issue view](https://docs.gitlab.com/cli/issue/view/). ClickUp should accept both task IDs and URLs wherever possible:

```bash
cup task view 86a123
cup task view https://app.clickup.com/t/86a123
cup task update https://app.clickup.com/t/86a123 --status done
```

## Case Study: Jira CLI Variants

Jira is useful because it has the same hard problem as ClickUp: workflow status is not globally standardized. The Atlassian CLI (`acli`) exposes this directly. `acli jira workitem search` searches by JQL or saved filter, can select fields, supports CSV or JSON output, supports limits and pagination, and can open the search in the browser [Atlassian CLI search](https://developer.atlassian.com/cloud/acli/reference/commands/jira-workitem-search/). `acli jira workitem transition` changes status by keys, JQL query, or filter ID, and has `--json`, `--yes`, and `--ignore-errors` [Atlassian CLI transition](https://developer.atlassian.com/cloud/acli/reference/commands/jira-workitem-transition/).

The design insight is that query selectors and mutation selectors can be the same:

```bash
acli jira workitem transition --key "KEY-1,KEY-2" --status "Done"
acli jira workitem transition --jql "project = TEAM" --status "In Progress"
acli jira workitem transition --filter 10001 --status "To Do" --yes
```

For ClickUp, the equivalent should exist only with guardrails:

```bash
cup task update TASK_ID --status done
cup task update --filter ready --status "in progress" --dry-run
cup task update --filter ready --status "in progress" --expect-count 1
```

The strongest third-party Jira CLI in this survey is `ankitpokhrel/jira-cli`. Its `issue list` command supports direct flags for priority, status, created/updated windows, labels, assignee, reporter, project, history, raw JQL, ordering, reverse sorting, plain output, raw JSON, and CSV [ankitpokhrel/jira-cli](https://github.com/ankitpokhrel/jira-cli). Its examples include recurring high-value queries such as:

```bash
jira issue list -a$(jira me)
jira issue list -s~Done --created-before -24w -a~x
jira issue list --created -1h --updated -30m
jira issue list -yHigh -s"In Progress" --created month -lbackend -l"high-prio"
```

This is one of the best examples of a CLI that is both expressive and task-oriented. It has human-friendly shortcuts like `$(jira me)` and relative time windows such as `--created week`, `--updated -30m`, and `--created-before -24w`. For short-horizon personal queues, these are more useful than elaborate blocker metadata:

```bash
cup task list --mine --updated-since -2d
cup task list --created today
cup task list --status-not done --assignee me
cup task list --stale 3d
```

`jira-cli` also separates state movement into `jira issue move ISSUE-1 "In Progress"` and supports comment, resolution, and assignment during transition where the workflow allows it [ankitpokhrel/jira-cli](https://github.com/ankitpokhrel/jira-cli). That suggests a useful ClickUp shape:

```bash
cup task move TASK_ID "in progress"
cup task move TASK_ID done --comment "Implemented and verified"
```

However, `move` and `update --status` should probably be aliases over the same implementation. Agents do better with one canonical command, plus aliases for humans.

`jira-cli` also supports links and remote web links: `jira issue link ISSUE-1 ISSUE-2 Blocks` and `jira issue link remote ISSUE-1 https://example.com "Example text"` [ankitpokhrel/jira-cli](https://github.com/ankitpokhrel/jira-cli). This is relevant to the closed "waiting on PR" idea. Jira has a native remote link concept; ClickUp may not have a first-class equivalent for arbitrary blocker URLs. The product rule should be: expose native relationships, but do not store invented relationships unless the user explicitly configures the storage.

## Case Study: Linear MCP and Linear-Style Update Surfaces

Linear's official MCP docs are important because they explicitly position MCP as a standardized interface for AI models and agents to access Linear data [Linear MCP docs](https://linear.app/docs/mcp). The docs say the server has tools for finding, creating, and updating Linear objects like issues, projects, and comments [Linear MCP docs](https://linear.app/docs/mcp). Linear's official GraphQL API uses mutations such as `issueCreate` and `issueUpdate`; `issueUpdate` can update fields like title and state using an issue UUID or shorthand ID such as `BLA-123` [Linear developer docs via Context7, source: https://linear.app/developers/graphql](https://linear.app/developers/graphql).

The attractive pattern here is not command-line syntax; it is the tool interface:

```json
{
  "issueId": "ENG-123",
  "title": "Updated title",
  "description": "New markdown body",
  "status": "In Progress",
  "priority": 2,
  "assignee": "me",
  "labelIds": ["bug", "urgent"]
}
```

This is close to ideal for agents. There is one update operation with many optional properties, and only the provided properties change. That maps cleanly to a CLI:

```bash
cup task update TASK_ID \
  --name "Updated title" \
  --description-file body.md \
  --status "in progress" \
  --priority high \
  --assignee me \
  --add-tag bug
```

For `clickup-tools`, this argues against many narrow mutation commands unless they are aliases. `task rename`, `task assign`, and `task status` may be convenient, but the canonical agent interface should be `task update`.

## Case Study: Todoist

Todoist is relevant less as a CLI and more as a personal task product with strong capture syntax. Its API exposes task operations such as get, create, update, move, close, reopen, and get tasks by filter [Todoist API](https://developer.todoist.com/api/v1/). Its Quick Add endpoint is especially interesting: it creates tasks with natural-language text and parses dates, projects, sections, labels, priorities, assignees, reminders, and trailing descriptions [Todoist Quick Add](https://developer.todoist.com/api/v1/).

The useful distinction is capture versus maintenance. Natural language is excellent for capture:

```bash
todoist quick "Review PR Friday #Work @important // Check auth flow"
```

But natural language is risky for maintenance because agents need to know exactly what changed. For ClickUp, it would be reasonable to add a `quick-add` or `capture` command later:

```bash
cup task quick "Review ClickUp issue tomorrow #cli @agentic"
```

But the core agent API should stay structured:

```bash
cup task create --name "Review ClickUp issue" --due tomorrow --tag cli --tag agentic
```

Todoist also reinforces that personal queues benefit from filters more than complex dependency graphs. Labels, projects, priorities, dates, and saved filters are the recurring primitives. For short-horizon tasks, "show me what needs attention today" beats "model every possible blocking relationship."

## Case Study: todo.txt

`todo.txt` is the opposite end of the spectrum: one line per task, human-readable text, and simple conventions. The format primer says "a single line in your todo.txt text file represents a single task" and emphasizes portability, searchability, and direct manipulation [todo.txt format](https://github.com/todotxt/todo.txt). It defines priority, project, and context as lightweight syntax: priorities like `(A)`, projects like `+GarageSale`, contexts like `@phone`, creation dates, completion dates, and a leading lowercase `x` for completed tasks [todo.txt format](https://github.com/todotxt/todo.txt).

The `todo.txt-cli` project keeps the command surface similarly small:

```bash
todo.sh add "THING I NEED TO DO +project @context"
todo.sh replace NR "UPDATED TODO"
todo.sh report
```

Its README describes it as "a simple and extensible shell script for managing your todo.txt file" and documents `todo.sh [-fhpantvV] [-d todo_config] action [task_number] [task_description]` [todo.txt-cli](https://github.com/todotxt/todo.txt-cli).

The lesson is restraint. For a personal queue, the most useful metadata axes are usually:

- What is it?
- Where does it live?
- What state is it in?
- When should I look at it?
- What labels help me batch it?
- What is the stable ID or URL?

If a feature does not improve those axes or make them easier for an agent to query/update, it should be suspect.

## Cross-Tool Patterns

### 1. Object Command Groups Work Better Than Flat Commands

`gh issue list`, `glab issue update`, `jira issue move`, and `acli jira workitem transition` all make the domain object explicit. For ClickUp:

```bash
cup task list
cup task view TASK_ID
cup task create --name "..."
cup task update TASK_ID --status done
cup task comment TASK_ID --body "..."
cup task delete TASK_ID
```

This is better than a broad set of top-level verbs because agents can infer the noun-specific help path.

### 2. Selectors Should Be Accepted Everywhere

Good CLIs accept local numeric IDs, global IDs, and URLs where possible. GitLab accepts issue IDs or full URLs for close/view commands [GitLab issue close](https://docs.gitlab.com/cli/issue/close/), [GitLab issue view](https://docs.gitlab.com/cli/issue/view/). GitHub uses issue numbers or URLs for edit [GitHub CLI issue edit](https://cli.github.com/manual/gh_issue_edit). Linear supports UUIDs and shorthand IDs for `issueUpdate` [Linear developer docs](https://linear.app/developers/graphql).

ClickUp should normalize:

```bash
cup task view TASK_ID
cup task view TASK_URL
cup task update TASK_ID ...
cup task update TASK_URL ...
```

For list selection, use explicit context:

```bash
cup task list --list LIST_ID
cup task list --space SPACE_ID
cup task list --folder FOLDER_ID
cup task list --all-configured-lists
```

Do not infer a board or list unless configured.

### 3. Query Presets Are More Valuable Than More Flags Forever

Jira's JQL and Taskwarrior's filters are powerful because queries can express the user's mental model. But raw query languages are easy for agents to get wrong. The practical compromise is:

```bash
cup task list --mine --status "on-deck" --updated-since -2d
cup task query ready
cup task query stale
cup config query.set ready '--mine --status "on-deck" --status "in progress"'
```

This keeps common agent tasks deterministic while allowing user-specific workflows.

### 4. State Movement Must Respect Workspace-Specific Statuses

GitHub has simple open/closed state. Jira and ClickUp have workflow-specific statuses. Atlassian CLI exposes transition by status, key, JQL, or filter [Atlassian CLI transition](https://developer.atlassian.com/cloud/acli/reference/commands/jira-workitem-transition/). `jira-cli` uses `jira issue move ISSUE-1 "In Progress"` [ankitpokhrel/jira-cli](https://github.com/ankitpokhrel/jira-cli).

ClickUp should support:

```bash
cup status list --list LIST_ID --json
cup task update TASK_ID --status "in progress"
cup task done TASK_ID
```

But `done` should be a configured alias, not a universal assumption:

```bash
cup config set status.done "complete"
cup config set status.active "in progress"
```

### 5. Machine-Readable Output Is Not Optional

GitHub CLI's `--json` and `--jq` pattern is best in class [GitHub CLI formatting](https://cli.github.com/manual/gh_help_formatting). GitLab's `--output json` and compact `ids`/`urls` output are also useful [GitLab issue list](https://docs.gitlab.com/cli/issue/list/). Taskwarrior's `export` is fundamental enough that extensions use it to access task data [Taskwarrior export](https://taskwarrior.org/docs/commands/export/).

For `clickup-tools`, every command that reads or mutates tasks should support JSON. Mutation outputs should return the changed object or a predictable envelope:

```json
{
  "ok": true,
  "action": "task.update",
  "task": {
    "id": "86a123",
    "name": "Review issue",
    "status": "in progress",
    "url": "https://app.clickup.com/t/86a123"
  }
}
```

No prose-only success messages for agent workflows.

### 6. Bulk Operations Need Dry Runs And Count Guards

Taskwarrior has a confirmation threshold for bulk modifications [Taskwarrior modify](https://taskwarrior.org/docs/commands/modify/). Atlassian CLI has `--yes`, `--ignore-errors`, JQL-based bulk transition, and JSON output [Atlassian CLI transition](https://developer.atlassian.com/cloud/acli/reference/commands/jira-workitem-transition/).

For agents, prompts are not enough. Use explicit confirmation mechanics:

```bash
cup task update --query stale --status "backlog" --dry-run --json
cup task update --query stale --status "backlog" --expect-count 3
cup task update --query stale --status "backlog" --yes
```

### 7. Add/Remove/Set Semantics Should Be Explicit

GitHub CLI uses `--add-label` and `--remove-label` [GitHub CLI issue edit](https://cli.github.com/manual/gh_issue_edit). GitLab CLI supports add/remove label flags and more compact assignee prefix semantics [GitLab issue update](https://docs.gitlab.com/cli/issue/update/). For agents, explicit wins:

```bash
cup task update TASK_ID --add-tag cli --remove-tag stale
cup task update TASK_ID --set-tags cli,agentic
cup task update TASK_ID --clear-due-date
```

Avoid overloading one `--tag` flag to mean replace, append, or filter depending on command context.

## Concrete Design Lessons For `clickup-tools`

### Recommended Command Shape

Use one canonical object hierarchy:

```bash
cup task list [filters]
cup task view TASK_SELECTOR
cup task create --name NAME [fields]
cup task update TASK_SELECTOR [fields]
cup task comment TASK_SELECTOR --body BODY
cup task delete TASK_SELECTOR
cup status list --list LIST_ID
cup query list
cup query run NAME
```

Keep aliases if they improve ergonomics, but document `task update` as the agent-safe mutation surface.

### Recommended Selectors

Support these selectors consistently:

- ClickUp task ID
- ClickUp task URL
- User-configured aliases for default list/space/folder
- Saved query names for recurrent filters

Avoid selectors that depend on visible row order, recently listed output, or a board/list the user did not configure.

### Recommended Filters

Prioritize filters that match short-horizon personal queue behavior:

```bash
--mine
--assignee me
--status STATUS
--status-not STATUS
--list LIST_ID_OR_ALIAS
--tag TAG
--not-tag TAG
--created-since -7d
--updated-since -2d
--due-before today
--due-after tomorrow
--search TEXT
--limit N
--sort updated:desc
```

These are more useful than a broad dependency model for the current product context.

### Recommended Output Modes

Adopt both rich and compact structured output:

```bash
--format table
--format json
--format jsonl
--output ids
--output urls
--json id,name,status,url,updated_at
```

If possible, make `--format json` global and ensure mutation commands respect it.

### Recommended Mutation Semantics

Use explicit flags and return structured results:

```bash
cup task update TASK_ID --name "New name"
cup task update TASK_ID --description-file body.md
cup task update TASK_ID --status "in progress"
cup task update TASK_ID --add-tag review --remove-tag stale
cup task update TASK_ID --due tomorrow
cup task update TASK_ID --clear-due
cup task update TASK_ID --assignee me
cup task update TASK_ID --unassign
```

Every mutation should return enough information for the next agent step: task ID, name, status, URL, and changed fields.

### What Not To Build Yet

Do not build `--blocked-by-pr` unless ClickUp has native storage for external URL relationships or the user configures a custom field. The survey supports a conservative rule: native links are fine, configured custom fields are fine, stuffing metadata into descriptions is not fine for an agent-first CLI.

Do not make board/list movement implicit. A "waiting on" board is a workflow convention, not universal task metadata. If a user wants that behavior, make it an explicit saved command or query alias:

```bash
cup task update TASK_ID --list waiting-on
cup query set waiting '--status "waiting"'
```

Do not optimize first for TUI flows or prompts. They can exist, but the non-interactive command path must be complete.

## Proposed Next Implementation Slice

The highest-leverage next slice is not another niche filter. It is an agent contract:

1. All task mutation commands honor `--format json`.
2. `task update TASK_ID` becomes the canonical multi-field update command.
3. `task list` gets stable JSON field selection and compact `ids`/`urls` output.
4. `task list` gets the core personal-queue filters: `--mine`, repeated/comma status filters, `--created-since`, `--updated-since`, and `--sort field:direction`.
5. Add `status list --list LIST_ID --format json` so agents can discover valid workflow states before moving a task.

This would move `clickup-tools` toward the best parts of `gh`, `glab`, Taskwarrior, and Linear MCP without importing their overfit assumptions.

## Sources

- Taskwarrior command syntax: https://taskwarrior.org/docs/syntax/
- Taskwarrior modify command: https://taskwarrior.org/docs/commands/modify/
- Taskwarrior tags and virtual tags: https://taskwarrior.org/docs/tags/
- Taskwarrior export command: https://taskwarrior.org/docs/commands/export/
- GitHub CLI issue manual: https://cli.github.com/manual/gh_issue
- GitHub CLI issue list: https://cli.github.com/manual/gh_issue_list
- GitHub CLI issue edit: https://cli.github.com/manual/gh_issue_edit
- GitHub CLI formatting: https://cli.github.com/manual/gh_help_formatting
- GitLab CLI issue list: https://docs.gitlab.com/cli/issue/list/
- GitLab CLI issue create: https://docs.gitlab.com/cli/issue/create/
- GitLab CLI issue update: https://docs.gitlab.com/cli/issue/update/
- GitLab CLI issue close: https://docs.gitlab.com/cli/issue/close/
- GitLab CLI issue view: https://docs.gitlab.com/cli/issue/view/
- Atlassian CLI work item search: https://developer.atlassian.com/cloud/acli/reference/commands/jira-workitem-search/
- Atlassian CLI work item transition: https://developer.atlassian.com/cloud/acli/reference/commands/jira-workitem-transition/
- Atlassian CLI work item edit: https://developer.atlassian.com/cloud/acli/reference/commands/jira-workitem-edit/
- `ankitpokhrel/jira-cli`: https://github.com/ankitpokhrel/jira-cli
- Linear MCP docs: https://linear.app/docs/mcp
- Linear GraphQL developer docs: https://linear.app/developers/graphql
- Todoist API: https://developer.todoist.com/api/v1/
- todo.txt format: https://github.com/todotxt/todo.txt
- todo.txt-cli: https://github.com/todotxt/todo.txt-cli
