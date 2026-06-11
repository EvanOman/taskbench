# Standard Task Backend contract

`openapi.yaml` defines the HTTP contract a server must implement to act as a
backend for this CLI. It is the HTTP projection of the Python `TaskProvider`
protocol in `clickup/core/providers.py`.

**Source of truth: the Python protocol.** The spec is derived from it. If you
change `TaskProvider` (or the pydantic models it returns), update the spec in
the same PR.

## Why this exists

The CLI talks to backends through `TaskProvider`, an in-process Python
protocol. That is the cheapest extension point if you're writing Python in
this repo — but invisible to everyone else. The OpenAPI spec gives non-Python
adopters a target: implement this small REST surface (any language, typically
as a thin shim in front of your existing tool) and the CLI can drive it via
the generic provider with zero code changes here.

## Two ways to add a backend

| Route | Write | Best when |
|---|---|---|
| **Native adapter** | A Python class implementing `TaskProvider`, registered in `get_provider()` | You're contributing to this repo; the backend has a Python SDK (see `planka_provider.py`) |
| **Spec-conformant shim** | An HTTP service implementing `spec/openapi.yaml` | You don't want to touch this repo; your backend logic isn't Python; you want one shim to serve many CLI installs |

The generic provider (`CLICKUP_PROVIDER=generic`, planned — see Status below)
speaks exactly this spec.

## Protocol ↔ endpoint mapping

| `TaskProvider` method | HTTP |
|---|---|
| `get_user` / `validate_auth` | `GET /me` (200 = valid, 401 = invalid)¹ |
| `get_teams` | `GET /workspaces` |
| `get_team` | `GET /workspaces/{id}` |
| `get_team_members` | `GET /workspaces/{id}/members` |
| `get_spaces` | `GET /workspaces/{id}/spaces` |
| `get_space` | `GET /spaces/{id}` |
| `get_folders` | `GET /spaces/{id}/folders` |
| `create_folder` | `POST /spaces/{id}/folders` |
| `get_folder` | `GET /folders/{id}` |
| `get_lists` | `GET /folders/{id}/lists` |
| `create_list` | `POST /folders/{id}/lists` |
| `get_folderless_lists` | `GET /spaces/{id}/lists` |
| `create_folderless_list` | `POST /spaces/{id}/lists` |
| `get_list` | `GET /lists/{id}` |
| `get_tasks` | `GET /lists/{id}/tasks` (+ filter query params) |
| `create_task` | `POST /lists/{id}/tasks` |
| `get_task` | `GET /tasks/{id}` |
| `update_task` | `PATCH /tasks/{id}` |
| `delete_task` | `DELETE /tasks/{id}` |
| `get_task_comments` | `GET /tasks/{id}/comments` |
| `create_comment` | `POST /tasks/{id}/comments` |
| `search_tasks` | `GET /workspaces/{id}/search/tasks` |
| `raw_request` | **not in the spec** — backend-native escape hatch, not portable |
| — | `GET /capabilities` (no protocol equivalent; formalizes adapter degradation) |

¹ `validate_auth` returns `(bool, str, User | None)` in the protocol; over
HTTP the boolean is carried entirely by the status code (200 → `(True, ...,
User)`, 401 → `(False, ..., None)`) and the body is just a `User`. A bare 401
with no body is valid — clients must not require an error envelope here.

## Design decisions

**Vocabulary follows the CLI, not the backend.** Workspace → space →
folder → list → task → comment. The CLI's JSON output, models, and flags all
use these terms; a shim translates once (its tool's terms → spec terms)
instead of every consumer translating differently. The Planka adapter's
mapping (project→space, board→list, column→status, card→task) is the worked
example.

**Folders are optional, not core.** Planka proved a backend can live without
them: declare `folders: false` in `/capabilities`, or synthesize one
placeholder folder per space (`folder_<spaceId>`). Same choice for `search`
and `delete_tasks`.

**Capability discovery beats faking it.** `GET /capabilities` returns flags;
omitted keys default to true; a 404 on the endpoint means "everything
supported". Unsupported calls return `400` with error code `unsupported`.

**Wire formats are ClickUp-shaped on purpose.** Epoch-ms-string timestamps,
string IDs (integer user IDs), priority written as int 1–4 / read as an
object, `task_count` as a string on folders. These are warts, but the CLI's
pydantic models already speak them, and inventing a cleaner wire format would
force a translation layer inside the CLI for zero user-visible benefit.

**Modify-if-passed is contractual.** `PATCH /tasks/{id}` only touches fields
present in the body, and an explicit `""` clears a field. This mirrors the
CLI's update semantics (AGENT.md, architecture decision 3) — a server that
treats absent and empty as the same will corrupt agent workflows.

**All schemas are open.** Servers may add fields; clients must ignore unknown
fields (models use `extra="allow"`). `comment_count` on tasks and `statuses`
on lists are RECOMMENDED extras the CLI already understands.

**Errors are a typed envelope.** `{"error": {"code", "message"}}` with codes
mapping 1:1 onto `clickup/core/exceptions.py`
(`authentication`/`authorization`/`not_found`/`validation`/`rate_limit`/
`unsupported`/`server`). 429 responses should include `Retry-After`.

**No pagination (yet).** No CLI call site passes paging filters; collections
return everything. If a backend can't, that's the first thing to version the
spec for.

**Filter honesty.** Servers MUST honor `statuses` and `include_closed` on
`GET /lists/{id}/tasks`; the date filters SHOULD be honored but the CLI
treats server-side filtering as best-effort.

## Conformance levels

- **Minimal**: `/me`, `/workspaces*`, `/spaces/{id}/lists`, `/lists/{id}`,
  `/lists/{id}/tasks` (GET+POST), `/tasks/{id}` (GET+PATCH), comments, and
  `/capabilities` declaring everything else false. This is enough for the
  CLI's core agent workflow (discover → list → create → update → comment).
- **Full**: everything in the spec.

## Status

- [x] Spec drafted (v0.1.0)
- [ ] `GenericProvider` adapter (`CLICKUP_PROVIDER=generic`, reads `TASKBACKEND_URL` + `TASKBACKEND_TOKEN`)
- [ ] Conformance test suite runnable against any base URL
