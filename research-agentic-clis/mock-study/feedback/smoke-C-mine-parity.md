# Smoke C: task mine filter parity

## Discovery path
`task mine --help` surfaced: `--status/-s`, `--sort/--order-by`, `--reverse`, `--brief`, `--limit`, `--open-only/--open`, `--updated-since`, `--workspace-id/-w`.

## Transcript
1. `clickup task mine --help` -- discovered flags
2. `clickup task mine --status "in progress" --sort "priority:desc" --brief` -- returned 2 tasks but sort order was wrong (normal before high)
3. `clickup task mine --status "in progress" --sort "priority" --brief` -- correct urgent-first ordering

## Did it work as expected?
Yes, after adjusting the sort direction.

## Friction
- Sort direction semantics are counterintuitive for priority. `:desc` produces *least*-urgent-first because priority 1=urgent, so higher numbers are lower priority. The help text doesn't clarify that `priority` ascending means urgent-first. An agent has to reason about the numeric encoding to pick the right direction.
- No shorthand like `--sort urgent-first` or `--urgent-first` flag exists.

## Verdict
partial
