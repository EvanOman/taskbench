# Smoke E: inline priority help

## Discovery path
From `clickup task create --help`:
```
--priority  -p  INTEGER  Priority (1=urgent, 2=high, 3=normal, 4=low).
```

## Transcript
1. `clickup --help` -- found `task` subcommand
2. `clickup task --help` -- found `create` subcommand
3. `clickup task create --help` -- found `--priority` with inline scale: `1=urgent, 2=high, 3=normal, 4=low`
4. `clickup task create "Test high priority task" --list-id inbox --priority 2 --description "..."` -- created successfully
5. `clickup task get mock_1006` -- confirmed `"priority": 2, "priority_label": "high"`

## Did it work as expected?
Yes. The help text unambiguously documented the priority scale. Created task stored priority=2 and returned `priority_label: "high"`, matching intent.

## Friction
- None for priority discovery -- the inline `(1=urgent, 2=high, 3=normal, 4=low)` is exactly the right amount of context.
- Minor: first attempt with `--list-id omegapoint` failed because mock config only has `inbox`/`active` aliases -- not a priority-help issue.

## Verdict
pass
