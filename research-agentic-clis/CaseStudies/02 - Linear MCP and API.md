---
tags:
  - ai-generated
  - agentic-cli
  - linear
  - mcp
---

# Linear MCP and API Case Study

## Executive Summary

Linear is agent-friendly because its issue model is small, regular, and strongly structured: an issue has a required team, title/status semantics, and a broad set of optional properties that can be changed through one `issueUpdate` input object. The most important design pattern for `clickup-tools` is not Linear's UI polish; it is the "single save/update surface" that lets an agent create or update a ticket by supplying only the fields it knows. Linear's MCP design appears to be moving in the same direction: a consolidated `save_issue` tool, structured list/get/save/comment tools, OAuth-hosted remote MCP, explicit validation, and tool documentation tuned for lower token use. For an agent-first ClickUp CLI, the lesson is to optimize for schema legibility, idempotent partial updates, predictable JSON responses, and discoverable lookup tools rather than human terminal ergonomics.

## Scope and Source Notes

This report focuses on Linear's official documentation, developer docs, changelog, and SDK/API schema shape. Linear's public MCP documentation documents transport, authentication, and the general existence of tools for finding, creating, and updating objects, but it does not publish full JSON schemas for each MCP tool on the docs page. Where MCP tool names such as `save_issue` and `list_issues` are discussed, I cite official Linear changelog entries when possible and clearly mark third-party MCP catalogs as corroborating rather than authoritative.

## Detailed Findings

### 1. Linear's core API is a GraphQL "partial input object" model

Linear's public API is GraphQL, served at `https://api.linear.app/graphql`, and Linear says it is the same API used internally to build the product (https://linear.app/developers/graphql). That matters for agent tooling because the API is not a thin, ad hoc integration layer. It exposes the actual domain model: teams, issues, workflow states, users, labels, comments, projects, and relationships.

The key ticket operation is `issueUpdate(id, input)`. Linear's getting-started docs show the pattern directly: pass either a UUID or shorthand issue key like `BLA-123`, then include an `input` object with only the properties being changed, such as `title` and `stateId` (https://linear.app/developers/graphql). The create path is similar: `issueCreate(input)` takes a structured object with `title`, `description`, and `teamId`, then returns a payload containing `success` and the created `issue` (https://linear.app/developers/graphql).

This is the first big agent-friendly design choice: there is no need for separate commands like `set-title`, `set-status`, `assign`, `set-labels`, `set-project`, and `set-priority` at the API layer. Those can exist as aliases, but the primitive is "update issue with a sparse set of fields."

The current `@linear/sdk` package, version `84.0.0` at research time, exposes `IssueUpdateInput` with many optional fields, including:

```ts
type IssueUpdateInput = {
  addedLabelIds?: string[];
  assigneeId?: string;
  cycleId?: string;
  delegateId?: string;
  description?: string;
  dueDate?: TimelessDate;
  estimate?: number;
  labelIds?: string[];
  parentId?: string;
  priority?: number;
  projectId?: string;
  projectMilestoneId?: string;
  removedLabelIds?: string[];
  stateId?: string;
  subscriberIds?: string[];
  teamId?: string;
  title?: string;
  trashed?: boolean;
};
```

