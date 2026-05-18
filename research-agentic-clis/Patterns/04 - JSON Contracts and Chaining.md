---
tags:
  - ai-generated
  - agentic-cli
  - json-contracts
---

# JSON Contracts and Chaining

## Executive Summary

Agent-friendly CLIs need to behave less like terminal narrators and more like typed local APIs. The strongest pattern across mature tools is not merely "support JSON"; it is "make machine mode an explicit, stable contract where stdout contains one parseable value, stderr contains diagnostics, exit codes distinguish failure classes, and every successful mutation returns the resource or an operation result that can feed the next command." `clickup-tools` is already close on read commands because several renderers emit `{"data": [...], "count": n}`, but mutation commands still emit prose-shaped success messages in JSON mode. The next design pass should define one envelope, one error shape, one pagination shape, and one mutation-result shape, then migrate commands to that contract instead of adding more piecemeal flags.

## Detailed Findings

### 1. Machine mode must be explicit, parseable, and free of human prose

The clearest shared lesson from mature CLIs is that machine-readable output needs an explicit mode and a clean stdout stream. GitHub CLI documents that commands default to line-based plain text, while commands that support `--json` convert output to JSON and can then be filtered with `--jq` or formatted with `--template` [GitHub CLI formatting](https://cli.github.com/manual/gh_help_formatting). Azure CLI goes further: JSON is the default output format, and `--output none` exists for commands where output is sensitive or unnecessary [Azure CLI output formats](https://learn.microsoft.com/en-us/cli/azure/format-output-azure-cli?view=azure-cli-lts). AWS CLI also treats JSON as a first-class output format and documents separate `json`, `yaml`, `yaml-stream`, `text`, and `table` modes [AWS CLI output formats](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-output-format.html).

For agents, the practical rule is stricter than for shell users: when `--format json` is active, stdout should contain exactly one valid JSON value and no decorative text. A human can ignore "Created task: Foo"; an agent has to parse around it. If a command succeeds, stdout should be either a resource object or a documented result envelope. If there is no useful output, stdout should be empty or a structured success object, not a sentence.

The Command Line Interface Guidelines make the stream split explicit: primary output belongs on stdout, while errors and diagnostics belong on stderr [CLI Guidelines](https://clig.dev/). Fuchsia's CLI guidelines make the same distinction and also state that tools should accept explicit programmatic mode even when running in an interactive shell [Fuchsia CLI guidelines](https://fuchsia.dev/fuchsia-src/development/api/cli). That matters for LLM agents because they often run commands through pseudo-terminals; TTY detection alone is not a reliable signal of the intended contract.

**Implication for `clickup-tools`:** `--format json` should be a hard contract. No success prose, bullets, Rich tables, emojis, progress narration, or "Found n task(s)" messages should appear on stdout in JSON mode. Warnings can go to stderr as structured diagnostics, but the main stdout payload must remain parseable.

### 2. JSON support is most useful when the CLI exposes both raw data and field selection

GitHub CLI's `--json fields` design has two strengths: it makes the caller name the fields they need, and it pairs JSON output with built-in `--jq` and `--template` support [GitHub CLI formatting](https://cli.github.com/manual/gh_help_formatting). This is probably part of why models handle `gh` well, but prevalence in training data is not the whole explanation. The command grammar itself is agent-friendly: `gh pr view 123 --json title,state,url` returns a small typed object, and `--jq .url` extracts the next argument without additional shell tooling.

gcloud shows the richer version of the same idea. It supports a global `--format` flag with formats such as `json`, `yaml`, `table`, `value`, `csv`, `none`, and `multi`, and it lets callers shape output with format expressions [gcloud format reference](https://cloud.google.com/sdk/gcloud/reference/topic/formats). Azure and AWS both use JMESPath-style query flags to let callers reduce output before it reaches the next command [Azure CLI output formats](https://learn.microsoft.com/en-us/cli/azure/format-output-azure-cli?view=azure-cli-lts), [AWS CLI output formats](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-output-format.html).

The agent-specific lesson is not that `clickup-tools` must implement a full query language immediately. It is that the CLI should make common extraction paths obvious. Agents often need exactly one ID, URL, status, or count. A stable JSON schema plus `--jq` would be ideal. A smaller first step is to keep every payload shallow enough that `jq -r '.data[0].id'` and `jq -r '.task.id'` are predictable.

**Implication for `clickup-tools`:** prefer stable field names over presentation-specific strings. Add `--jq` later if useful, but design the JSON now so field selection is obvious. Avoid output shapes where a caller has to know that create returns `message` while get returns a task object.

### 3. Collection envelopes should be consistent: `data`, `count`, and pagination metadata

Several established systems converge on collection envelopes rather than bare arrays. Stripe list responses use a top-level object with `object: "list"`, `url`, `has_more`, and `data` [Stripe pagination](https://docs.stripe.com/api/pagination?lang=curl). JSON:API defines top-level `data` and recommends pagination links under top-level `links` with keys such as `first`, `last`, `prev`, and `next` [JSON:API pagination](https://jsonapi.org/format/index.html). GitHub's REST API keeps paginated arrays in the response body but exposes navigation in the HTTP `Link` header [GitHub REST pagination](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api?ref=blog.julescheron.com).

For a CLI, HTTP headers are usually lost, so pagination metadata belongs in the JSON body. The most useful minimal envelope for agent chaining is:

```json
{
  "data": [],
  "count": 0,
  "next_page": null,
  "has_more": false
}
```

If the upstream API is page-based, `next_page` can be an integer. If it is cursor-based, `next_page` can be a cursor string. If the command fetched all pages, `next_page` should be `null` and `has_more` should be `false`. The important part is not the exact name; it is that agents should never infer "there are no more tasks" from `count < limit` unless the contract says that is valid.

Kubernetes adds a useful nuance: list responses can represent a consistent snapshot using list metadata and continuation tokens, so clients can continue without accidentally mixing incompatible snapshots [Kubernetes API concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/). `clickup-tools` probably does not need snapshot semantics, but it should preserve enough pagination state that an agent can safely continue a list operation without guessing.

**Implication for `clickup-tools`:** keep the existing `data` and `count` convention, but standardize it everywhere. Add `limit`, `next_page`, and `has_more` when a command can be paginated. Do not return bare arrays from some list commands and envelopes from others.

### 4. Single-resource commands should return the resource, not a message envelope

Read commands like `task get` naturally return a task object. Mutation commands should do the same whenever the upstream API returns the changed resource. This is the strongest difference between a human CLI and an agentic CLI. A human wants confirmation; an agent wants the ID, URL, status, and resulting fields for the next step.

MCP's tool design makes this explicit. Tool results can include `structuredContent`, and tools may publish an `outputSchema`; if they do, servers must return structured results that conform to the schema and clients should validate them [MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools). The MCP schema reference also distinguishes tool-originated errors from protocol errors using `isError` and structured result content [MCP schema reference](https://modelcontextprotocol.io/specification/2025-11-25/schema). That is a good mental model for a CLI used by agents: the CLI command is a local tool call, and the output should be the structured result, not an explanation of the result.

`clickup-tools` currently has the mixed pattern this report is meant to fix. Renderers such as `render_tasks` already output `{"data": [...], "count": n}` in JSON mode. But task mutations such as create, update, status changes, and delete use message renderers, so JSON mode can produce `{"message": "Created task: ...", "level": "success"}` rather than the created task. That breaks chaining because the agent has to regex an ID out of a sentence or issue a second `task get`.

**Implication for `clickup-tools`:** define mutation outputs as resources or operation envelopes:

```json
{
  "data": {
    "id": "abc123",
    "name": "Write report",
    "status": {"status": "in progress"},
    "url": "https://app.clickup.com/t/abc123"
  }
}
```

For deletes or commands where the resource is no longer retrievable:

```json
{
  "data": {
    "id": "abc123",
    "deleted": true
  }
}
```

Avoid `{"message": "Deleted task abc123"}` in machine mode.

### 5. Error shape should be structured, stable, and paired with meaningful exit codes

Errors need two contracts: process-level status and JSON-level details. The process-level rule is old and still correct: exit code `0` means success, non-zero means failure [CLI Guidelines](https://clig.dev/). Fuchsia's CLI guidelines reserve `0` for no error and `1` for a general error, while allowing more specific codes for other cases [Fuchsia CLI guidelines](https://fuchsia.dev/fuchsia-src/development/api/cli). Pulumi documents a richer mapping, including separate codes for general errors, configuration or validation errors, and detected changes [Pulumi CLI exit codes](https://www.pulumi.com/docs/iac/cli/exit-codes/).

For JSON error bodies, RFC 9457 is the best primary source. It standardizes Problem Details as a JSON object with fields such as `type`, `title`, `status`, `detail`, and `instance`, with extension members allowed for domain-specific data [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html). JSON-RPC has a similar but smaller error object with numeric `code`, short `message`, and optional `data`; MCP inherits that for protocol-level errors [MCP schema reference](https://modelcontextprotocol.io/specification/2025-06-18/schema).

For a CLI, the HTTP `status` field is less important than the process `exit_code`, but the shape transfers well:

```json
{
  "error": {
    "type": "https://clickup-tools/errors/usage",
    "title": "Invalid argument",
    "detail": "--sort direction must be 'asc' or 'desc'.",
    "exit_code": 2,
    "command": "task list",
    "retryable": false
  }
}
```

For API failures:

```json
{
  "error": {
    "type": "https://clickup-tools/errors/clickup-api",
    "title": "ClickUp API request failed",
    "detail": "Rate limited",
    "exit_code": 1,
    "upstream_status": 429,
    "retryable": true
  }
}
```

The current `clickup-tools` JSON error shape is `{"error": "..."}`. That is parseable, but too thin for an agent to self-correct. It does not distinguish invalid user input from missing config, authentication failure, not found, rate limit, or upstream server failure.

**Implication for `clickup-tools`:** preserve stderr for errors, but make JSON stderr structured. Use exit code `2` for usage and validation errors, `1` for runtime/API errors, and consider `3` for not-found or no-match only if command semantics need it. Include `retryable`, `upstream_status`, and `field` or `argument` where possible.

### 6. Idempotency matters more for agents than for humans

Agents retry. They lose context. They may run the same command again after a timeout because they cannot tell whether the mutation succeeded. That makes idempotency a first-class CLI concern.

Stripe's API is the cleanest source pattern: clients provide an idempotency key for create/update requests, and Stripe stores the resulting status code and body of the first request for that key so retries return the same result instead of duplicating the operation [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests?api-version=2024-11-20.acacia). Stripe also compares reused keys against incoming parameters to prevent accidental misuse.

ClickUp's API may not expose an equivalent idempotency header for every mutation. That does not mean `clickup-tools` should ignore the problem. The CLI can still provide local and semantic idempotency patterns:

- For create commands, support `--idempotency-key KEY` and store a local key-to-result cache for a short TTL.
- Support `--external-id` only if ClickUp has a real field or configured custom field that can be queried before create.
- For "ensure" style commands, prefer idempotent semantics: `task ensure --name X --list-id Y` can search then create, while `task create` always creates.
- For updates, return before/after or changed fields so an agent can tell whether a retry changed anything.

**Implication for `clickup-tools`:** do not try to make all creates magically idempotent, but provide an explicit `--idempotency-key` or separate `ensure` command for agent workflows. Document which commands are safe to retry.

### 7. Dry-run should return the planned operation in the same shape as execution

Dry-run is valuable for agents because it lets them validate inputs, permissions, and resolution logic before mutating remote state. Kubernetes has a strong pattern with `--dry-run=client|server`: client dry-run prints the object that would be sent without sending it, while server dry-run submits the request but does not persist the resource [kubectl reference](https://kubernetes.io/docs/reference/kubectl/kubectl-cmds/). AWS EC2's `--dry-run` checks whether the caller has permissions without making the real request and returns specific dry-run outcomes such as `DryRunOperation` or `UnauthorizedOperation` [AWS CLI EC2 dry-run reference](https://docs.aws.amazon.com/cli/v1/reference/ec2/wait/instance-running.html).

For `clickup-tools`, dry-run should not be a human-only preview table. In JSON mode, it should return a typed plan:

```json
{
  "data": {
    "dry_run": true,
    "operation": "task.update",
    "target": {"task_id": "abc123"},
    "changes": {
      "status": {"from": "on-deck", "to": "in progress"},
      "priority": {"from": 4, "to": 2}
    },
    "request": {
      "method": "PUT",
      "path": "/task/abc123",
      "body": {"status": "in progress", "priority": 2}
    }
  }
}
```

There is an important product distinction: client dry-run can validate CLI parsing and config resolution; server dry-run requires upstream support. If ClickUp does not provide non-persistent validation for a mutation, the CLI should call it `--dry-run=client` or simply `--plan`, not imply server validation.

**Implication for `clickup-tools`:** make dry-run output machine-readable and explicit about what was and was not verified. Existing bulk dry-run behavior should be converted from preview prose/tables to an operation plan in JSON mode.

### 8. Batch operations need per-item results and an aggregate status

Batch commands are common in agent workflows because they reduce round trips. They are also where output contracts often fail. A sentence like "Bulk update completed: 8 updated, 2 failed" loses the only information the agent needs: which two failed and why.

The right shape is an aggregate plus per-item result list:

```json
{
  "data": [
    {
      "id": "task1",
      "ok": true,
      "operation": "task.update",
      "result": {"id": "task1", "status": {"status": "complete"}}
    },
    {
      "id": "task2",
      "ok": false,
      "operation": "task.update",
      "error": {
        "type": "https://clickup-tools/errors/not-found",
        "title": "Task not found",
        "detail": "No task found for task2",
        "retryable": false
      }
    }
  ],
  "count": 2,
  "succeeded": 1,
  "failed": 1,
  "partial_failure": true
}
```

Exit-code policy should be explicit. A pragmatic contract is: exit `0` only when every requested item succeeded; exit `1` when any item failed at runtime; exit `2` when the batch request itself is invalid before item execution begins. If there is a strong need to let agents continue after partial success, add `--allow-partial` but still include `partial_failure: true`.

This mirrors MCP's distinction between a tool call that returns a structured error result the model can inspect and a protocol-level error that prevents the tool call from being understood [MCP schema reference](https://modelcontextprotocol.io/specification/2025-11-25/schema). In CLI terms, a malformed CSV is a command error; one row failing is an item error.

**Implication for `clickup-tools`:** all bulk commands should return a batch result envelope in JSON mode. Per-item errors should use the same error object as top-level errors.

### 9. Stable schemas are more important than pretty schemas

Terraform's machine-readable UI is instructive because it treats JSON as a versioned event stream. Long-running commands such as `plan`, `apply`, `refresh`, and `test` emit a stream of JSON UI messages under `-json`, with fields like message type and timestamp [Terraform machine-readable UI](https://developer.hashicorp.com/terraform/internals/machine-readable-ui). Terraform also documents separate JSON formats for plans and state [Terraform JSON format](https://developer.hashicorp.com/terraform/internals/json-format). The lesson is not that `clickup-tools` needs event streams; it is that machine output deserves its own documented compatibility surface.

Agent reliability depends on stable names and additive change. Renaming `priority_label` to `priority_name` is a breaking change even if humans would not notice. Changing a single-resource response from `{...task...}` to `{"data": {...task...}}` is a breaking change. Returning a string where a number was previously returned is a breaking change.

The safest versioning policy is:

- Add fields freely.
- Do not remove or rename fields inside a major contract version.
- Use `null` for known-but-empty fields.
- Omit fields only when the concept does not apply.
- Keep timestamps in ISO 8601 strings in JSON mode.
- Keep IDs as strings even if they look numeric.
- Document whether list order is stable and what the default sort is.

**Implication for `clickup-tools`:** create a short `docs/json-contract.md` or equivalent before implementation. Tests should parse JSON and assert keys for every command, especially mutations.

### 10. Human output and agent output should be separate products

Azure's `table` documentation explicitly warns that nested objects are not included in table output, making it useful for quick human scanning but incomplete as data [Azure CLI output formats](https://learn.microsoft.com/en-us/cli/azure/format-output-azure-cli?view=azure-cli-lts). That is the right distinction. Human table output can be lossy. Machine JSON output cannot.

The worst pattern is a hybrid output that tries to satisfy both consumers: JSON plus explanatory text, tables plus hidden IDs, or success messages that embed values in prose. Agents do not benefit from "friendly" output; they benefit from low-entropy contracts. Humans can still use `--format table`.

**Implication for `clickup-tools`:** optimize JSON for agents and table output for humans. Do not make JSON prettier at the cost of stability. Do not make table output complete at the cost of readability.

## Concrete Design Lessons for `clickup-tools`

### Recommended JSON contract

Use one top-level envelope for every JSON success response:

```json
{
  "data": {},
  "meta": {
    "command": "task.create",
    "api": "clickup",
    "dry_run": false
  }
}
```

For collections:

```json
{
  "data": [],
  "count": 0,
  "next_page": null,
  "has_more": false,
  "meta": {
    "command": "task.list",
    "limit": 50,
    "sort": "updated:desc"
  }
}
```

For no-output success:

```json
{
  "data": {
    "ok": true
  },
  "meta": {
    "command": "config.set"
  }
}
```

This is slightly more verbose than the current mixed approach, but it eliminates command-specific guessing. The value of `data` is always the thing the caller asked for. The value of `meta` is always operational context.

### Recommended error contract

In JSON mode, stderr should contain:

```json
{
  "error": {
    "type": "https://clickup-tools/errors/usage",
    "title": "Invalid argument",
    "detail": "Task ID is required.",
    "exit_code": 2,
    "command": "task.status",
    "argument": "task_id",
    "retryable": false
  }
}
```

Use:

- `exit_code: 0` for complete success.
- `exit_code: 1` for runtime/API errors.
- `exit_code: 2` for usage, validation, missing required config, or unsafe command refusal.
- Optional future codes only if agents can act differently on them.

Top-level stdout should be empty on failure unless there is a partial batch result. For partial batches, stdout can contain the batch result and stderr can contain a summary error object, but this must be documented.

### Recommended mutation outputs

Change these commands first:

- `task create`: return the created task under `data`.
- `task update`: return the updated task under `data`.
- `task status`, `task done`, `task start`, `task park`: return the updated task under `data`.
- `task delete`: return `{ "id": "...", "deleted": true }` under `data`.
- `comments add`: return the created comment under `data`.
- `config set`: return `{ "key": "...", "value": "...", "updated": true }`.

Do not return success messages in JSON mode. If human copy is needed, put it in table mode only.

### Recommended collection outputs

Keep `data` and `count`, but extend list/search commands:

```json
{
  "data": [{ "id": "task1" }],
  "count": 1,
  "limit": 50,
  "next_page": null,
  "has_more": false,
  "meta": {
    "command": "task.list",
    "list_id": "901"
  }
}
```

If the upstream ClickUp endpoint cannot produce reliable `has_more`, document that `has_more` is `null` until pagination is implemented. Do not fake certainty.

### Recommended dry-run and plan mode

Add `--dry-run` only where output can be useful and honest. For task updates, dry-run should resolve the target and show planned changes. For creates, dry-run should show the request body and resolved list ID. For bulk operations, dry-run should return the same batch envelope as execution, with `dry_run: true` and without result resources.

### Recommended idempotency policy

Document retry safety per command:

| Command type | Retry safety | Recommendation |
|---|---:|---|
| `get`, `list`, `search` | Safe | No idempotency key needed |
| `update status`, `update fields` | Usually safe if setting absolute values | Return updated resource |
| `create` | Unsafe | Add `--idempotency-key` or separate `ensure` command |
| `delete` | Potentially unsafe if IDs are reused upstream, usually safe for same ID | Return deleted ID and tolerate already-deleted only if explicitly designed |
| `bulk` | Mixed | Return per-item results and support resume/retry from failed items |

Do not silently deduplicate creates by title. That crosses from output contract into product behavior and can surprise users.

### Recommended batch contract

Bulk commands should return:

```json
{
  "data": [],
  "count": 0,
  "succeeded": 0,
  "failed": 0,
  "partial_failure": false,
  "meta": {
    "command": "bulk.update",
    "dry_run": false
  }
}
```

Each item should include `ok`, `operation`, `id` when known, and either `result` or `error`. This allows an agent to retry only failed items.

### Recommended implementation sequence

1. Define internal helpers: `render_success(data, meta=None)`, `render_collection(data, count=None, pagination=None, meta=None)`, and `render_error_object(...)`.
2. Migrate task mutation commands to return resources in JSON mode.
3. Migrate config/list/workspace mutations to structured JSON.
4. Migrate bulk commands to per-item batch envelopes.
5. Add integration tests that invoke every command with `--format json` and assert stdout is valid JSON or intentionally empty.
6. Add tests that assert stderr error JSON has `error.type`, `error.title`, `error.detail`, `error.exit_code`, and process exit code alignment.
7. Document the contract in the README or a dedicated agent contract doc.

## Sources

- GitHub CLI manual, formatting JSON output, `--json`, `--jq`, and `--template`: https://cli.github.com/manual/gh_help_formatting
- GitHub CLI reference showing JSON-related flags across commands: https://cli.github.com/manual/gh_help_reference
- Azure CLI output formats: https://learn.microsoft.com/en-us/cli/azure/format-output-azure-cli?view=azure-cli-lts
- AWS CLI output formats: https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-output-format.html
- gcloud format reference: https://cloud.google.com/sdk/gcloud/reference/topic/formats
- Command Line Interface Guidelines: https://clig.dev/
- Fuchsia command-line interface guidelines: https://fuchsia.dev/fuchsia-src/development/api/cli
- Model Context Protocol tools specification, structured content and output schemas: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- Model Context Protocol schema reference, tool result and JSON-RPC error shapes: https://modelcontextprotocol.io/specification/2025-11-25/schema
- RFC 9457, Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
- Stripe API pagination: https://docs.stripe.com/api/pagination?lang=curl
- Stripe idempotent requests: https://docs.stripe.com/api/idempotent_requests?api-version=2024-11-20.acacia
- JSON:API specification, pagination and top-level document structure: https://jsonapi.org/format/index.html
- GitHub REST API pagination: https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api?ref=blog.julescheron.com
- Kubernetes API concepts, list continuation and resource versions: https://kubernetes.io/docs/reference/using-api/api-concepts/
- kubectl command reference, dry-run modes: https://kubernetes.io/docs/reference/kubectl/kubectl-cmds/
- AWS CLI EC2 dry-run behavior: https://docs.aws.amazon.com/cli/v1/reference/ec2/wait/instance-running.html
- Terraform machine-readable UI: https://developer.hashicorp.com/terraform/internals/machine-readable-ui
- Terraform JSON format: https://developer.hashicorp.com/terraform/internals/json-format
- Pulumi CLI exit codes: https://www.pulumi.com/docs/iac/cli/exit-codes/
