---
tags:
  - ai-generated
  - agentic-cli
  - command-design
---

# Mutation Command Shapes

## Executive Summary

For an agent-first task CLI, the best shape is a hybrid: one broad `task update` command for ordinary field patches, plus narrow lifecycle/action commands for operations that are semantically distinct from field updates. GitHub CLI looks agent-friendly because it is both common and well-designed: it exposes predictable noun/verb commands, supports `--json`/`--jq` on reads, and separates field editing from actions such as close, reopen, comment, lock, and transfer. Linear's API/MCP shape points in the same direction from the other side: agents do well with one schema-rich update interface for issue properties, while comments, archives, attachments, and workflow-specific actions remain distinct tools. For `clickup-tools`, the product should optimize around low-ambiguity writes, structured returns, and explicit field operations rather than a growing pile of convenience subcommands.

## Scope And Evaluation Criteria

This report compares three mutation-interface styles for ticket/task systems:

- **Granular subcommands**: `task status`, `task assign`, `task comment`, `task close`.
- **Broad patch command**: `task update TASK_ID --status done --assignee me --due-date tomorrow`.
- **Hybrid design**: broad patch command for fields, narrow verbs for lifecycle and non-field actions.

The evaluation is agent-centered. Human memorability matters only when it also helps an LLM choose the right tool. The key criteria are discoverability, argument errors, partial updates, clearing fields, multi-ID operations, concurrency, and structured returns.

## Pattern 1: Granular Subcommands

Granular subcommands are commands where each user-level operation gets its own verb: `issue close`, `issue reopen`, `issue comment`, `issue lock`, `issue transfer`, `task status`, `task assign`, and so on.

