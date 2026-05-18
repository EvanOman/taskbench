---
tags:
  - ai-generated
  - agentic-cli
  - product-strategy
---

# Contrarian Product Lens: Agentic ClickUp CLI

## Executive Summary

The strongest version of clickup-tools is probably smaller than the issue list suggests. For a short-horizon personal to-do queue operated by agents, the CLI should not become a workflow system, a schema extension layer, or a ClickUp opinion engine. It should be a narrow, reliable adapter that turns common agent intentions into deterministic ClickUp API calls and machine-readable results. Most "nice to have" semantics belong in prompts, ClickUp configuration, MCP tools, or direct API escape hatches until repeated agent failures prove they deserve a first-class CLI command.

The product bet should be: make the happy path boring, inspectable, and hard to corrupt. Agents do not need human-friendly terminal ergonomics. They need stable contracts, idempotent-ish mutations, compact JSON, clear errors, and a small set of verbs that map cleanly to ClickUp's real data model.

## Product Decision 1: The CLI Should Be an Agent Adapter, Not a Workflow Engine

The tempting mistake is to encode Evan's current task-management habits into the CLI: "waiting on" boards, blocker semantics, query aliases, custom list groupings, status workflows, and convenience flags for every recurring phrase. That makes sense when designing for a human terminal user who wants fewer keystrokes. It is less compelling for agents.

Agents are already good at composing small primitives if the primitives are predictable. They are less good at discovering hidden workflow assumptions. A command like `task update TASK_ID --status waiting` is understandable if the status exists in ClickUp. A command like `task update TASK_ID --blocked-by-pr URL` is less clear unless ClickUp has a native external-blocker field. It creates a product question the CLI cannot answer: where does that fact live, and what else should it imply?

The CLI should therefore avoid making workflow decisions. It should not infer that "blocked" means moving to a "Waiting On" board. It should not create custom fields, assume field names, or mutate descriptions with hidden metadata. It should expose ClickUp concepts cleanly and let prompts decide when to use them.

The rule of thumb:

- If ClickUp has a native field or relationship, the CLI can wrap it.
- If the user has configured a workspace-specific field, the CLI can write it explicitly.
- If the information only exists as a convention in prose, keep it in the prompt or task description until the convention becomes stable.

## Product Decision 2: Short-Horizon Personal Tasks Do Not Need Rich Blocker Modeling

The recent blocker-metadata discussion is a useful warning sign. "Waiting on PR" sounds structured, but for a personal queue it is often just context for a reminder. If the task is "Follow up after PR review," the title already carries the next action. Storing the PR URL in a special field only matters if the agent will later query, sort, or automate against that field.

For short-horizon tasks, the cost of modeling can exceed the benefit:

- The task may resolve before the metadata is ever queried.
- The agent has to learn a new command shape and failure mode.
- The user has to configure a ClickUp field or accept brittle description stuffing.
- Future agents may treat the metadata as authoritative even when the task title or comments have moved on.

ClickUp does have native task dependencies, so `blocked by another ClickUp task` can be represented cleanly. External blockers, such as GitHub PRs, do not appear to have an equivalent first-class task field in the standard task update schema. ClickUp custom fields can hold that data, but custom fields are workspace-specific. That means they should be opt-in configuration, not default product behavior.

Product call: do not implement external blocker metadata now. Keep native task dependencies as a possible small feature, but only if actual use shows agents need it.

## Product Decision 3: Agent Fluency Beats Human Convenience

For agent use, the most valuable CLI features are not the ones that save typing. They are the ones that reduce ambiguity after every operation.

The GitHub CLI is a useful reference point, but not because agents memorized its commands from training data. Prevalence helps, but the design itself has agent-friendly properties:

- Commands map to resource nouns and verbs: `issue list`, `issue view`, `issue edit`, `api`.
- JSON output is available for many read paths with explicit field selection.
- `--jq` and `--template` let callers shape output without adding new commands.
- `gh api` provides an escape hatch for unsupported cases without waiting for the CLI to grow.

The important lesson is not "copy gh's surface area." The lesson is "build a small stable core plus a raw API path." That lets the CLI stay opinion-light while still handling edge cases.

