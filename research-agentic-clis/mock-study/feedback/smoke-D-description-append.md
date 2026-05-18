# Smoke D: task update --description-append

## Discovery path
`clickup task update --help` listed `--description-append` with clear docs: "Append text to the existing description. The caller supplies any leading separator."

## Transcript
1. `clickup task mine` -- found task `mock_1001` with description "Summarize completed work, blockers, and next actions."
2. `clickup task update mock_1001 --description-append " — due Friday"`
3. `clickup task get mock_1001` -- confirmed description is now "Summarize completed work, blockers, and next actions. — due Friday"

## Did it work as expected?
Yes.
- **Before:** "Summarize completed work, blockers, and next actions."
- **After:** "Summarize completed work, blockers, and next actions. — due Friday"

## Friction
- None. The flag was clearly documented and worked on the first try.
- Nice that the caller controls the separator rather than the CLI injecting one.

## Verdict
pass
