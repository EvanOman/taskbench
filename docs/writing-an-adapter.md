# Writing a new backend adapter

How to add a backend as a native Python adapter. (If you'd rather not write
Python in this repo, implement `spec/openapi.yaml` as an HTTP shim instead —
see `spec/README.md`.)

`clickup/core/planka_provider.py` is the reference implementation: a complete
adapter for a backend whose concepts *don't* match the task hierarchy, showing
every degradation pattern below.

## Steps

### 1. Write the concept mapping first

Top-of-file docstring, before any code. Decide what maps to what and what
doesn't exist:

```python
"""Foo task provider — maps Foo's model to the TaskProvider protocol.

Concept mapping (TaskProvider -> Foo):
    Team/Workspace  -> synthetic singleton
    Space           -> Foo Project
    Folder          -> no-op (returns [] / synthetic placeholder)
    List            -> Foo Board
    Status          -> Foo Column
    Task            -> Foo Card
    Comment         -> Foo Comment
"""
```

If you can't fill this table in, stop — the adapter will be a pile of special
cases.

### 2. Implement `TaskProvider`

Create `clickup/core/foo_provider.py` with a class implementing every method
of the protocol (`clickup/core/providers.py`). It's a `typing.Protocol` —
no inheritance, just matching signatures. Rules:

- Return the pydantic models from `clickup/core/models.py`, never raw dicts.
- IDs on the wire are **strings** (stringify your backend's ints; see
  `_sid()` in the Planka adapter). User IDs stay integers.
- Timestamps are **epoch-ms strings** (`_iso_to_ms()` shows the conversion).
- Read connection config from env vars prefixed with your backend name
  (`FOO_URL`, `FOO_TOKEN`, ...), with sane localhost defaults.
- Raise the typed exceptions from `clickup/core/exceptions.py`
  (`NotFoundError`, `ValidationError`, `AuthenticationError`, ...) — `main.py`
  maps them onto exit codes and the stderr error envelope.

### 3. Degrade honestly, don't fake

For concepts your backend lacks:

| Missing concept | Pattern (from PlankaProvider) |
|---|---|
| Multi-workspace | Synthesize one workspace from the logged-in user |
| Folders | Return one synthetic placeholder per space, id `folder_<spaceId>`; reject `create_folder` with `ValidationError` |
| Raw API passthrough | Raise `ValidationError("raw_request not supported for Foo: ...")` |
| Anything else | Raise `ValidationError` with a message that tells the agent what to do instead |

Never silently return wrong data; agents act on it.

### 4. Register the adapter

In `clickup/core/providers.py`:

- Add a branch to `get_provider()` (import inside the branch so the
  dependency stays lazy).
- Add the name to `provider_requires_credentials()` if it needs auth.
- Extend the `ValueError` message listing valid provider names.

If the backend needs an SDK, add it to `pyproject.toml` dependencies.

### 5. Test it

- Unit tests with a faked SDK/HTTP layer under `tests/unit/`.
- Smoke-test the real thing end-to-end:

  ```bash
  CLICKUP_PROVIDER=foo FOO_URL=... uv run clickup discover hierarchy
  CLICKUP_PROVIDER=foo ... uv run clickup task create "test" --list-id <id>
  ```

- `just fc` must pass. If the adapter is an early prototype, you may exclude
  it from coverage/ty in `pyproject.toml` (the Planka adapter is excluded) —
  but say so in the PR.
- For agent-facing changes, run the `cli-agent-eval` skill.

### 6. Update the contract surface

- New provider name + env vars → document in `docs/backends.md`.
- If you had to *change* `TaskProvider` or the models, update
  `spec/openapi.yaml` in the same PR (the spec is derived from the protocol).

## History note

Three adapters were prototyped as a bake-off (Planka, Plane, Todoist — PRs
#30/#31/#32). Planka won and is merged; the other two live on the
`adapter/plane` and `adapter/todoist` branches as additional worked examples.