For clickup-tools, agent fluency means:

- Every mutation should be able to return JSON.
- Every JSON response should include the canonical task ID and URL.
- Errors should be structured enough for an agent to decide whether to retry, ask for config, or stop.
- List/view commands should return compact records by default, with an option for full records.
- The CLI should have a documented raw API escape hatch for rare fields and new ClickUp features.

This beats adding many bespoke commands. A model can recover from "field not supported, use raw API" more safely than from an undocumented pseudo-workflow baked into a convenience flag.

## Product Decision 4: Prompt Conventions Should Carry Soft Semantics

Some behavior belongs in the agent prompt, not the CLI. Prompt conventions are the right place for rules that are contextual, subjective, or likely to change.

Good prompt-convention examples:

- "When creating personal tasks, keep titles action-oriented and include the external reference in the title if it matters."
- "Do not move tasks between ClickUp lists unless the user explicitly asks."
- "Use the configured default list unless the user names another list."
- "For a GitHub PR follow-up, write `Follow up on PR review: owner/repo#123` rather than creating blocker metadata."
- "Prefer updating an existing task over creating a duplicate if a search finds a close match."

These are cheap to change and easy to inspect. They also match the actual product need: shape agent behavior around personal workflow without forcing the CLI to own that workflow.

Bad CLI-feature candidates are usually prompt rules in disguise:

- `--waiting-on-pr`
- `--personal-followup`
- `--triage-mode`
- `--next-action`
- `--stale`
- `--today`

Each may be useful language for an agent, but not necessarily a durable API. Put the convention in an agent instruction first. Promote it to CLI only when agents repeatedly fail to follow it despite clear prompting.

## Product Decision 5: ClickUp Configuration Should Carry Workspace-Specific Reality

ClickUp is flexible enough that the same words mean different things across workspaces. "Waiting on" might be a list, a status, a tag, a custom field, or nothing at all. The CLI should not pretend otherwise.

Workspace-specific facts belong in config:

- Default list ID.
- Workspace/team ID.
- Common status aliases, if needed.
- Optional custom field IDs.
- Optional named list aliases.
- Whether custom task IDs are used.

The CLI can make these easy to discover and validate, but it should not invent them. A good pattern is:

```bash
cup config set default_list_id 123
cup config set status_alias.waiting "waiting on"
cup config set field_alias.external_url abc123
cup task update TASK_ID --field external_url=https://github.com/org/repo/pull/123
```

This keeps the boundary honest. The CLI provides a typed route to configured ClickUp objects, but the user decides what those objects mean.

The practical product constraint: config should not become a programming language. A small map of aliases is useful. Conditional workflow rules are not. If a behavior needs conditionals, it probably belongs in the agent prompt or an MCP tool.

## Product Decision 6: MCP Tools May Be Better Than CLI Commands for Agent-Only Workflows

If the primary consumer is an LLM agent, MCP is a serious alternative to command growth. Linear's MCP server is a useful signal: it exposes tools for finding, creating, and updating objects directly to agents, with OAuth and client integration handled at the protocol layer. That shape avoids several CLI-specific problems:

- No shell quoting issues.
- Tool schemas can express optional arguments directly.
- Results are structured by default.
- The agent sees tool descriptions in its runtime context.
- Authentication and permissions can be scoped through the MCP connection.

For clickup-tools, this suggests a split:

- Keep the CLI as the local, scriptable, debuggable substrate.
- Consider MCP for the small set of agent-facing task operations once the command semantics stabilize.
- Do not use the CLI to simulate rich tool schemas through dozens of flags if a typed MCP tool would express the operation more cleanly.

The strongest MCP candidate is not a large task-management surface. It is probably one tool with a broad, optional update schema:

```text
update_task(
  task_id,
  name?,
  status?,
  due_date?,
  priority?,
  description_append?,
  assignees_add?,
  assignees_remove?,
  custom_fields?,
)
```

That mirrors what agents want: "change the known thing." The CLI can still expose `task update`, but MCP may be the better primary interface for agent-only contexts.