GitHub CLI is the strongest example. The `gh issue` surface divides commands into general commands (`create`, `list`, `status`) and targeted commands (`close`, `comment`, `delete`, `edit`, `lock`, `pin`, `reopen`, `transfer`, etc.) in the official manual (https://cli.github.com/manual/gh_issue). Its reference makes the semantic split concrete: `gh issue close` accepts a closing comment, duplicate marker, and close reason; `gh issue comment` manages comment body, file input, edit-last, delete-last, and confirmation; `gh issue reopen` accepts a reopening comment (https://cli.github.com/manual/gh_help_reference). These are not merely aliases for setting fields. They map to distinct platform actions with distinct audit, notification, and validation behavior.

This is good for agents when the command name matches the user's intent. If the user says "close issue 25 as duplicate," `gh issue close 25 --duplicate-of 12 --reason duplicate` is easier to infer than a generic update command with a `state` enum plus a duplicate relationship. The command itself narrows the action space and reduces the number of irrelevant flags the model has to consider.

Granular commands also make dangerous operations easier to identify. `delete`, `close`, `transfer`, and `lock` are more obviously side-effecting than `update`. This aligns with MCP's tool-design vocabulary: tools can describe whether they are read-only, destructive, idempotent, or open-world, and MCP structured tool results can include an output schema for validation (https://modelcontextprotocol.io/docs/concepts/tools). Even though `clickup-tools` is a CLI rather than an MCP server, the same principle applies: command shape should reveal risk.

The downside is surface-area growth. A CLI with `task status`, `task assign`, `task unassign`, `task priority`, `task due`, `task tag`, `task untag`, `task rename`, `task describe`, and `task move` becomes harder for agents because many commands overlap. The model may know the desired field but choose the wrong verb. Worse, if each granular command has its own return shape, error convention, or partial-update behavior, the surface becomes brittle for automation.

GitHub avoids some of this by using `gh issue edit` as the broad field-edit command. The same manual that lists many targeted commands also defines `gh issue edit {<numbers> | <urls>} [flags]` for editing one or more issues, with field-ish flags such as `--title`, `--body`, `--milestone`, `--add-label`, `--remove-label`, `--add-assignee`, and `--remove-assignee` (https://cli.github.com/manual/gh_issue_edit). This is not pure granular design. It is a hybrid.

## Pattern 2: One Broad Update Command

A broad update command treats mutation as a patch operation over a resource:

```bash
cup task update TASK_ID \
  --title "Tighten JSON output" \
  --status "in progress" \
  --add-tag agentic-cli \
  --remove-tag stale \
  --assignee me
```

Linear's GraphQL API is the cleanest source for this pattern. Linear's getting-started docs show `issueUpdate(id: "BLA-123", input: { title: "New Issue Title", stateId: "NEW-STATE-ID" })`, returning `success` and selected issue fields (https://linear.app/developers/graphql?noRedirect=1). Linear's SDK docs generalize this: to update a model, call the mutation with required variables and an input object, or call `.update()` from the model; mutations often return a success boolean and the mutated entity (https://linear.app/developers/sdk-fetching-and-modifying-data). For LLMs, this is close to ideal: one schema, explicit optional fields, and one predictable result envelope.

ClickUp's own API also supports a broad update shape for regular task fields. The official `Update Task` endpoint is `PUT /api/v2/task/{task_id}` and updates a task by including one or more fields in the request body (https://developer.clickup.com/reference/updatetask). The ClickUp task docs describe tasks as carrying fields such as name, description, assignees, status, priority, due dates, tags, custom fields, links, and dependencies (https://developer.clickup.com/docs/tasks). That strongly suggests a CLI-level `task update` should exist because the underlying object has many mutable properties.

The broad command works especially well for agents because it supports partial updates naturally. If an agent only needs to change a status, it should not need to read and resubmit the whole task. This reduces race conditions and token use. It also matches Jira's REST guidance: an issue edit can send only the fields to update, and absent fields are left unchanged; Jira supports both simple `fields` updates and operation-based `update` arrays such as add/remove/set (https://developer.atlassian.com/server/jira/platform/updating-an-issue-via-the-jira-rest-apis-6848604/). That "absent means unchanged" rule is the foundation of safe agent mutation.

The main weakness is ambiguity around collection fields and clearing fields. Does `--assignee alice` replace all assignees or add Alice? Does `--tags bug,urgent` replace tags or add tags? Does `--due-date ""` clear the due date, set an empty string, or fail validation? Agents are prone to plausible-but-wrong flag guesses, so broad update commands need explicit operation verbs for non-scalar fields.

GitLab's `glab issue update` is instructive here. It uses one broad command, `glab issue update <id> [flags]`, but its assignee flag encodes add/remove/replace semantics: assignees can be prefixed with `!` or `-` to remove, `+` to add, or unprefixed to replace; labels use separate `--label` and `--unlabel`; milestone can be set to `""` or `0` to unassign (https://docs.gitlab.com/cli/issue/update/). This is powerful, but the prefix semantics are not especially agent-friendly. They are compact for humans, but a model can easily miss `+` versus replace. For `clickup-tools`, explicit `--add-assignee` and `--remove-assignee` are safer than overloaded values.

## Pattern 3: Hybrid Designs

The best observed systems are hybrid. They use broad update for object fields and specific commands for actions with distinct semantics.

GitHub CLI:

- `gh issue edit` handles field edits and supports multiple issue numbers/URLs in one command (https://cli.github.com/manual/gh_issue_edit).
- `gh issue close`, `reopen`, `comment`, `delete`, `lock`, `transfer`, `pin`, and `unpin` remain targeted commands (https://cli.github.com/manual/gh_issue).
- `gh pr edit` mirrors `gh issue edit`, but PR-specific actions such as `merge`, `ready`, `review`, `update-branch`, and `checks` remain separate (https://cli.github.com/manual/gh_pr_edit).

Linear:

- `issueUpdate` patches issue properties with an input object and returns `success` plus the mutated issue (https://linear.app/developers/graphql?noRedirect=1).
- Comments are separate mutations/tools. The SDK docs show `createComment` returning a payload with `success` and `comment`, separate from issue update (https://linear.app/developers/sdk-fetching-and-modifying-data).
- Attachments are also separate. Linear documents issue attachments as external resources linked to issues, "similarly to GitHub Pull Requests," designed for API developers and integrations (https://linear.app/developers/attachments).
- Linear's MCP docs say the official MCP server exposes tools for finding, creating, and updating objects like issues, projects, cycles, and comments, not one mega-tool for everything (https://linear.app/docs/mcp).

Jira:

- Field edits use `PUT /issue/{issueIdOrKey}` with `fields` and `update`.
- Status movement is a transition, not a field edit. Atlassian's Cloud REST docs state that issue transition is not supported by edit issue and is ignored there; to transition an issue, use Transition issue (https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/).
- The older REST reference says `POST /issue/{issueIdOrKey}/transitions` performs a transition and can update/set other fields when performing the transition, but only fields available on the transition screen are accepted (https://docs.atlassian.com/software/jira/docs/api/REST/1000.1143.0/).

ClickUp:

- `Update Task` patches regular fields, but ClickUp explicitly says custom fields must use the Set Custom Field endpoint rather than Update Task (https://developer.clickup.com/reference/updatetask).
- ClickUp's task docs repeat that custom fields can be set on creation, but updating custom fields on an existing task requires Set Custom Field Value (https://developer.clickup.com/docs/tasks).
- Custom field objects have field IDs, types, and type-specific values (https://developer.clickup.com/docs/customfields). That means a CLI should not pretend every field is a native task field.

The common rule: **use separate commands when the backend uses separate concepts, permissions, validation rules, or audit behavior**. Use broad update only where the backend really supports patching fields on the same resource.

## Discoverability For LLM Agents

Agents discover commands through help text, examples, prior knowledge, and semantic similarity. The GitHub CLI probably benefits from training prevalence, but the design itself is also highly learnable: `gh <noun> <verb>`, common verbs across nouns, stable `--json` conventions on reads, and fallback `gh api` for raw API access. The manual's issue command list is compact enough for a model to reason over, and targeted commands are named with common English verbs (https://cli.github.com/manual/gh_issue).

For `clickup-tools`, discoverability should be biased toward few top-level verbs:

```text
cup task create
cup task update
cup task comment
cup task close
cup task reopen
cup task delete
cup task list
cup task view
```

Avoid creating field-specific verbs unless the field is a workflow action or common enough to deserve a stable affordance. `task status` feels convenient, but it competes with `task update --status`. An agent can learn one broad field mutation command more reliably than twenty near-synonyms.

The help output for `task update` should include examples that cover the hardest semantics:

```bash
cup task update TASK_ID --status "in progress"
cup task update TASK_ID --add-tag agentic-cli --remove-tag stale
cup task update TASK_ID --assign me --unassign 123456
cup task update TASK_ID --clear-due-date
cup task update TASK_ID --json
```

This matters because agents often infer from examples. Examples should encode the intended operation model.

## Argument Errors And Validation

Broad update commands reduce wrong-command errors but can increase wrong-argument errors. The mitigation is not to split every field into a subcommand; it is to make flags explicit, typed, and mutually exclusive where needed.

Preferred:

```bash
cup task update TASK_ID --add-tag bug --remove-tag stale
cup task update TASK_ID --set-tags bug,urgent
cup task update TASK_ID --clear-due-date
```

Risky:

```bash
cup task update TASK_ID --tags bug,urgent
cup task update TASK_ID --due-date ""
cup task update TASK_ID --assignee +alice,-bob
```

GitHub's `--add-label` / `--remove-label` pattern is clearer than GitLab's prefix-coded assignee values for agents, even though both solve add/remove semantics (https://cli.github.com/manual/gh_issue_edit, https://docs.gitlab.com/cli/issue/update/). Jira's explicit update operations are even clearer at the API level: collections can support `add`, `remove`, and `set` as distinct operations (https://developer.atlassian.com/server/jira/platform/updating-an-issue-via-the-jira-rest-apis-6848604/). `clickup-tools` should expose this explicitly in flags rather than relying on value syntax.

Validation should be local where possible:

- Unknown status should fail before mutation when statuses are cached or discoverable.
- Mutually exclusive flags such as `--set-tags` and `--add-tag` should either be forbidden together or have documented ordering.
- Empty strings should not be used as magic clear values.
- IDs and names should have explicit flags when ambiguity matters: `--assignee-id`, `--assignee-name`, `--status`.
- Commands should print machine-readable error objects under `--json`.

## Partial Updates

Partial update semantics are essential for agents. An agent frequently receives a task ID and a single requested change. Requiring a read-modify-write loop increases latency and creates races with humans or other agents.

ClickUp's native `Update Task` endpoint supports "include one or more fields" semantics (https://developer.clickup.com/reference/updatetask). Jira's edit docs explicitly say absent fields are left unchanged (https://developer.atlassian.com/server/jira/platform/updating-an-issue-via-the-jira-rest-apis-6848604/). Linear's `issueUpdate` input object shows only changed properties in the mutation example (https://linear.app/developers/graphql?noRedirect=1).

`clickup-tools` should guarantee:

- Omitted flags never clear fields.
- Scalar field flags set only that field.
- Add/remove flags apply only the named collection operation.
- Multi-step updates should be reported as multi-operation results.

ClickUp complicates this because custom fields use a separate endpoint. If `task update` allows both native fields and custom fields, it may need to perform multiple API calls. That is acceptable only if the JSON result makes the operation boundaries visible.

Example structured result:

```json
{
  "ok": true,
  "task": {
    "id": "86abc",
    "name": "Improve mutation JSON"
  },
  "operations": [
    {
      "kind": "task_update",
      "ok": true,
      "changed": ["status", "priority"]
    },
    {
      "kind": "custom_field_set",
      "field_id": "5dc86497-098d-4bb0-87d6-cf28e43812e7",
      "ok": true
    }
  ]
}
```

## Clearing Fields

Clearing fields deserves first-class syntax. It is one of the easiest places for agents to make destructive mistakes.

GitHub exposes removal as separate flags: `--remove-label`, `--remove-assignee`, `--remove-milestone`, and `--remove-project` (https://cli.github.com/manual/gh_issue_edit). GitLab's `glab issue update` uses a mix: `--unlabel`, `--unassign`, and special values for milestone clearing (https://docs.gitlab.com/cli/issue/update/). ClickUp's Update Task docs include at least one magic-value behavior: to clear task description, include `Description` with a single space (https://developer.clickup.com/reference/updatetask). That is an API wart; it should not become the primary CLI design.

Recommended `clickup-tools` convention:

- `--clear-description`
- `--clear-due-date`
- `--clear-priority`
- `--clear-assignees`
- `--clear-tags`
- `--clear-field FIELD_ID_OR_ALIAS` for configured custom fields

Do not overload empty strings. Do not treat omitted values as clears. Under `--json`, a clear operation should be explicit in the returned `operations` array.

## Multi-ID Operations

Multi-ID support is valuable for agents but should be carefully scoped.

GitHub supports editing multiple issues in one command: `gh issue edit 23 34 --add-label "help wanted"` (https://cli.github.com/manual/gh_issue_edit). This is a strong precedent for safe, uniform batch operations. It works because the same field operation can be applied to all selected issues and GitHub can express the target set as explicit IDs/URLs.

For `clickup-tools`, multi-ID should be limited to operations that are:

- Same operation for every task.
- No per-task dynamic value computation.
- Recoverable or at least clearly reported per task.
- Safe to retry when possible.

Good:

```bash
cup task update TASK1 TASK2 TASK3 --add-tag follow-up --json
cup task close TASK1 TASK2 --comment "Done in PR #42" --json
```

Risky:

```bash
cup task update --query "status='next'" --status done
```

Query-selected mutation should require `--dry-run` first or an explicit `--execute` flag. This mirrors bulk operation patterns in Jira ecosystems: bulk transition runbooks commonly include dry-run previews and explicit execution to prevent unintended large mutations (https://atlassiancli.com/runbooks/jira-bulk-transition.html). Even if that source is not Atlassian-official, the pattern is sound for agent safety.

For multi-ID JSON returns, do not collapse success into prose. Return per-target outcomes:

```json
{
  "ok": false,
  "summary": {
    "requested": 3,
    "succeeded": 2,
    "failed": 1
  },
  "results": [
    {"task_id": "A", "ok": true, "task": {"id": "A", "status": "done"}},
    {"task_id": "B", "ok": true, "task": {"id": "B", "status": "done"}},
    {"task_id": "C", "ok": false, "error": {"code": "status_not_allowed", "message": "Status 'done' is not valid for this list"}}
  ]
}
```

Exit code should be non-zero if any target fails, unless an explicit `--allow-partial` option exists.

## Concurrency And Race Conditions

CLIs often hide concurrency, but agents need clarity because they chain operations quickly and may operate alongside humans or other agents.

The safest default is patch-style mutation where omitted fields are unchanged. That avoids overwriting concurrent changes. Broad update commands should never implement a read-modify-write cycle for scalar fields unless required by the API.

Collection operations require special care. `--set-tags` may overwrite tags added by someone else since the agent last read the task. `--add-tag` and `--remove-tag` are safer because they express a delta. GitHub's separate add/remove label flags and Jira's operation arrays both point toward delta semantics (https://cli.github.com/manual/gh_issue_edit, https://developer.atlassian.com/server/jira/platform/updating-an-issue-via-the-jira-rest-apis-6848604/).

For `clickup-tools`, the concurrency design should be:

- Prefer delta flags for collections.
- Reserve `--set-*` for intentional replacement.
- Return updated task snapshots so the agent can see final state.
- Include operation-level failures when ClickUp requires multiple API calls.
- Later, consider `--if-updated-at` or `--if-version` only if ClickUp exposes a reliable concurrency token. Do not invent optimistic concurrency from timestamps unless the API supports it consistently.

Status changes are a special case. ClickUp status is a field on a task, but statuses are constrained by list/workflow. A status update can fail because the target list does not have that status. The CLI should surface valid statuses in the error if available.

## Structured Returns

Structured returns are non-negotiable for an agent-first CLI.

GitHub CLI supports `--json`, `--jq`, and `--template` on many read commands. Its formatting docs say `--json` converts output to JSON and `--jq`/`--template` can shape it for scripts; it also requires explicit field names, which limits over-fetching (https://cli.github.com/manual/gh_help_formatting). GitHub's newer `agent-task view` command exposes JSON fields such as `completedAt`, `createdAt`, `id`, `pullRequestNumber`, `state`, and `updatedAt` (https://cli.github.com/manual/gh_agent-task_view). This reinforces the pattern that machine consumption should be explicit and schema-like.

Linear's mutation examples are stronger for writes: mutations return a `success` boolean and the mutated entity fields selected by the caller (https://linear.app/developers/graphql?noRedirect=1). The SDK docs state that mutations often return success and the mutated entity (https://linear.app/developers/sdk-fetching-and-modifying-data). MCP formalizes this for agent tools by supporting structured content and output schemas, with clients expected to validate structured results when an output schema exists (https://modelcontextprotocol.io/docs/concepts/tools).

`clickup-tools` should make JSON a global contract, not a best-effort format:

- Every mutating command supports `--json`.
- Under `--json`, stdout contains only JSON.
- Human prose goes to stderr or is suppressed.
- The result includes `ok`, `task` or `tasks`, `operations`, and `error`.
- The result includes enough canonical IDs for the next command.
- Errors use stable codes, not only human messages.

Recommended single-task update shape:

```json
{
  "ok": true,
  "task": {
    "id": "86abc",
    "custom_id": "AI-123",
    "url": "https://app.clickup.com/t/86abc",
    "name": "Add JSON output for task mutations",
    "status": "in progress",
    "assignees": [{"id": 123, "username": "evan"}],
    "updated_at": "2026-05-16T06:10:00Z"
  },
  "operations": [
    {
      "kind": "task_update",
      "ok": true,
      "changed": ["status"]
    }
  ]
}
```

Recommended error shape:

```json
{
  "ok": false,
  "error": {
    "code": "invalid_status",
    "message": "Status 'reviewing' is not available for list 'Personal Queue'.",
    "details": {
      "task_id": "86abc",
      "valid_statuses": ["to do", "in progress", "done"]
    }
  }
}
```

## Where Granular Commands Still Make Sense

Use a targeted command when the operation is not just setting a task field.

Recommended targeted commands:

- `task create`: creation has required fields, defaults, templates, and list selection.
- `task comment`: comments are append-only conversation actions, not task field edits. GitHub and Linear both keep comments separate from ordinary issue update (https://cli.github.com/manual/gh_help_reference, https://linear.app/developers/sdk-fetching-and-modifying-data).
- `task close` / `task reopen`: these may map to status internally, but they are high-level lifecycle actions. They can apply configured default terminal/open statuses, include comments, and be marked as potentially destructive.
- `task delete`: destructive and should never be hidden behind `task update`.
- `task move`: if moving between lists changes available statuses/custom fields, treat it as a distinct operation.
- `task link` / `task unlink` / `task depend`: if implemented, these map to relationship endpoints and should not be disguised as generic fields.
- `task field set` / `task field clear`: custom fields are not part of ClickUp's Update Task endpoint, so a targeted namespace may be clearer than overloading `task update`.

Avoid these unless there is strong evidence:

- `task status` as a primary mutation command. Prefer `task update --status`. A convenience alias can exist later, but it should call the same implementation and return the same JSON.
- `task assign` as a primary command. Prefer `task update --add-assignee`, `--remove-assignee`, and `--set-assignees`.
- `task priority` / `task due` / `task rename`. These are simple field patches and belong under `task update`.

## Design Lessons For clickup-tools

### 1. Make `task update` The Canonical Field Patch Interface

`task update` should be the main mutation command for native ClickUp task fields:

```bash
cup task update TASK_ID \
  --name "Fix mutation output" \
  --description-file spec.md \
  --status "in progress" \
  --priority high \
  --due-date 2026-05-20 \
  --add-tag agentic-cli \
  --remove-tag stale \
  --add-assignee me \
  --remove-assignee 123456 \
  --json
```

This gives agents one place to learn ordinary mutation. It also maps cleanly to ClickUp's `Update Task` endpoint for native fields (https://developer.clickup.com/reference/updatetask).

### 2. Use Explicit Delta Flags For Collections

Prefer:

```bash
--add-tag TAG
--remove-tag TAG
--set-tags TAGS
--add-assignee USER
--remove-assignee USER
--set-assignees USERS
```

This borrows the clarity of GitHub's add/remove flags and Jira's explicit operations while avoiding GitLab's compact prefix semantics (https://cli.github.com/manual/gh_issue_edit, https://developer.atlassian.com/server/jira/platform/updating-an-issue-via-the-jira-rest-apis-6848604/, https://docs.gitlab.com/cli/issue/update/).

### 3. Make Clears First-Class

Use `--clear-*` flags. Do not require magic empty strings or API-specific quirks.

```bash
cup task update TASK_ID --clear-due-date --clear-priority --json
```

If ClickUp requires unusual payloads internally, hide that behind a clear operation and report the clear explicitly in JSON.

### 4. Keep Comments Separate

Do not implement comments as `task update --comment`. Use:

```bash
cup task comment TASK_ID --body "Implemented in PR #42" --json
```

Comments are append operations with their own IDs and audit semantics. GitHub's `gh issue comment` and Linear's separate comment mutation both support keeping this separate (https://cli.github.com/manual/gh_help_reference, https://linear.app/developers/sdk-fetching-and-modifying-data).

### 5. Treat Status As A Field, But Offer Lifecycle Shortcuts Carefully

Primary:

```bash
cup task update TASK_ID --status "in progress" --json
```

Optional lifecycle commands:

```bash
cup task close TASK_ID --comment "Done" --json
cup task reopen TASK_ID --status "to do" --json
```

This mirrors GitHub's split between `edit` and `close`/`reopen` while acknowledging that ClickUp status is not exactly GitHub issue state. Lifecycle shortcuts should be configurable and transparent about what status they set.

### 6. Do Not Hide Custom Fields Inside Generic Update Without A Clear Contract

ClickUp explicitly says existing-task custom field updates require Set Custom Field Value, not Update Task (https://developer.clickup.com/docs/tasks). That argues for one of two designs:

```bash
cup task field set TASK_ID FIELD_ALIAS VALUE --json
cup task field clear TASK_ID FIELD_ALIAS --json
```

or:

```bash
cup task update TASK_ID --field blocked_url=https://example.com --json
```

If the second form is allowed, the JSON result must disclose that this was a separate custom-field operation. It should fail if the field alias is not configured. Do not stuff agent metadata into descriptions as a fallback.

### 7. Make Multi-ID Explicit And Per-Target

Allow:

```bash
cup task update TASK1 TASK2 --add-tag reviewed --json
```

Return a result object with per-task success/failure. Do not silently skip failures. Consider `--dry-run` for query-selected mutation before allowing execution.

### 8. Prefer Agent-Safe Verb Names Over Human Abbreviations

Avoid short aliases in documentation examples. Agents do better with semantic flags than compact shorthands:

- Prefer `--add-assignee` over `-a`.
- Prefer `--description-file -` over clever positional stdin behavior.
- Prefer `--format json` or `--json` consistently, not both with different semantics.

### 9. Make JSON The Default For Agent Mode

If the CLI has or gains an agent mode, all commands should default to structured output there:

```bash
export CUP_AGENT=1
cup task update TASK_ID --status done
```

Even outside agent mode, mutating commands should accept `--json` and return only JSON on stdout.

### 10. Document The Operation Model In Help Text

The `task update --help` text should explicitly say:

- Omitted fields are unchanged.
- `--set-*` replaces.
- `--add-*` and `--remove-*` are deltas.
- `--clear-*` clears.
- Multiple task IDs apply the same operation to each task.
- JSON output includes per-operation results.

Agents learn from help output. The command docs are part of the model interface.

## Recommended Command Shape

Recommended near-term surface:

```text
cup task create [TITLE] [field flags] [--json]
cup task update TASK_ID... [field patch flags] [--json]
cup task comment TASK_ID --body BODY | --body-file FILE [--json]
cup task close TASK_ID... [--comment TEXT] [--json]
cup task reopen TASK_ID... [--status STATUS] [--json]
cup task delete TASK_ID... --yes [--json]
cup task move TASK_ID... --list-id LIST_ID [--status STATUS] [--json]
cup task field set TASK_ID FIELD VALUE [--json]
cup task field clear TASK_ID FIELD [--json]
cup task list [filters] [--json]
cup task view TASK_ID [--json]
```

Do not prioritize:

```text
cup task status
cup task assign
cup task due
cup task priority
cup task rename
```

Those can be aliases later, but they should not define the core agent contract.

## Sources

- GitHub CLI manual, `gh issue`: https://cli.github.com/manual/gh_issue
- GitHub CLI reference, issue commands: https://cli.github.com/manual/gh_help_reference
- GitHub CLI manual, `gh issue edit`: https://cli.github.com/manual/gh_issue_edit
- GitHub CLI manual, `gh pr edit`: https://cli.github.com/manual/gh_pr_edit
- GitHub CLI formatting docs: https://cli.github.com/manual/gh_help_formatting
- GitHub CLI manual, `gh agent-task`: https://cli.github.com/manual/gh_agent-task
- GitHub CLI manual, `gh agent-task view`: https://cli.github.com/manual/gh_agent-task_view
- GitLab CLI docs, `glab issue update`: https://docs.gitlab.com/cli/issue/update/
- Linear Developers, GraphQL getting started: https://linear.app/developers/graphql?noRedirect=1
- Linear Developers, SDK fetching and modifying data: https://linear.app/developers/sdk-fetching-and-modifying-data
- Linear Developers, attachments: https://linear.app/developers/attachments
- Linear MCP docs: https://linear.app/docs/mcp
- Atlassian Jira REST API, edit issue: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/
- Atlassian Jira REST API, updating issue via REST: https://developer.atlassian.com/server/jira/platform/updating-an-issue-via-the-jira-rest-apis-6848604/
- Atlassian Jira REST reference, transitions: https://docs.atlassian.com/software/jira/docs/api/REST/1000.1143.0/
- ClickUp API, Update Task: https://developer.clickup.com/reference/updatetask
- ClickUp API, Tasks overview: https://developer.clickup.com/docs/tasks
- ClickUp API, Custom Fields: https://developer.clickup.com/docs/customfields
- Model Context Protocol docs, tools and structured content: https://modelcontextprotocol.io/docs/concepts/tools
- Atlassian CLI bulk transition runbook: https://atlassiancli.com/runbooks/jira-bulk-transition.html
