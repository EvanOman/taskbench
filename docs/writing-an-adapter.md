# Writing a new backend adapter

How to add a backend as a Python adapter, either in-tree or as an external
package. (If you'd rather not write Python, implement `spec/openapi.yaml` as
an HTTP shim instead — see `spec/README.md`.)

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

Create a class implementing every method of the protocol
(`taskbench/core/providers.py`). It's a `typing.Protocol` — no inheritance,
just matching signatures. Rules:

- Return the pydantic models from `taskbench/core/models.py`, never raw dicts.
- IDs on the wire are **strings** (stringify your backend's ints). User IDs
  stay integers.
- Timestamps are **epoch-ms strings**.
- Read connection config from env vars prefixed with your backend name
  (`FOO_URL`, `FOO_TOKEN`, ...), with sane localhost defaults.
- Raise the typed exceptions from `taskbench/core/exceptions.py`
  (`NotFoundError`, `ValidationError`, `AuthenticationError`, ...) — `main.py`
  maps them onto exit codes and the stderr error envelope.

### 3. Degrade honestly, don't fake

For concepts your backend lacks:

| Missing concept | Pattern |
|---|---|
| Multi-workspace | Synthesize one workspace from the logged-in user |
| Folders | Return one synthetic placeholder per space, id `folder_<spaceId>`; reject `create_folder` with `ValidationError` |
| Raw API passthrough | Raise `ValidationError("raw_request not supported for Foo: ...")` |
| Anything else | Raise `ValidationError` with a message that tells the agent what to do instead |

Never silently return wrong data; agents act on it.

### 4. Register the adapter

**Option A: External package (recommended for non-ClickUp backends)**

Create a separate package with an entry point:

```toml
# In your adapter's pyproject.toml
[project.entry-points."taskbench.providers"]
foo = "taskbench_foo:FooProvider"
```

The factory function receives `(config: Config, console: Console | None)` and
must return an object matching `TaskProvider`. Install the adapter package and
`get_provider()` discovers it automatically via
`entry_points(group="taskbench.providers")`.

**Option B: In-tree adapter**

Add a branch to `get_provider()` in `taskbench/core/providers.py` (import
inside the branch so the dependency stays lazy). Update
`provider_requires_credentials()` if the adapter needs ClickUp auth.

### 5. Test it

- Unit tests with a faked SDK/HTTP layer under `tests/unit/`.
- Smoke-test the real thing end-to-end:

  ```bash
  TASKBENCH_PROVIDER=foo FOO_URL=... uv run taskbench discover hierarchy
  TASKBENCH_PROVIDER=foo ... uv run taskbench task create "test" --list-id <id>
  ```

- `just fc` must pass. If the adapter is an early prototype, you may exclude
  it from coverage/ty in `pyproject.toml` — but say so in the PR.
- For agent-facing changes, run the `cli-agent-eval` skill.

### 6. Update the contract surface

- New provider name + env vars → document in `docs/backends.md`.
- If you had to *change* `TaskProvider` or the models, update
  `spec/openapi.yaml` in the same PR (the spec is derived from the protocol).
