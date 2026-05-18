# Agent 09 Report

## Use case
Create tasks with special characters (brackets, parens, exclamation) and multi-line descriptions; verify data integrity round-trips.

## Transcript
1. `clickup --help` -- discovered top-level commands and global `--format` flag
2. `clickup task --help` -- found `create`, `get`, `list`, etc.
3. `clickup task create --help` -- learned positional NAME arg plus `--list-id`, `--description`, etc.
4. `clickup mock init` -- seeded mock JSON backend
5. `clickup task create '[bug] Fix login page (urgent!)' --list-id list_inbox` -- created task mock_1006
6. `clickup task get mock_1006` -- verified name stored verbatim: `[bug] Fix login page (urgent!)`
7. `clickup task create 'Newline description test' --list-id list_inbox --description "$(printf 'Line one.\nLine two.')"` -- created task mock_1007
8. `clickup task get mock_1007` -- verified description contains literal newline
9. `clickup --format table task get mock_1006` -- table output also renders brackets intact (Rich markup escaping works)
10. `clickup --format table task get mock_1007` -- newline description renders across two rows in table

## What worked well
- Help text is clear and layered: top-level -> subcommand -> action
- Special characters in task names (`[bug]`, `(urgent!)`) stored and displayed without corruption in both JSON and table modes
- Newlines in descriptions work via shell `printf`; no CLI-level escaping needed
- JSON output is consistent and machine-parseable (all fields present, ISO timestamps)
- `mock init` bootstrapped a working offline backend with zero config

## Friction / surprises / broken things
- `mock init` silently overwrites `json_store_path` in the config file to a hardcoded global path (`~/.config/clickup-toolkit/mock-store.json`), discarding the user-specified path. This is surprising and destructive to the config.
- No `--description` stdin mode or heredoc hint in `--help`. Multi-line descriptions require shell tricks (`printf`, `$'...'`). An agent can figure it out, but a note in the help text would reduce guesswork.
- `mock init` output format defaults to JSON regardless of the config's `output_format: table` setting -- minor inconsistency.
- The default status is `to do` but the config mentions `default_status` is configurable; the relationship between config defaults and list defaults isn't documented in `--help`.

## Concrete improvement suggestions
- `mock init` should respect the existing `json_store_path` in the config and only set it if absent.
- Add a `--description-stdin` flag or accept `-` to read description from stdin, making multi-line descriptions trivial for agents (`echo "..." | clickup task create NAME --description-stdin`).
- Document the status fallback chain in `task create --help` (flag > config `default_status` > list default).

## Verdict
pass
