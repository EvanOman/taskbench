# Factory Assessment — taskbench (formerly clickup-tools)

_Generated 2026-06-20 by `/factory-assess`. Framework: [Software Factory Operating Method](https://blog.sshh.io/p/designing-software-for-software-factories)._

## Headline

taskbench is already **one of the most factory-like projects you could point this at** — strong on seedability and testing, with a genuinely excellent contract and a working feedback loop. The one live problem: **today's `clickup` → `taskbench` rename drifted the contract.** The code is renamed and runs; the docs that tell agents how to navigate it still say `clickup/`.

## Scorecard — 10 / 12

| Pillar | Score | Evidence |
|---|---|---|
| **1 — Seedability** | **3/3** | `just fc` = format+lint(ruff)+type(ty)+test; CI green-gate; `--cov-fail-under=90`. Brownfield with strong patterns. An agent can reliably tell if a PR breaks functionality. Exemplary. |
| **2 — Contract** | **2/3** | `AGENT.md` is excellent in structure (docs map, 8 numbered load-bearing architecture decisions w/ rationale, decision log, risk boundaries, parked-features). Hits ~5/6 properties. **Docked one point: drifted today** — 9 stale `clickup/` path refs + stale entry-point names. |
| **3 — Harness** | **3/3** | 7-tier ladder: lint ✓ · type ✓ · unit ✓ · single-service integration (mocked e2e CLI) ✓ · live ✓ · **product-surface ✓ via `cli-agent-eval`** (a 12-task agent-as-customer swarm with friction metrics). Far past typical. Gaps: tier 3 (security scan) absent; tier 7 (rollout monitor) ~N/A for a CLI. |
| **4 — Feedback** | **2/3** | Real loop exists and works: eval friction → `evals/<sha>.json` delta tracking → GitHub issues → "backlog batch" commits → contract updates (18/18 consecutive eval runs achieved). Not yet a formalized/automated sticky batch; friction→contract encoding is manual. |

## The live gap: contract drift from the rename

The package rename is **structurally complete** (`taskbench` imports, `taskbench --help` runs, `pyproject.toml` updated, entry points now `taskbench`/`tb`), but the **contract and docs were not carried along**:

| File | Stale `clickup/` refs |
|---|---|
| `AGENT.md` | 9 |
| `README.md` | 6 |
| `docs/architecture.md` | 7 |
| `docs/writing-an-adapter.md` | 6 |
| `docs/backends.md` | 4 |
| `spec/README.md`, `spec/openapi.yaml` | yes |
| `.claude/skills/cli-agent-eval/SKILL.md` | yes |
| `research-agentic-clis/mock-study/00-synthesis.md` | yes (historical — leave) |

Also stale in `AGENT.md`: the entry-point/alias names. It documents `clickup` / `cup`; the binaries are now `taskbench` / `tb`. Any agent reading the contract to drive the CLI will reach for the wrong command.

This is exactly the failure mode the framework warns about — **a review gate (the contract) silently stops matching reality.** In factory terms: property 3 (stability) and the "agents must be able to navigate from the contract" guarantee both just broke.

## Recommended next steps (in order)

1. **Fix the contract drift now** (part of finishing the rename). Sweep `clickup/` → `taskbench/` and `clickup`/`cup` → `taskbench`/`tb` across `AGENT.md`, `README.md`, `docs/`, `spec/`, and the eval skill. Leave the `research-agentic-clis/` historical note. → would restore Pillar 2 to 3/3.
2. **Latent drift source:** `AGENT.md`'s hardcoded layout tree violates the framework's "don't enumerate files — point at a live command" rule, which is *why* the rename broke it. The annotated tree carries real semantic value (what each file does), so this is a judgment call: keep the annotated tree but treat it as a known maintenance point, or thin it to a `tree taskbench/` pointer + a short "what each subpackage means" prose block.
3. **Add Pillar-3 tier 3** (security/compliance scan): a `just audit` target (`uv run pip-audit`, ruff security rules) + a CI step. Cheap, agent-runnable, closes the one real ladder gap.
4. **Formalize Pillar 4** (make feedback sticky): the eval-friction → contract-patch loop already happens by hand; a `/factory-feedback`-style batch would systematize converting friction items into contract/code changes that deprecate the gate.

## Note

This repo is close enough to the framework that the highest-value use of these tools here is **maintenance** (keep the contract in sync, close the two small gaps), not a ground-up build. Good reference example of what "factory-like" converges toward.
