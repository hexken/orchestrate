---
name: orchestrate-setup
description: Use when a project has a work plan and the user wants the orchestration workspace set up, or says "set up orchestration", "choose the models", "add a harness" or "write an adapter". Scaffolds .orchestrate/ in the repository, records the role table (harness, model, effort per role), installs or writes the harness and land adapters and checks them, creates the unit worktrees, and hands the owner the permissions script to run.
---

# Set up the workspace

Run in Herdr (`test "${HERDR_ENV:-}" = 1`, else stop). `ORCH` below is `uv run --project "${ORCHESTRATE_HOME:-$HOME/Dev/personal/orchestrate}" orch` until step 2, then `<repo>/.orchestrate/bin/orch`.

## 1. Ask what is not known yet

Bundle into at most two AskUserQuestion rounds:
- the main checkout's path and the destination branch units merge into;
- the planning repo's path and the work plan file;
- the forge (GitHub, Bitbucket, other) and its CLI;
- harness, model and effort per role. Offer the defaults from `ORCH roles` (shown after step 2) as the recommended option; the roles are orchestrator, builder, reviewer, second_reviewer (another vendor, print mode), light_reviewer, light_reviewer_claude (used when the builder is not Claude), proxy, proxy_second, mechanical;
- how many units may run at once (worktrees; two is a good start on one laptop);
- the checks a branch must pass before it is pushed: read the repository's CI config step by step and propose a local command for every step it runs (lint, types, tests, builds of other parts such as a UI, generated-file checks), not only the obvious ones. A CI failure costs a whole build; the same failure found by the push step costs seconds;
- whether whole-suite tests need a shared lock (a heavy suite on one laptop does). The push step holds `[land].heavy_lock` around the checks and sets `ORCH_HEAVY_LOCK_HELD=1`; a lock wrapper the project's own test command uses must skip locking when that is set, or a nested run deadlocks;
- whether the spec gate is on (`orchestrate-proxy`, `orchestrate-acceptance`).

## 2. Scaffold

`ORCH scaffold --repo <main checkout> --name <name> --destination <branch> --planning-repo <path> --land <forge adapter name>`

It writes `.orchestrate/` (never overwriting a file), the `bin/orch` wrapper, and adds `.orchestrate` and `scratch/` to the repository's `.git/info/exclude`.

## 3. Fill orchestrate.toml

Edit `.orchestrate/orchestrate.toml`; it is the one home of these values:
- `[project].work_plan`;
- `[roles.<role>]` for every role the user changed; an extra builder such as `[roles.builder_agy]` for units built on another harness, and a `[pipeline.<harness>]` saying which reviews a unit built on that harness gets. A pipeline's `light` role (a light review of the fixes) is empty by default: the builder proves each fix with a test that fails without it and the land re-runs every check. Set it only if the record shows fixes escaping;
- `[land]`: `checks`, `heavy_lock`, `theirs_on_conflict` and `commit_paths` if a check writes results that must be committed; `ci_config` (the CI files, relative to the repository) so `orch doctor` lists every CI step with no local counterpart, and `ci_ignore` for steps that only belong in CI (installs, deploys). Where `orch doctor` says it cannot parse a CI line, compare that part by hand;
- `[worktrees].share`: untracked files of the main checkout that every worktree needs (for example `.claude` or a local rules file);
- `[review].context`: files a print-mode reviewer needs copied in (spec, work plan);
- `briefs/refresh.md`: the message builders get when a sibling merges; add the project's conflict hints (which generated files to regenerate, which shared lists to keep both sides of);
- `[[sources.entries]]` and `[[homes]]` from `READINESS.md`;
- `[spec_gate]` if on.
`ORCH roles` then shows the table; `ORCH doctor` checks the rest.

## 4. Adapters

For each harness named in `[roles]` and for the forge:
1. If `$ORCHESTRATE_HOME/examples/adapters/<harness|land>-<name>` exists, copy it to `.orchestrate/adapters/` and make it executable.
2. Otherwise write one by following `references/adapters.md`: read the tool's official CLI documentation for how to start an interactive session with a model and effort, how to run one prompt non-interactively, and how it finds skills. Show the user any install command before running it.
3. Check each: `ORCH conform harness <name> --role <a role that uses it>` and `ORCH conform land <name>`. Add `--live` only with the user's yes: it makes two small real model calls.

## 5. Worktrees and rules

1. `ORCH worktrees --count <n>`: worktrees beside the main checkout, each with its clean push checkout, `.orchestrate` linked in, and `[worktrees].paths` recorded.
2. Each harness must read the project's rules in each worktree. For a harness that reads `AGENTS.md`, add an untracked `AGENTS.md` that includes `CLAUDE.md` (and any local rules file), excluded in `.git/info/exclude`. Record what you did in `.orchestrate/AGENT-SETUP.md`.
3. If a harness needs real copies of skills (its adapter's `describe` says so), run `ORCH skills-sync <harness> <skill folder>...`, and note in `AGENT-SETUP.md` to re-run it after a skill changes.

## 6. Permissions (the owner's step)

Show the owner `.orchestrate/setup-permissions.py` and what it allows. Agents never widen their own permissions: the owner reads it, edits it if they want, and runs it themself (`! python3 .orchestrate/setup-permissions.py`).

## 7. Finish

1. Write the first units and the work plan's path into "Current state" in `.orchestrate/ORCHESTRATION.md`.
2. `ORCH doctor` must report every line `ok`. Quote any line that is not, with its fix.
3. Next: `orchestrate-start`.