## Product Decision 7: Direct API Wrappers Are the Correct Escape Hatch

The worst reason to add a feature is "ClickUp supports it and an agent might need it someday." ClickUp's API surface is too large for that strategy. A raw API wrapper gives the project permission to stay small.

The `gh api` model is the right reference. It lets users and agents call endpoints that the polished CLI does not wrap yet. That reduces pressure to add one-off flags and provides a migration path: if the same raw API call appears often, promote it into a first-class command.

For clickup-tools, a raw API command should support:

- HTTP method selection.
- Path relative to the ClickUp API base.
- JSON request body from inline text or file.
- Query params.
- JSON output.
- Clear inclusion of request IDs or status codes on errors.

Example:

```bash
cup api GET /task/TASK_ID
cup api PUT /task/TASK_ID --json '{"status":"in progress"}'
cup api POST /task/TASK_ID/field/FIELD_ID --json '{"value":"https://github.com/org/repo/pull/123"}'
```

This feature prevents over-engineering elsewhere. It is the release valve.

## Product Decision 8: The Smallest High-Leverage Feature Set

The minimum high-leverage agentic CLI is not a feature-rich task app. It is a reliable read/update/create/delete adapter with structured output and a raw API path.

Recommended core:

1. `task create`

Create a task in a known list. Return JSON with `id`, `custom_id`, `name`, `status`, `url`, `list`, `due_date`, and `date_updated`.

2. `task update`

One update command with optional fields. It should support name, description or markdown content, status, priority, due date, assignees, tags, and maybe native dependencies. It should return the updated task in JSON.

3. `task list`

Filter by list, status, assignee, updated-since, created-since, due-before, due-after, and include-closed. Return compact JSON by default.

4. `task view`

Fetch a single task with full JSON. Include custom fields and relationships if ClickUp returns them.

5. `task comment`

Append a comment or update-style note. This is often better than mutating descriptions because it preserves history.

6. `config`

Manage default list, workspace/team ID, status aliases, list aliases, and field aliases.

7. `api`

Raw ClickUp API access for everything else.

8. Global output contract

`--format json` should be honored by every command, especially mutations. Agent consumers should not need to parse prose.

Everything else should be treated as suspect until proven.

## Product Decision 9: Over-Engineering Traps to Avoid

### Trap: Encoding Personal Workflow as Product Surface

If the command only makes sense in Evan's current board layout, it is config or prompt material. A `waiting on` board may be real in one ClickUp setup and nonexistent in another.

### Trap: Metadata Without a Native Home

If ClickUp has no first-class field for a concept, the CLI should not quietly hide it in descriptions. Hidden description markers create long-term data ambiguity. Custom fields are acceptable only when explicitly configured.

### Trap: Flag Proliferation as Prompt Repair

When agents misuse a command, the answer is not always a new flag. Often the answer is a better command description, a narrower tool schema, or a prompt rule.

### Trap: Query Features That Duplicate Agent Reasoning

Agents can filter JSON locally. The CLI should push filters down to ClickUp when doing so reduces pagination, rate limits, or ambiguity. It should not add every possible semantic filter just because the user can imagine asking for it.

### Trap: Human Niceties Masquerading as Agent Needs

Pretty tables, terminal colors, interactive pickers, and short aliases can be pleasant, but they do not improve agent reliability. They should not outrank JSON, stable IDs, and clear errors.

### Trap: Local State

Avoid local caches, local task mirrors, and local workflow state unless there is a hard performance or API-limit reason. For a short-horizon personal queue, ClickUp should remain the source of truth.

### Trap: Partial Abstractions Over ClickUp Oddities

ClickUp has custom task IDs, team IDs, list-specific statuses, custom fields, and separate endpoints for custom-field updates. A partial abstraction that hides those details until it fails is worse than exposing them honestly.

## Actionable Recommendations for clickup-tools

1. Reframe the roadmap around an "agent contract" issue.

The first milestone should be JSON consistency, not more task semantics. Every mutation should return structured JSON under `--format json`, and every command should have predictable exit behavior.

2. Close or defer issues that require invented metadata.

