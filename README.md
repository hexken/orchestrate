# Orchestrate

Build a project with several coding agents at once, in Herdr, the terminal multiplexer for coding agents. An orchestrating session plans and judges; `orch` does the mechanical work. Each unit of work gets its own builder in its own Herdr tab. `orch` starts the reviews when the builder finishes, sends the findings back, then lands the branch (push, pull request, build) and merges it once the build is green and the reviews are clean. At breakpoints it aligns the specs, notes and code, compacts the bookkeeping, and reports to the owner.

It is two things:
- **Skills** (`skills/`): procedures a coding agent follows, one per step.
- **`orch`**: a small Python package (standard library only) for the parts that must be deterministic: the unit state machine, the registry and event log, verdicts, the push step, scaffolding, worktrees, breakpoints, the alignment and compaction checks, the spec-gate scan, and the report the optimizer reads.

Harnesses (Claude Code, Antigravity, others) and forges (Bitbucket, GitHub, others) sit behind small **adapters** with a fixed contract. Worked examples are in `examples/adapters/`. For any other tool, the setup skill has the agent write an adapter from that tool's docs and check it with `orch conform`.

## Prerequisites

- Herdr, with `herdr-name` (names an agent so the name survives restarts).
- git, [uv](https://docs.astral.sh/uv/), Python 3.11 or later.
- At least one harness CLI, logged in, and the forge's CLI, logged in.
- A project in git with an `origin` remote.

`orch doctor` checks all of these.

## The path

| Step | Skill | Result |
|---|---|---|
| 1 | `orchestrate-onboard` | Prerequisites checked, and the requirements (prose, stories, Gherkin, an ontology, an ontology with flows) checked against a readiness bar: `READINESS.md` |
| 2 | `orchestrate-plan` | A work plan of units, milestones, waves and interfaces |
| 3 | `orchestrate-setup` | `.orchestrate/` in the repository: config, role table, adapters, briefs, worktrees, a permissions script for the owner to run |
| 4 | `orchestrate-start`, `-status`, `-stop`, `-resume` | The loop: units built, reviewed, landed and merged |
| 5 | `orchestrate-breakpoint`, `orchestrate-align`, `orchestrate-compact` | At each milestone's end, or at one the owner adds: every source checked against the code, change narration removed, notes compacted, one message to the owner |
| 6 | `orchestrate-optimize` | Proposed changes to roles, models, pipelines and timeouts, from the logs |

Optional spec gate: `orchestrate-proxy` (a model rules on questions in the owner's place, with a blind first answer and a second vendor's vote) and `orchestrate-acceptance` (acceptance tests in domain language against a small DSL, installed by script, checked against the spec's scenario titles).

`skills/orchestrate/SKILL.md` is the index: the words used throughout, the rules every skill keeps, and where state lives.

## `orch`

In a set-up project, run `.orchestrate/bin/orch <verb>`. Before setup, run `uv run --project ~/Dev/personal/orchestrate orch <verb>`.

| Verb | Does |
|---|---|
| `doctor` | Checks the prerequisites, the config and the adapters |
| `scaffold --repo PATH` | Writes `.orchestrate/` into a repository; never overwrites |
| `worktrees --count N` | Unit worktrees, their clean push checkouts, the workspace linked in |
| `conform harness NAME` / `conform land NAME` | Checks an adapter against its contract (`--live` makes two small real calls) |
| `roles` | Prints the role table and review pipelines |
| `start UNIT --worktree PATH --plan FILE` | Cuts the unit's branch, opens its Herdr tab, starts its builder and live view |
| `supervise` | Runs the unit flow every `poll_seconds` until an event; one per workspace |
| `stop` | Stops this workspace's supervisor; running review and land jobs finish |
| `status`, `timeline UNIT`, `watch UNIT` | The registry, one unit's marks, its live view |
| `resume UNIT STATUS`, `reland UNIT`, `merge UNIT`, `close UNIT`, `note UNIT TEXT` | Handle an event; record an owner input or intervention |
| `breakpoint add NAME --after U,…` / `--now` / `--milestone N`, `breakpoint list`, `breakpoint pass NAME` | Breakpoints |
| `align` | Dead references, terms defined twice, missing homes, unclassified sources, scan failures: a worklist |
| `compact scan PATH…`, `compact verify BEFORE AFTER` / `--rev REV PATH` | Change-narration candidates; refuses a conservative pass that lost meaning |
| `scan` | Spec gate: scenario titles and guarantees against the acceptance tests |
| `install-acceptance [--sync]` | Spec gate: installs drafted acceptance tests after the checks pass |
| `report [--since DATE] [--json]` | Stage times, fix rounds, events, review yield and tokens per role |
| `skills-sync HARNESS PATH…` | Copies skills where a harness needs real files |

A running supervisor reads the config once, at start: after editing `orchestrate.toml` or the package, `orch stop` and start it again. Never edit a shell adapter while a job is running it, because bash reads a script as it runs.

## Config

`.orchestrate/orchestrate.toml`. Relative paths are relative to the file's folder. Each key's default is in `src/orchestrate/config.py` (`orch roles` prints the roles); `orch scaffold` writes a file with the defaults filled in.

| Section | Key | Meaning |
|---|---|---|
| `[project]` | `name` | Project name |
| | `repo` | The main checkout; agents never touch it |
| | `destination` | The branch units merge into |
| | `branch_prefix` | Unit branches are `<prefix><unit in lowercase>` |
| | `planning_repo` | Where specs, plans and bookkeeping live |
| | `work_plan` | The work-plan file; `orch` reads its `ID` and `Milestone` columns |
| | `scratch` | Per-worktree folder for briefs, summaries and reviews (git-excluded) |
| `[herdr]` | `workspace` | Herdr workspace for unit tabs |
| | `orchestrator_pane` | The orchestrator's pane, for reference |
| `[worktrees]` | `paths` | Unit worktrees (`orch worktrees` fills it) |
| | `share` | Untracked files of the main checkout linked into each worktree |
| `[land]` | `adapter` | `adapters/land-<name>` |
| | `checks` | Shell commands run in the clean push checkout before a push |
| | `heavy_lock` | Lock file held around the checks and the push, for a heavy suite on one machine |
| | `push_suffix` | Push checkout path is `<worktree><suffix>` |
| | `timeout_minutes` | How long a land waits for the build |
| | `theirs_on_conflict` | Files where the destination's version wins a merge conflict |
| | `commit_paths` | Files the checks write that are committed before the push |
| | `ci_config` | The forge's CI file, relative to the repository; `orch doctor` lists each CI command with no counterpart in `checks` |
| | `ci_ignore` | Regexes: a CI command, or a CI line `orch doctor` cannot parse, that matches one needs no local counterpart (installs, deploys) |
| `[timeouts]` | `stall_minutes` | An idle agent with nothing new for this long is an event |
| | `wedged_minutes` | A "working" agent whose transcript is silent this long is an event |
| | `job_hours` | A background job running longer is an event |
| | `poll_seconds` | Supervisor pass interval |
| | `idle_seconds` | An agent counts as finished after two idle readings this far apart |
| `[review]` | `clean` | Verdict words that pass |
| | `hold` | Verdict words that send fixes |
| | `docs_only` | A change touching only these gets no review (`*` stays within a folder) |
| | `verdict_lines` | A bare verdict line must come within this many lines |
| | `context` | Files copied into a print-mode reviewer's throwaway worktree |
| `[roles.<role>]` | `harness`, `model`, `effort`, `mode` | One per role; `mode` is `interactive` or `print` |
| `[pipeline.<harness>]` | `reviews`, `light` | Reviews a unit built on that harness gets, and its light reviewer of the fixes (empty, the default: none; the fixes land with every check re-run) |
| `[sources]` | `impl_docs` | `deferred` while implementation docs wait for the end; `maintained` otherwise |
| `[[sources.entries]]` | `path`, `kind`, `owner`, `compact`, `root` | A file or glob; kind `spec`, `plan`, `bookkeeping`, `memory`, `log`, `code` or `docs`; owner `owner` or `agent`; compact `conservative`, `full` or `none`; root `impl`, `planning` or `workspace` (absolute and `~` paths stand alone) |
| `[[homes]]` | `question`, `path`, `root` | The one home of each kind of fact |
| `[breakpoints]` | `steps` | Steps run at each breakpoint |
| | `conditional_go` | Conditions under which the build carries on without waiting |
| `[spec_gate]` | `enabled` | Turns on the spec gate |
| | `spec` | The spec file |
| | `acceptance_dir`, `drafts_dir` | Installed tests and their drafts |
| | `install_checks` | Commands that must pass before drafts are committed |
| | `title_section`, `title_pattern`, `guarantee_pattern`, `test_marker` | How scenario titles, guarantee IDs and test markers are found |
| | `property_dir` | Tests here need no scenario title |
| | `milestone` | Untested titles of earlier milestones fail the scan |

## Trying it

This repository is not installed anywhere. To try the skills on one project, link them into that project's `.claude/skills/` (excluded from its git) or point your agent at `skills/` directly. To install it properly, follow `INSTALL.md`.

## Development

```shell
uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest -q
```

Tests use fakes for Herdr, the harness CLIs, remotes and forge CLIs, and never start a real agent session.