The exact list changes over time, but the shape is stable: required identifier outside, optional mutation fields inside. The SDK docs also reinforce the general convention: required variables come first, optional variables are passed as a final object; mutations return a success boolean and the mutated entity (https://linear.app/developers/sdk-fetching-and-modifying-data).

For an LLM, this is easier than command selection among dozens of tiny verbs. The model can decide "I need to update issue X" and fill whichever fields it knows. Unknown fields can be omitted without needing no-op values.

### 2. Linear separates human-readable names from durable IDs, but gives lookup paths

Linear's underlying API generally wants durable identifiers. The GraphQL examples use `teamId`, `stateId`, `assignee.id`, and issue IDs; the docs explicitly tell developers they can find entity IDs from the Linear command menu via "Copy model UUID" (https://linear.app/developers/graphql). The SDK also exposes object relations and connection helpers so clients can resolve teams, users, workflow states, labels, and issues before mutating them (https://linear.app/developers/sdk-fetching-and-modifying-data).

This is good API design, but raw UUID requirements are not ideal for agents. Linear mitigates that in several places:

- Issue IDs can be addressed by UUID or shorthand issue identifier, e.g. `BLA-123` (https://linear.app/developers/graphql).
- The issue creation URL supports names as well as UUIDs for fields like status, assignee, cycle, label, and project (https://linear.app/docs/creating-issues).
- Linear's MCP catalog entries, as imported by third-party MCP gateways, describe agent-facing conveniences such as `assignee` accepting a user ID, name, email, or `"me"` for the `save_issue` tool. This is corroborating, not primary Linear documentation, but it matches the product direction visible elsewhere (https://www.speakeasy.com/product/mcp-gateway/catalog/linear).

The lesson is that an agent-facing CLI should support both:

- canonical IDs for deterministic execution
- ergonomic aliases for common values like `me`, status names, label names, and task keys

But the CLI should resolve aliases explicitly and return the resolved IDs in JSON. Silent name matching is dangerous when multiple teams/lists/statuses share names.

### 3. Status transitions are structured, team-specific, and queryable

Linear's issue statuses are team-specific workflows. The default shape is Backlog, Todo, In Progress, Done, and Canceled, but teams can customize statuses inside fixed categories (https://linear.app/docs/configuring-workflows). The API example uses `stateId` as the status field, and the docs show how to query `workflowStates` and list their IDs and names (https://linear.app/developers/graphql).

Linear's agent best practices also show a more advanced pattern: when an agent starts implementation work, it should query the team's workflow states filtered by `type: { eq: "started" }`, then pick the one with the lowest `position` before moving the issue into a started state (https://linear.app/developers/agent-best-practices). That is a very useful design signal. Linear is not hard-coding "In Progress"; it asks agents to discover the correct state category for the team and then make a state transition.

For `clickup-tools`, this argues against global assumptions like "on-deck" or "waiting" unless configured. The agent-friendly surface should have discovery commands:

```bash
cup list-statuses --list-id LIST
cup task update TASK --status "in progress"
```

The update command can accept a status name, but it should resolve against the selected ClickUp list/workspace and fail with structured ambiguity if there are multiple matches.

### 4. Comments are their own first-class operation

Linear has a separate comment creation input, `CommentCreateInput`, with fields such as `body`, `issueId`, `parentId`, `createdAt`, and `doNotSubscribeToIssue` in the SDK type definitions. The SDK docs show `createComment({ issueId: "some-issue-id" })` returning a payload with `success` and `comment` (https://linear.app/developers/sdk-fetching-and-modifying-data).

Linear Agent's product docs also emphasize comments as a native collaboration surface: Linear Agent can post, edit, and delete its own comments, and `@Linear` can be invoked from comments to produce updates, summaries, action items, and decision recaps in-place (https://linear.app/docs/linear-agent). The developer docs distinguish comments from frozen agent activities: comments are editable and may not be reliable as a durable transcript, so agent applications should rely on Agent Activities to reconstruct a session (https://linear.app/developers/agent-best-practices).

For our CLI, the design lesson is:

- Comments should be a separate primitive from task description updates.
- Comment creation should return the created comment ID, task ID, author, body, and URL in JSON.
- The CLI should not stuff operational state into comments if the target system has a native field or relation.
- If comments are used as agent progress logs, they should be append-only from the CLI's perspective unless the user explicitly asks to edit/delete.

### 5. Labels and assignees are structured, but Linear documents their edge cases

Labels in Linear are scoped to either the workspace or a team. Linear recommends workspace-level labels for concepts used across teams, and notes that team-specific labels can behave like workspace labels in UI filtering when names match, but not in the API, where unique identifiers are required (https://linear.app/docs/labels). That is exactly the kind of edge case agents mishandle if the tool interface hides the distinction.

Assignees are similarly structured. Linear issues have a single assignee, and assignment creates ownership, notifications, search/filter affordances, and history. Linear now also separates human ownership from agent delegation: a user remains primary assignee while an agent can be delegated to work on the issue (https://linear.app/docs/assigning-issues). The API/SDK reflects this with both `assigneeId` and `delegateId` on issue inputs.

For `clickup-tools`, this suggests a product distinction:

- `assignee` means the accountable human or ClickUp assignee.
- `agent` or `delegate` means the automation currently working the task, if ClickUp has an equivalent or if the CLI can model it explicitly.

Do not overload assignment to mean "the agent touched this." That erodes the human's queue semantics.

### 6. Linear's MCP surface is centrally hosted and auth-aware

Linear's official MCP docs describe a remote MCP server at `https://mcp.linear.app/mcp` using Streamable HTTP transport and OAuth 2.1 with dynamic client registration (https://linear.app/docs/mcp). The same docs provide setup instructions for Claude, Claude Code, Codex, Cursor, Jules, VS Code, v0, Windsurf, Zed, and other clients, and they state that the server has tools for finding, creating, and updating objects like issues, projects, and comments (https://linear.app/docs/mcp).

Two details are especially relevant:

- The server is centrally hosted and managed by Linear, not copied into each client environment (https://linear.app/docs/mcp).
- Linear supports passing OAuth tokens and API keys directly in the `Authorization: Bearer <token>` header, enabling app users, read-only restricted API keys, or existing OAuth applications without an extra interactive hop (https://linear.app/docs/mcp).

This gives agents a stable, canonical interface. The remote server can improve schemas, validation, and behavior without every user upgrading a local package. For a CLI, we cannot get that exact benefit unless we ship an MCP server or plugin, but we can mimic it by making one canonical machine interface and avoiding drift between human commands and agent commands.

### 7. Linear appears to be consolidating MCP mutations into "save" tools

Linear's official changelog says the MCP server was expanded on February 5, 2026 with tools for creating/editing initiatives, initiative updates, project milestones, project updates, project labels, and image loading, and that Linear improved performance and reduced token usage through better tool documentation (https://linear.app/changelog/2026-02-05-linear-mcp-for-product-management). The current changelog also has MCP-specific notes, including:

- Unknown tool parameters now return validation errors instead of being silently dropped (https://linear.app/changelog).
- Links added through `save_issue` now go through integration-aware attachment linking, so integration URLs can become rich attachments and enable sync instead of plain URL attachments (https://linear.app/changelog).
- Issues with explicit zero values, such as 0-point estimate or "No priority," no longer serialize as `undefined`, so consumers can distinguish zero from unset (https://linear.app/changelog).
- Issues created through MCP without a `stateId` now default to the team's default state in certain member contexts, even when triage is enabled (https://linear.app/changelog).

Those changelog notes are small, but they reveal a lot about agent tool design:

- Tool schemas must reject unknown fields. Silent drops are bad for agents because they create false success.
- Zero and null must be semantically precise. `0`, `null`, omitted, and `undefined` mean different things.
- Links are structured attachments, not just description text.
- Defaults should match the user's workspace semantics.

Third-party MCP catalogs currently list a Linear `save_issue` tool that creates or updates depending on whether `id` is provided, plus `list_issues`, `get_issue`, `save_comment`, `list_issue_statuses`, `list_issue_labels`, `list_teams`, and `list_users` (https://www.speakeasy.com/product/mcp-gateway/catalog/linear). Because this is not Linear's official docs, we should treat the specific schema as an observed external catalog, not a contract. Still, it aligns strongly with the official changelog's references to `save_issue`.

For `clickup-tools`, the analogous design would be:

```bash
cup task save \
  --id TASK_ID \
  --name "..." \
  --description "..." \
  --status "..." \
  --assignee "..." \
  --priority "..." \
  --tags bug,agent \
  --due-date 2026-05-20 \
  --list-id LIST_ID \
  --format json
```

When `--id` is omitted, create. When `--id` is present, update. If ClickUp makes create/update too different internally, the CLI can still expose this as one agent-facing operation and route under the hood.

### 8. Linear designs for agent identity and human accountability

Linear's Agent Interaction Guidelines state that agents should disclose they are agents, inhabit the platform natively, give instant feedback, make internal state transparent, respect disengagement, and not be treated as accountable humans (https://linear.app/developers/aig). Linear's agent setup docs say app-authenticated agents behave like workspace users: they can be mentioned, delegated issues, create/reply to comments, and collaborate on projects and documents (https://linear.app/developers/agents).

The most important product idea is delegation. Linear says assigning an issue to an app sets it as `delegate`, not `assignee`, so the human maintains ownership while the agent works on their behalf (https://linear.app/developers/agents). In the agent best practices, Linear recommends setting the agent as delegate when implementation begins if no delegate is present (https://linear.app/developers/agent-best-practices).

This is relevant even if `clickup-tools` is just a CLI. A task operation should avoid muddying who owns the task. Agent-facing metadata can say "last_actor", "created_by_cli", "agent_session", or "delegate" if there is a native field. It should not silently reassign the task to the automation unless that is the user's explicit workflow.

### 9. Linear's list/query design combines structured filters with agent-friendly shortcuts

Linear's product filtering supports almost every issue property, including priority, cycle, estimate, labels, links, project, status, blocked/blocking/related relationships, dates, assignee, creator, subscribers, and content (https://linear.app/docs/filters). Linear's API docs recommend filtering in GraphQL rather than fetching all issues and filtering in code, and recommend ordering recent updates rather than polling individual issues (https://linear.app/developers/graphql).

This is important for agent chaining. A good ticket CLI should make these operations cheap and unambiguous:

```bash
cup task list --assignee me --status started --updated-since 2026-05-01 --format json
cup task list --list-id LIST --tag bug --limit 20 --order updated:desc --format json
cup task get TASK_ID --format json
```

The response should include enough fields to chain into the next mutation without a second lookup: task ID, name/title, status ID/name, list ID/name, assignees, tags/labels, URL, updated timestamp, and maybe a short description preview.

### 10. Linear's structured responses are consistent and chainable

Linear's GraphQL mutations commonly return a payload with `success` and the mutated entity, and the docs show selecting exactly the fields needed from the entity after mutation (https://linear.app/developers/graphql, https://linear.app/developers/sdk-fetching-and-modifying-data). This is excellent for agents: after creating or updating an issue, the response can be used immediately in the next step without scraping terminal text.

For `clickup-tools`, this should be a hard rule:

- Every mutation supports `--format json`.
- JSON mutation output is never prose.
- Successful output includes `success: true`, `operation`, and the task/comment/list entity.
- Failed output includes `success: false`, stable `error.code`, human-readable `error.message`, and machine-actionable details such as ambiguous matches.

Example:

```json
{
  "success": true,
  "operation": "task.update",
  "task": {
    "id": "abc123",
    "name": "Fix auth redirect",
    "status": {"id": "st2", "name": "in progress"},
    "list": {"id": "list1", "name": "AI Engineering"},
    "url": "https://app.clickup.com/t/abc123",
    "updated_at": "2026-05-16T06:10:00Z"
  },
  "changed": ["status"]
}
```

## Concrete Design Lessons for `clickup-tools`

### Build one canonical `task save` or `task update` interface

Add an agent-first command that accepts a sparse set of optional fields and applies them in one operation. Keep existing human-friendly commands as aliases if useful, but agents should have one obvious mutation surface.

Recommended shape:

```bash
cup task save [TASK_ID] \
  --name TEXT \
  --description MARKDOWN \
  --status STATUS_OR_ID \
  --assignee USER_OR_ME \
  --priority PRIORITY \
  --tags TAG1,TAG2 \
  --due-date YYYY-MM-DD \
  --list-id LIST_ID \
  --format json
```

If `TASK_ID` is omitted, require `--name` and `--list-id` or a configured default list. If `TASK_ID` is present, all fields are optional but at least one mutation field must be supplied.

### Make lookup/discovery first-class

Agent-friendly mutation depends on reliable lookup. Add or tighten:

```bash
cup list lists --format json
cup list statuses --list-id LIST --format json
cup list users --format json
cup task get TASK_ID --format json
cup task list --assignee me --status STATUS --updated-since DATE --format json
```

Every lookup should return IDs and names. Every mutation accepting a name should either resolve it uniquely or fail with structured ambiguity.

### Prefer native fields and relationships over description stuffing

Linear's design uses native status, assignee, labels, links, comments, relations, and agent delegation fields. The same principle should govern ClickUp. Do not encode "blocked by PR", "waiting on", or "agent session state" in descriptions unless there is no native place and the user has opted into that convention. For external URLs, prefer ClickUp native custom fields only when explicitly configured, or represent the URL as a normal ClickUp attachment/link if the API supports it.

### Return structured mutation results always

This is probably the highest-leverage issue in the current CLI. Agents should never have to regex task IDs out of "Created task: ..." prose.

Minimum mutation envelope:

```json
{
  "success": true,
  "operation": "task.create",
  "task": {},
  "warnings": []
}
```

Minimum error envelope:

```json
{
  "success": false,
  "operation": "task.update",
  "error": {
    "code": "ambiguous_status",
    "message": "Status name matched multiple statuses",
    "candidates": []
  }
}
```

### Treat unknown arguments as errors

Linear's changelog explicitly calls out changing unknown MCP parameters from silent drops to validation errors (https://linear.app/changelog). `clickup-tools` should do the same. For agents, a silently ignored flag is worse than a hard failure because the agent may proceed under a false belief.

### Distinguish omitted, null, empty, and zero

Linear's MCP changelog notes the importance of serializing explicit zero values correctly (https://linear.app/changelog). In our CLI:

- omitted means do not change
- empty string should usually be rejected unless it has a clear meaning
- `null` or `--clear FIELD` should clear a field
- `0` should remain a real value when the backing API supports it

This matters for priority, points, due dates, assignees, tags, and custom fields.

### Make comments appendable and separately addressable

Add a clean comment primitive:

```bash
cup task comment TASK_ID --body-file note.md --format json
```

Return the comment ID and URL. Do not conflate comments with task descriptions.

### Keep status semantics workspace-local

Do not assume `waiting`, `on deck`, `in progress`, or `done` exist globally. Support configured aliases if we want convenience:

```bash
cup config set status.started "in progress"
cup task start TASK_ID --format json
```

But the canonical command should still be `task save/update --status ...`, and it should resolve status against the task's actual list/workflow.

### Consider an MCP server after the CLI interface stabilizes

Linear's strongest agent surface is not just a CLI; it is a remote MCP server with schemas, OAuth, and tool documentation. For `clickup-tools`, a local MCP server could wrap the same service layer as the CLI and expose a smaller tool list:

- `get_task`
- `list_tasks`
- `save_task`
- `save_comment`
- `list_lists`
- `list_statuses`
- `list_users`

That is probably better than exposing every CLI command as a separate tool. Agents do better with a few high-quality tools than many overlapping commands.

## Recommended `clickup-tools` Direction

The current open issues feel piecemeal because they are optimizing individual commands without first defining the agent contract. The Linear-inspired contract should be:

1. **Canonical sparse mutation:** one save/update task operation with optional fields.
2. **Canonical structured read:** list/get operations that return chainable IDs and URLs.
3. **Explicit discovery:** list statuses/users/lists/tags so agents can resolve names safely.
4. **Strict JSON:** every command supports machine-readable success and error envelopes.
5. **No invented workflow semantics:** use ClickUp-native fields and configured aliases, not hidden assumptions.
6. **Small MCP-shaped surface:** design the CLI now so it can later be wrapped by an MCP server without redesign.

This reframes the issue backlog. Instead of adding individual filters, blocked-by metadata, or isolated output fixes, first create the stable agent contract. After that, filters and convenience commands become easy aliases over a coherent model.

## Sources

- Linear MCP server documentation: https://linear.app/docs/mcp
- Linear GraphQL API getting started: https://linear.app/developers/graphql
- Linear TypeScript SDK getting started: https://linear.app/developers/sdk
- Linear SDK fetching and modifying data: https://linear.app/developers/sdk-fetching-and-modifying-data
- Linear Agent Interaction Guidelines: https://linear.app/developers/aig
- Linear Agents getting started: https://linear.app/developers/agents
- Linear Agent interaction best practices: https://linear.app/developers/agent-best-practices
- Linear Agent product docs: https://linear.app/docs/linear-agent
- Linear issue creation docs: https://linear.app/docs/creating-issues
- Linear issue status/workflow docs: https://linear.app/docs/configuring-workflows
- Linear assignment and delegation docs: https://linear.app/docs/assigning-issues
- Linear labels docs: https://linear.app/docs/labels
- Linear filters docs: https://linear.app/docs/filters
- Linear MCP for product management changelog, February 5, 2026: https://linear.app/changelog/2026-02-05-linear-mcp-for-product-management
- Linear changelog MCP/API entries: https://linear.app/changelog
- Linear SDK package, inspected at `@linear/sdk@84.0.0`: https://www.npmjs.com/package/@linear/sdk
- Linear SDK repository: https://github.com/linear/linear
- Third-party MCP catalog for observed Linear MCP tool list, treated as corroborating not authoritative: https://www.speakeasy.com/product/mcp-gateway/catalog/linear
