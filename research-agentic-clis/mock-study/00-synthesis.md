# JSON-backend mock study — synthesis

15 sub-agents drove the CLI against fresh JSON stores in parallel, each handed one
real-world use case and forbidden from reading source. This is what fell out.

## Headline finding

**The TaskProvider seam is only half-applied.** Only `clickup/cli/commands/task.py`
was migrated to `TaskProvider`. Every other command group — `list`, `discover`,
`workspace`, `api`, `bulk`, `templates`, `config`, `setup` — still constructs
`ClickUpClient` directly. With `provider: json` the workspace looks like a
chimera: `task ...` reads/writes the local store, but `list create`, `discover
hierarchy`, `workspace folders`, `list get`, etc. all silently hit the real
ClickUp API. Agent 11 hit this dead-on: created a list, was told it didn't
exist when adding a task to it.

This is the cleanest bug in the report and the most agent-hostile because it
can't be inferred from `--help`.

## Verdict distribution

| Verdict | Count | Agents |
|---|---|---|
| pass | 11 | 01, 02, 03, 05, 06, 07, 08, 09, 10, 13, 14 |
| partial | 4 | 04, 11, 12, 15 |
| fail | 0 | — |

The eleven "pass" verdicts are real — the basic agent workflow works — but the
friction sections still stacked up themes worth fixing.

## Theme summary

### JSON contract leaks (P0 — breaks pipelines)
- `task comments list` prints an info JSON line (`{"message": "N comment(s)"}`) on stdout next to the data envelope. Breaks `| jq`. (01, 06)
- `task search` empty result returns `{"message": "...", "level": "warn"}` instead of `{"data": [], "count": 0}`. (05)
- "No list ID configured" guidance leaks to stdout next to the JSON error on stderr. (15)
- Typer-level errors (unknown subcommand, bad `--limit abc`) emit Rich prose, not `{"error": ...}`. Agents that consistently parse the envelope miss these. (15)
- Status object returned by `task status`/`task start` has `color/type/orderindex` null, unlike the richer object from `task statuses`. Agents can't verify the move using `type == "custom"`. (01, 07)

### Input validation gaps (P0/P1)
- Priority `0`, `-1`, `99` silently accepted. Help says "1-4". (15)
- `--sort fartfield` silently ignored. No way for agent to know the sort didn't apply. (04, 15)
- Empty task name accepted. (15)
- JsonProvider accepts arbitrary status strings. (15)

### Cross-list view is broken (P0)
- `task list --all-lists --sort priority` does **per-list** sort then concatenates. `priority:asc` and `priority:desc` produce identical output. Agent 04 had to drop to `jq` to get a real priority-sorted view.

### Filter ergonomics (P1)
- No `--status STATUS` filter on `task list`. Forces "list all, scan with jq". (04, 08)
- No `--open-only` / `--exclude-closed` shorthand. Forces `--status "to do,in progress,on-deck"` after enumerating. (04)
- `task mine` has none of `task list`'s filters: no `--status`, `--sort`, `--priority`, `--updated-since`. Second-class for the most natural entry point. (03, 04, 08, 10)
- No `task list --name SUBSTR` filter; agents fall back to `task search` or jq. (12)

### Output verbosity (P2)
- 30+ fields per task in JSON, many null. Want `--fields a,b,c` or `--brief`. (04, 07, 12)
- Table mode for `task list` omits `date_updated`, hiding what `--updated-since` filtered on. (10)
- `config show` table mode truncates long values like `json_store_path`. (02)

### Discovery / inline-doc gaps (P2)
- Priority's inverted scale (1=urgent, 4=low) not in `--help`. (01, 03)
- Accepted units for `--updated-since` not enumerated. (10)
- Sort direction semantics for `priority` undocumented (does `asc` mean "1 first" or "4 first"?). (01)
- `--list-id` flag help shows `[default: None]` even when a config default is in play. (07, 11)

### Missing features (P2)
- No `task update --description-append TEXT`. Forces read-modify-write to extend a field. (12)
- No batch verb form: `task done id1 id2 id3 ...` variadic. (08)
- No `folder create`. (11)
- No `comment_count` on task objects → audits are N+1. (06)
- No way to list tasks across the whole workspace without pre-configuring `default_lists`. (06)

### Argument-style inconsistency (P3)
- `list get --list-id X` (option) vs `task get X` (positional). Same shape, different argument style. (11)

### `mock init` surprises (P3)
- Silently overwrites `json_store_path` in config to the global default even when `--path` was supplied to point elsewhere. (09)
- Defaults to JSON output regardless of config's `output_format: table`. (09)

### Diagnostic / observability (P3)
- `clickup status` returns `default_team_name`, `default_space_name`, `default_list_name` as null even when IDs are configured. (13)
- No `provider` field anywhere visible in `status` or `config show` output — agents can't tell whether they're talking to JSON or real ClickUp. (11)
- Update responses don't show a diff or echo previous→new. (03, 08)

## Cross-cutting takeaway

Agents that already know the CLI accomplish each scenario in 2–4 commands. New
agents accomplish them in 8–14, with most of the extra cost going to:

1. Discovering the priority scale.
2. Discovering which command-group routes to which provider.
3. Working around `--sort priority --all-lists` not actually sorting.
4. Working around the missing `--status`/`--name` filters on `task list`.

Fixing the JSON contract leaks and shipping the seam through all commands
removes the worst of the friction without adding any new surface area.