The blocker issue was correctly closed. Apply the same test to future features: if ClickUp does not natively store the concept and the user has not configured a field, do not add the command.

3. Implement a raw `cup api` command before adding more specialized flags.

This is the highest-leverage anti-bloat feature. It lets agents handle rare ClickUp operations while preserving a small core.

4. Collapse create/update ergonomics into one broad update surface.

Prefer a Linear-like `task update TASK_ID` with many optional fields over many tiny verbs. This fits agent use: the agent already knows the target task and desired changes.

5. Add field and status aliases through config, not code.

Make workspace-specific reality explicit:

```bash
cup config set list_alias.inbox 123
cup config set status_alias.waiting "waiting on"
cup config set field_alias.external_url abc123
```

Then allow generic field operations:

```bash
cup task update TASK_ID --field external_url=...
```

6. Keep query improvements narrow and API-grounded.

Add filters that ClickUp can execute or that materially reduce agent mistakes: `--status`, `--list-id`, `--updated-since`, `--created-since`, `--due-before`, `--due-after`, `--include-closed`. Do not add semantic filters like `--waiting-on-pr` until the storage model exists and is used.

7. Prefer comments over description rewrites for ongoing context.

Agents frequently need to leave a trace: "checked this, still waiting," "PR merged," "asked reviewer." A comment command is safer than constantly rewriting the task description.

8. Design for repair.

Every failure should tell the agent what to do next. Examples:

- Missing default list: "Set `default_list_id` or pass `--list-id`."
- Unknown status: "Status not found for this list. Run `cup task statuses --list-id ...`."
- Custom field alias missing: "Set `field_alias.external_url` or pass a raw field ID."

9. Write agent-facing docs, not only CLI help.

Add a short `AGENTS.md` or `docs/agent-usage.md` with canonical recipes:

- Create a task.
- Find recent open tasks.
- Update status.
- Append a comment.
- Avoid duplicate creation.
- Use raw API for unsupported ClickUp fields.

10. Evaluate features by observed agent failures.

Use this promotion rule:

- Once: fix the prompt.
- Twice: add a doc recipe.
- Three times with the same failure mode: improve CLI output/errors.
- Repeated after that: add a first-class command or MCP tool.

## What This Means for the Current Issues

The current issue list should be treated as raw product signals, not an implementation queue.

Agent-fluency work should move up. JSON output for mutations, compact task records, predictable errors, and a raw API escape hatch are foundational. They improve every future agent workflow without assuming a particular ClickUp setup.

Task-list filters are useful, but only the API-grounded filters should survive. The CLI should help agents retrieve the right candidate set, then let the model reason over JSON. It should not grow into a semantic query language for personal productivity.

Query convenience should be merged into the agent contract where possible. Sorting, default lists, and configured aliases are useful. Named lifestyle queries like "today," "stale," or "waiting" should remain prompt/config conventions until there is clear repeated usage.

Blocker metadata should stay closed for now. Native ClickUp dependencies may be worth wrapping later, but external blockers need explicit storage. Without that, the feature creates false structure.

## Sources

- GitHub CLI manual, "Formatting": documents `--json`, `--jq`, and `--template` as structured output and shaping mechanisms. https://cli.github.com/manual/gh_help_formatting
- GitHub CLI manual, `gh api`: documents raw API access and examples for calling GitHub endpoints directly. https://cli.github.com/manual/gh_api
- Linear MCP docs: describes Linear's MCP server as exposing tools for finding, creating, and updating objects such as issues, projects, and comments. https://linear.app/docs/mcp
- ClickUp API docs, "Update Task": notes that updating custom fields requires the Set Custom Field endpoint rather than the general task update endpoint. https://developer.clickup.com/reference/updatetask
- ClickUp API docs, "Tasks": describes task creation/update concepts and custom-field handling. https://developer.clickup.com/docs/tasks
- ClickUp Help, "Create Dependency Relationships in tasks": describes native task dependency relationships such as blocked-by and blocking. https://help.clickup.com/hc/en-us/articles/6309943321751-Create-Dependency-Relationships-in-tasks
